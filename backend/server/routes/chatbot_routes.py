import logging
import hmac
from hashlib import sha256
from secrets import token_urlsafe

from flask import Blueprint, current_app, jsonify, request, session

from ..auth import STUDENT_SESSION_TOKEN_KEY, STUDENT_TERMS_ACCEPTED_SESSION_KEY
from ..db import fetch_account_by_id, save_chatbot_feedback
from ..request_validation import require_login

from ..services import ai_service, student_session_service, transient_chat_service
from ..services.conversation_service import (
    determine_escalation_reason,
    finalize_conversation,
    ensure_staff_visible_active_conversation,
    mark_active_conversation_for_staff_review,
    mark_active_conversation_for_immediate_review,
    record_chat_inquiry,
    save_flagged_case_transcript,
    should_escalate_conversation,
)

logger = logging.getLogger(__name__)

_ESCALATION_SESSION_KEY = "conversation_escalated"
_ESCALATION_REASON_SESSION_KEY = "conversation_escalation_reason"
_REVIEW_FLAG_SESSION_KEY = "conversation_needs_staff_review"
_FINALIZATION_APPOINTMENT_KEY = "finalization_appointment"
_ACTIVE_SUMMARY_SESSION_KEY = "active_conversation_summary_id"
_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY = "chatbot_feedback_response_tokens"
_FEEDBACK_TOKEN_LIMIT = 20
_FEEDBACK_COMMENT_LIMIT = 500
_FEEDBACK_CONTEXTS = frozenset(
    {
        "appointment",
        "academics",
        "office_services",
        "counseling_support",
        "general_support",
        "safety",
    }
)
_FEEDBACK_CATEGORIES = frozenset(
    {
        "helpful",
        "clear_useful",
        "not_helpful",
        "incorrect_information",
        "did_not_understand",
        "safety_concern",
        "other",
    }
)


def _opaque_session_id() -> str:
    """Return the server-side session identifier without exposing it to clients."""

    return str(getattr(session, "sid", "") or "").strip()


def _feedback_context_for_result(result: object, should_escalate: bool) -> str:
    """Map server-derived routing data to a small, non-transcript feedback tag."""
    if should_escalate:
        return "safety"

    normalized_topic = str(
        getattr(result, "normalized_topic", "") or ""
    ).casefold()
    context_by_topic = {
        "appointments": "appointment",
        "academics": "academics",
        "school_services": "office_services",
        "counseling": "counseling_support",
        "mental_health": "counseling_support",
    }
    return context_by_topic.get(normalized_topic, "general_support")


def _register_feedback_response_token(summary_id: int, response_context: str) -> str:
    """Keep short-lived feedback authorization server-side in the session."""
    token = token_urlsafe(24)
    prior_tokens = session.get(_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY, [])
    if not isinstance(prior_tokens, list):
        prior_tokens = []
    tokens = [entry for entry in prior_tokens if isinstance(entry, dict)]
    tokens.append(
        {
            "token": token,
            "summary_id": int(summary_id),
            "response_context": (
                response_context
                if response_context in _FEEDBACK_CONTEXTS
                else "general_support"
            ),
        }
    )
    session[_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY] = tokens[-_FEEDBACK_TOKEN_LIMIT:]
    return token


def _feedback_summary_for_token(token: str) -> int | None:
    """Resolve a client token only when it belongs to this authenticated session."""
    tokens = session.get(_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY, [])
    if not isinstance(tokens, list):
        return None
    for entry in tokens:
        if not isinstance(entry, dict):
            continue
        stored_token = entry.get("token")
        if isinstance(stored_token, str) and hmac.compare_digest(stored_token, token):
            try:
                return int(entry["summary_id"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _feedback_context_for_token(token: str) -> str | None:
    """Return only the server-derived context attached to this session token."""
    tokens = session.get(_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY, [])
    if not isinstance(tokens, list):
        return None
    for entry in tokens:
        if not isinstance(entry, dict):
            continue
        stored_token = entry.get("token")
        if isinstance(stored_token, str) and hmac.compare_digest(stored_token, token):
            response_context = entry.get("response_context")
            return (
                response_context
                if isinstance(response_context, str)
                and response_context in _FEEDBACK_CONTEXTS
                else "general_support"
            )
    return None


def _consume_feedback_response_token(token: str) -> None:
    tokens = session.get(_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY, [])
    if not isinstance(tokens, list):
        return
    session[_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY] = [
        entry
        for entry in tokens
        if not (
            isinstance(entry, dict)
            and isinstance(entry.get("token"), str)
            and hmac.compare_digest(entry["token"], token)
        )
    ]

chatbot_bp = Blueprint(
    "chatbot",
    __name__,
)


@chatbot_bp.post("/internal/maintenance/finalize-idle-student-conversations")
def finalize_idle_student_conversations():
    """Finalize abandoned student chats for the VPS-local maintenance timer.

    This endpoint deliberately has no browser session.  It is protected by a
    server-only secret header and is called through the loopback Gunicorn
    listener, never by the public UI.
    """

    configured_key = str(
        current_app.config.get("STUDENT_CHAT_IDLE_FINALIZER_KEY") or ""
    )
    provided_key = request.headers.get("X-CTRL4-Idle-Finalizer-Key", "")
    if not configured_key or not hmac.compare_digest(configured_key, provided_key):
        logger.warning("Rejected idle student conversation finalizer request.")
        return jsonify(
            {
                "success": False,
                "message": "Maintenance authorization failed.",
                "errors": None,
            }
        ), 403

    report = student_session_service.finalize_idle_sessions(
        idle_timeout_seconds=current_app.config[
            "STUDENT_CHAT_IDLE_TIMEOUT_SECONDS"
        ],
        transient_chat=transient_chat_service,
        finalizer=finalize_conversation,
        user_loader=lambda account_id: fetch_account_by_id(
            account_id,
            role="student",
        ),
    )
    logger.info(
        "Idle student conversation maintenance completed "
        "(checked=%s finalized=%s cleared=%s failed=%s).",
        report["checked"],
        report["finalized"],
        report["cleared"],
        report["failed"],
    )
    return jsonify(
        {
            "success": True,
            "message": "Idle student conversation maintenance completed.",
            "data": report,
        }
    ), 200


@chatbot_bp.post("/chat")
def chat():
    payload = request.get_json(silent=True) or {}

    user = require_login()
    if not user:
        return jsonify(
            {
                "success": False,
                "message": "Login required.",
                "errors": None,
            }
        ), 401

    if (
        str(user.get("role", "")).lower() == "student"
        and session.get(STUDENT_TERMS_ACCEPTED_SESSION_KEY) is not True
    ):
        return jsonify(
            {
                "success": False,
                "message": "Accept the terms and conditions before starting the chat.",
                "errors": None,
            }
        ), 403

    message = str(payload.get("message", "")).strip()

    if not message:
        return jsonify(
            {
                "success": False,
                "message": "Message is required.",
                "errors": None,
            }
        ), 400

    try:
        prior_history = transient_chat_service.prior_history(
            _opaque_session_id(),
            user.get("id"),
            payload.get("conversation", []),
            message,
        )
        result = ai_service.respond(
            message=message,
            conversation=prior_history,
            user=user,
        )

        logger.info(
            "AI response generated (emotion=%s, language=%s, escalated=%s, confidence=%.4f)",
            result.emotion,
            result.language,
            result.escalated,
            result.confidence,
        )
        if not result.success:
            logger.warning("AIService returned an unsuccessful chat result.")
            return jsonify(
                {
                    "success": False,
                    "message": "Unable to generate a response.",
                    "data": {
                        "response": result.response,
                    },
                }
            ), 200

        record_chat_inquiry(
            account_id=user["id"],
            emotion=result.emotion,
            escalated=result.escalated,
        )
        transient_chat_service.record_exchange(
            _opaque_session_id(),
            user.get("id"),
            prior_history,
            message,
            result.response,
        )
        if session.get(_ACTIVE_SUMMARY_SESSION_KEY) is None:
            session[_ACTIVE_SUMMARY_SESSION_KEY] = ensure_staff_visible_active_conversation(
                user["id"]
            )
        should_escalate = should_escalate_conversation(
            escalated=result.escalated,
            normalized_emotion=result.normalized_emotion,
        )
        needs_staff_review = bool(getattr(result, "needs_staff_review", False))
        feedback_token = _register_feedback_response_token(
            int(session[_ACTIVE_SUMMARY_SESSION_KEY]),
            _feedback_context_for_result(result, should_escalate),
        )
        session_escalated = bool(session.get(_ESCALATION_SESSION_KEY))
        if needs_staff_review:
            # Warning signs retain the normal supportive response, but are
            # immediately visible to authorized counselors as a pending review.
            # This is separate from the urgent-crisis notification path below.
            session[_REVIEW_FLAG_SESSION_KEY] = True
            mark_active_conversation_for_staff_review(
                int(session[_ACTIVE_SUMMARY_SESSION_KEY]),
                user["id"],
                "Counselor review requested for a reported wellbeing warning sign.",
            )
        if should_escalate:
            escalation_reason = (
                determine_escalation_reason(
                    escalated=result.escalated,
                    normalized_emotion=result.normalized_emotion,
                )
                or "AI safety escalation."
            )
            session[_ESCALATION_SESSION_KEY] = True
            session[_ESCALATION_REASON_SESSION_KEY] = escalation_reason
            mark_active_conversation_for_immediate_review(
                int(session[_ACTIVE_SUMMARY_SESSION_KEY]),
                user["id"],
                escalation_reason,
            )
        if bool(
            session.get(_ESCALATION_SESSION_KEY)
            or session.get(_REVIEW_FLAG_SESSION_KEY)
        ):
            save_flagged_case_transcript(
                int(session[_ACTIVE_SUMMARY_SESSION_KEY]),
                transient_chat_service.get_transcript_history(
                    _opaque_session_id(),
                    user.get("id"),
                ),
            )
        if str(user.get("role", "")).lower() == "student":
            student_session_service.update_conversation_context(
                user.get("id"),
                session.get(STUDENT_SESSION_TOKEN_KEY),
                topic=result.topic,
                language=result.language,
                emotion=result.emotion,
                flagged=bool(
                    session.get(_ESCALATION_SESSION_KEY)
                    or session.get(_REVIEW_FLAG_SESSION_KEY)
                ),
                review_only=bool(session.get(_REVIEW_FLAG_SESSION_KEY))
                and not bool(session.get(_ESCALATION_SESSION_KEY)),
                escalation_reason=session.get(_ESCALATION_REASON_SESSION_KEY),
                appointment=session.get(_FINALIZATION_APPOINTMENT_KEY),
                active_summary_id=session.get(_ACTIVE_SUMMARY_SESSION_KEY),
            )
            student_session_service.record_chat_activity(
                user.get("id"),
                session.get(STUDENT_SESSION_TOKEN_KEY),
            )

        return jsonify(
            {
                "success": True,
                "message": "Response generated successfully.",
                "data": {
                    "response": result.response,
                    "emotion": result.emotion,
                    "sentiment": result.sentiment,
                    "language": result.language,
                    "topic": result.topic,
                    "escalated": should_escalate,
                    "needs_staff_review": needs_staff_review,
                    "session_escalated": session_escalated or should_escalate,
                    "confidence": round(result.confidence, 4),
                    "feedback_token": feedback_token,
                },
            }
        ), 200

    except Exception as exc:
        logger.error(
            "Chat request processing failed (exception_type=%s).",
            type(exc).__name__,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@chatbot_bp.post("/chat/feedback")
def submit_chat_feedback():
    """Record one optional rating for a bot reply without storing chat text."""
    payload = request.get_json(silent=True) or {}
    user = require_login()
    if not user:
        return jsonify(
            {"success": False, "message": "Login required.", "errors": None}
        ), 401
    if str(user.get("role", "")).lower() != "student":
        return jsonify(
            {"success": False, "message": "Student access required.", "errors": None}
        ), 403
    if session.get(STUDENT_TERMS_ACCEPTED_SESSION_KEY) is not True:
        return jsonify(
            {
                "success": False,
                "message": "Accept the terms and conditions before sending feedback.",
                "errors": None,
            }
        ), 403

    token = str(payload.get("response_token", "")).strip()
    category = str(payload.get("category", "")).strip().lower()
    raw_comment = payload.get("comment", "")
    comment = "" if raw_comment is None else str(raw_comment).strip()

    if not token or _feedback_summary_for_token(token) is None:
        return jsonify(
            {
                "success": False,
                "message": "This reply can no longer receive feedback.",
                "errors": None,
            }
        ), 400
    if category not in _FEEDBACK_CATEGORIES:
        return jsonify(
            {"success": False, "message": "Select a valid feedback category.", "errors": None}
        ), 400
    if len(comment) > _FEEDBACK_COMMENT_LIMIT:
        return jsonify(
            {
                "success": False,
                "message": "Feedback comments must be 500 characters or fewer.",
                "errors": None,
            }
        ), 400

    summary_id = _feedback_summary_for_token(token)
    response_context = _feedback_context_for_token(token)
    if summary_id is None or response_context is None:
        return jsonify(
            {
                "success": False,
                "message": "This reply can no longer receive feedback.",
                "errors": None,
            }
        ), 400

    try:
        feedback_id = save_chatbot_feedback(
            {
                "account_id": int(user["id"]),
                "conversation_summary_id": summary_id,
                "response_token_hash": sha256(token.encode("utf-8")).hexdigest(),
                "category": category,
                "comment": comment or None,
                "response_context": response_context,
            }
        )
        _consume_feedback_response_token(token)
    except Exception as exc:
        logger.error(
            "Chat feedback persistence failed (exception_type=%s).",
            type(exc).__name__,
        )
        return jsonify(
            {"success": False, "message": "Unable to save feedback.", "errors": None}
        ), 500

    return jsonify(
        {
            "success": True,
            "message": "Thank you for your feedback.",
            "data": {"feedback_id": feedback_id},
        }
    ), 201


@chatbot_bp.post("/chat/finalize")
def finalize_chat():
    payload = request.get_json(silent=True) or {}

    user = require_login()
    if not user:
        return jsonify(
            {
                "success": False,
                "message": "Login required.",
                "errors": None,
            }
        ), 401

    # Finalization trusts only server-owned transient exchanges. The browser
    # welcome is display-only and must never become summary evidence.
    conversation = transient_chat_service.get_visible_history(
        _opaque_session_id(),
        user.get("id"),
    )

    try:
        result = finalize_conversation(
            user=user,
            conversation=conversation,
            topic=str(payload.get("topic", "general")),
            language=str(payload.get("language", "unknown")),
            emotion=str(payload.get("emotion", "neutral")),
            flagged=bool(
                session.get(_ESCALATION_SESSION_KEY)
                or session.get(_REVIEW_FLAG_SESSION_KEY)
            ),
            review_only=bool(session.get(_REVIEW_FLAG_SESSION_KEY))
            and not bool(session.get(_ESCALATION_SESSION_KEY)),
            escalation_reason=session.get(_ESCALATION_REASON_SESSION_KEY),
            appointment=session.get(_FINALIZATION_APPOINTMENT_KEY),
            active_summary_id=session.get(_ACTIVE_SUMMARY_SESSION_KEY),
        )
        session.pop(_ESCALATION_SESSION_KEY, None)
        session.pop(_ESCALATION_REASON_SESSION_KEY, None)
        session.pop(_REVIEW_FLAG_SESSION_KEY, None)
        session.pop(_FINALIZATION_APPOINTMENT_KEY, None)
        session.pop(_ACTIVE_SUMMARY_SESSION_KEY, None)
        session.pop(_FEEDBACK_RESPONSE_TOKENS_SESSION_KEY, None)
        transient_chat_service.clear(_opaque_session_id(), user.get("id"))
        if str(user.get("role", "")).lower() == "student":
            student_session_service.clear_conversation_context(
                user.get("id"),
                session.get(STUDENT_SESSION_TOKEN_KEY),
            )

        message = (
            "No meaningful student message was recorded."
            if result.get("status") == "skipped"
            else "Conversation finalized successfully."
        )

        return jsonify(
            {
                "success": True,
                "message": message,
                "data": result,
            }
        ), 200

    except Exception as exc:
        logger.error(
            "Conversation finalization failed (exception_type=%s).",
            type(exc).__name__,
        )

        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500
