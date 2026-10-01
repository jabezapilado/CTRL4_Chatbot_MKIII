import logging
from flask import Blueprint, jsonify, request

from ..request_validation import require_role
from ..services.case_note_service import (
    create_staff_case_note,
    list_staff_case_notes,
    update_staff_case_note,
)
from ..services.referral_service import (
    add_staff_referral_note,
    create_staff_referral,
    list_staff_referrals,
    update_staff_referral_status,
)
from ..services.intervention_service import (
    create_staff_intervention,
    list_staff_interventions,
    record_staff_intervention_outcome,
    update_staff_intervention_progress,
)
from ..services.confidentiality_service import (
    get_staff_case_confidentiality,
    update_staff_case_confidentiality,
)
from ..services.conversation_service import (
    get_staff_inbox_item,
    get_staff_flagged_case_transcript,
    list_staff_flagged_case_items,
    list_staff_inbox_items,
    list_staff_reviewed_case_history,
    list_staff_conversation_summaries,
    list_staff_escalations,
    list_staff_chatbot_feedback,
    summarize_staff_chatbot_feedback,
    list_staff_inquiries,
    mark_staff_flagged_conversation_reviewed,
)

logger = logging.getLogger(__name__)

conversation_bp = Blueprint(
    "conversation",
    __name__,
    url_prefix="/api",
)


def _authorized_flagged_case_or_not_found(staff_account: dict, summary_id: int):
    """Reuse Staff Inbox program scope for every flagged-case subresource."""
    item = get_staff_inbox_item(staff_account, summary_id)
    if item is not None and item.get("flagged_status"):
        return item, None
    return None, (
        jsonify(
            {
                "success": False,
                "message": "Flagged conversation not found.",
                "errors": None,
            }
        ),
        404,
    )


@conversation_bp.get("/staff/inbox")
def staff_inbox():
    user, error = require_role("staff")
    if error:
        return error
    try:
        response = jsonify(
            {
                "success": True,
                "message": "Staff inbox retrieved successfully.",
                "data": {"items": list_staff_inbox_items(user)},
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception("Failed to retrieve staff inbox.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/staff/chatbot-feedback")
def staff_chatbot_feedback():
    """Show only feedback from students in the logged-in counselor's programs."""
    user, error = require_role("staff")
    if error:
        return error
    try:
        items = list_staff_chatbot_feedback(user)
        response = jsonify(
            {
                "success": True,
                "message": "Chatbot feedback retrieved successfully.",
                "data": {
                    "items": items,
                    "insights": summarize_staff_chatbot_feedback(items),
                },
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception("Failed to retrieve chatbot feedback.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/staff/inbox/<int:summary_id>")
def staff_inbox_detail(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    try:
        item = get_staff_inbox_item(user, summary_id)
        if item is None:
            return jsonify(
                {
                    "success": False,
                    "message": "Inbox item not found.",
                    "errors": None,
                }
            ), 404
        response = jsonify(
            {
                "success": True,
                "message": "Inbox item retrieved successfully.",
                "data": item,
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception("Failed to retrieve staff inbox item %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/staff/inbox/<int:summary_id>/history")
def staff_reviewed_case_history(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    try:
        items = list_staff_reviewed_case_history(user, summary_id)
        if items is None:
            return jsonify(
                {
                    "success": False,
                    "message": "Inbox item not found.",
                    "errors": None,
                }
            ), 404
        response = jsonify(
            {
                "success": True,
                "message": "Reviewed case history retrieved successfully.",
                "data": {"items": items},
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception("Failed to retrieve reviewed case history for %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/inquiries")
def inquiries():
    user, error = require_role("staff")
    if error:
        return error
    try:
        items = list_staff_inquiries(user)
        return jsonify(
            {
                "success": True,
                "message": "Inquiries retrieved successfully.",
                "data": {
                    "items": items,
                },
            }
        ), 200
    except Exception:
        logger.exception("Failed to retrieve inquiries.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/conversation-summaries")
def conversation_summaries():
    user, error = require_role("staff")
    if error:
        return error
    try:
        items = list_staff_conversation_summaries(user)
        return jsonify(
            {
                "success": True,
                "message": "Conversation summaries retrieved successfully.",
                "data": {
                    "items": items,
                },
            }
        ), 200
    except Exception:
        logger.exception("Failed to retrieve conversation summaries.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/escalations")
def escalations():
    user, error = require_role("staff")
    if error:
        return error
    try:
        items = list_staff_escalations(user)
        return jsonify(
            {
                "success": True,
                "message": "Escalations retrieved successfully.",
                "data": {
                    "items": items,
                },
            }
        ), 200
    except Exception:
        logger.exception("Failed to retrieve escalations.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/flagged-conversations")
def flagged_conversations():
    user, error = require_role("staff")
    if error:
        return error
    try:
        response = jsonify(
            {
                "success": True,
                "message": "Flagged conversations retrieved successfully.",
                "data": {
                    "items": list_staff_flagged_case_items(user),
                },
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception("Failed to retrieve flagged conversations.")
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/flagged-conversations/<int:summary_id>")
def flagged_conversation(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    try:
        item, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
        if access_error:
            return access_error
        return jsonify(
            {
                "success": True,
                "message": "Flagged conversation retrieved successfully.",
                "data": item,
            }
        ), 200
    except Exception:
        logger.exception("Failed to retrieve flagged conversation %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/flagged-conversations/<int:summary_id>/transcript")
def flagged_conversation_transcript(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    try:
        transcript = get_staff_flagged_case_transcript(user, summary_id)
        if transcript is None:
            return jsonify(
                {
                    "success": False,
                    "message": "Flagged conversation not found.",
                    "errors": None,
                }
            ), 404
        response = jsonify(
            {
                "success": True,
                "message": "Flagged conversation transcript retrieved successfully.",
                "data": {"items": transcript},
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        logger.exception(
            "Failed to retrieve flagged conversation transcript for %s.",
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.patch("/flagged-conversations/<int:summary_id>/review")
def review_flagged_conversation(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    try:
        _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
        if access_error:
            return access_error
        item = mark_staff_flagged_conversation_reviewed(summary_id)
        if item is None:
            return jsonify(
                {
                    "success": False,
                    "message": "Flagged conversation not found.",
                    "errors": None,
                }
            ), 404
        return jsonify(
            {
                "success": True,
                "message": "Flagged conversation marked as reviewed.",
                "data": item,
            }
        ), 200
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 409
    except Exception:
        logger.exception("Failed to review flagged conversation %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.get("/flagged-conversations/<int:summary_id>/confidentiality")
def case_confidentiality(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error
    try:
        confidentiality = get_staff_case_confidentiality(summary_id)
        return jsonify(
            {
                "success": True,
                "message": "Case confidentiality retrieved successfully.",
                "data": confidentiality,
            }
        ), 200
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except Exception:
        logger.exception("Failed to retrieve confidentiality for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.patch("/flagged-conversations/<int:summary_id>/confidentiality")
def update_case_confidentiality(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        confidentiality = update_staff_case_confidentiality(
            user,
            summary_id,
            str(payload.get("confidentiality_status", "")),
            payload.get("confidentiality_reason"),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception("Failed to update confidentiality for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info("Staff %s updated confidentiality for case %s.", user["id"], summary_id)
    return jsonify(
        {
            "success": True,
            "message": "Case confidentiality updated successfully.",
            "data": confidentiality,
        }
    ), 200


@conversation_bp.get("/flagged-conversations/<int:summary_id>/notes")
def case_notes(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error
    try:
        items = list_staff_case_notes(summary_id)
        return jsonify(
            {
                "success": True,
                "message": "Counselor notes retrieved successfully.",
                "data": {"items": items},
            }
        ), 200
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except Exception:
        logger.exception("Failed to retrieve counselor notes for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.post("/flagged-conversations/<int:summary_id>/notes")
def create_case_note(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        note = create_staff_case_note(
            user,
            summary_id,
            str(payload.get("note_text", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception("Failed to create counselor note for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info("Staff %s created counselor note for case %s.", user["id"], summary_id)
    return jsonify(
        {
            "success": True,
            "message": "Counselor note created successfully.",
            "data": note,
        }
    ), 201


@conversation_bp.patch(
    "/flagged-conversations/<int:summary_id>/notes/<int:note_id>"
)
def update_case_note(summary_id: int, note_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        note = update_staff_case_note(
            user,
            summary_id,
            note_id,
            str(payload.get("note_text", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception(
            "Failed to update counselor note %s for case %s.",
            note_id,
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info(
        "Staff %s updated counselor note %s for case %s.",
        user["id"],
        note_id,
        summary_id,
    )
    return jsonify(
        {
            "success": True,
            "message": "Counselor note updated successfully.",
            "data": note,
        }
    ), 200


@conversation_bp.get("/flagged-conversations/<int:summary_id>/referrals")
def referrals(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error
    try:
        items = list_staff_referrals(summary_id)
        return jsonify(
            {
                "success": True,
                "message": "Referrals retrieved successfully.",
                "data": {"items": items},
            }
        ), 200
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except Exception:
        logger.exception("Failed to retrieve referrals for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.post("/flagged-conversations/<int:summary_id>/referrals")
def create_referral(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        referral = create_staff_referral(
            user,
            summary_id,
            str(payload.get("destination", "")),
            str(payload.get("referral_reason", "")),
            payload.get("note_text"),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception("Failed to create referral for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info("Staff %s created referral for case %s.", user["id"], summary_id)
    return jsonify(
        {
            "success": True,
            "message": "Referral created successfully.",
            "data": referral,
        }
    ), 201


@conversation_bp.patch(
    "/flagged-conversations/<int:summary_id>/referrals/<int:referral_id>/status"
)
def update_referral_status(summary_id: int, referral_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        referral = update_staff_referral_status(
            user,
            summary_id,
            referral_id,
            str(payload.get("status", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception(
            "Failed to update referral %s for case %s.",
            referral_id,
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info(
        "Staff %s updated referral %s for case %s.",
        user["id"],
        referral_id,
        summary_id,
    )
    return jsonify(
        {
            "success": True,
            "message": "Referral status updated successfully.",
            "data": referral,
        }
    ), 200


@conversation_bp.post(
    "/flagged-conversations/<int:summary_id>/referrals/<int:referral_id>/notes"
)
def add_referral_note(summary_id: int, referral_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        referral = add_staff_referral_note(
            user,
            summary_id,
            referral_id,
            str(payload.get("note_text", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception(
            "Failed to add note to referral %s for case %s.",
            referral_id,
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info(
        "Staff %s added note to referral %s for case %s.",
        user["id"],
        referral_id,
        summary_id,
    )
    return jsonify(
        {
            "success": True,
            "message": "Referral note added successfully.",
            "data": referral,
        }
    ), 201


@conversation_bp.get("/flagged-conversations/<int:summary_id>/interventions")
def interventions(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error
    try:
        items = list_staff_interventions(summary_id)
        return jsonify(
            {
                "success": True,
                "message": "Interventions retrieved successfully.",
                "data": {"items": items},
            }
        ), 200
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except Exception:
        logger.exception("Failed to retrieve interventions for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500


@conversation_bp.post("/flagged-conversations/<int:summary_id>/interventions")
def create_intervention(summary_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        intervention = create_staff_intervention(
            user,
            summary_id,
            str(payload.get("intervention_type", "")),
            str(payload.get("objective", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception("Failed to create intervention for case %s.", summary_id)
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info("Staff %s created intervention for case %s.", user["id"], summary_id)
    return jsonify(
        {
            "success": True,
            "message": "Intervention created successfully.",
            "data": intervention,
        }
    ), 201


@conversation_bp.patch(
    "/flagged-conversations/<int:summary_id>/interventions/<int:intervention_id>/progress"
)
def update_intervention_progress(summary_id: int, intervention_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        intervention = update_staff_intervention_progress(
            user,
            summary_id,
            intervention_id,
            str(payload.get("progress_status", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception(
            "Failed to update intervention %s for case %s.",
            intervention_id,
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info(
        "Staff %s updated intervention %s for case %s.",
        user["id"],
        intervention_id,
        summary_id,
    )
    return jsonify(
        {
            "success": True,
            "message": "Intervention progress updated successfully.",
            "data": intervention,
        }
    ), 200


@conversation_bp.patch(
    "/flagged-conversations/<int:summary_id>/interventions/<int:intervention_id>/outcome"
)
def record_intervention_outcome(summary_id: int, intervention_id: int):
    user, error = require_role("staff")
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    _, access_error = _authorized_flagged_case_or_not_found(user, summary_id)
    if access_error:
        return access_error

    try:
        intervention = record_staff_intervention_outcome(
            user,
            summary_id,
            intervention_id,
            str(payload.get("outcome", "")),
        )
    except LookupError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 404
    except ValueError as error:
        return jsonify(
            {
                "success": False,
                "message": str(error),
                "errors": None,
            }
        ), 400
    except Exception:
        logger.exception(
            "Failed to record outcome for intervention %s in case %s.",
            intervention_id,
            summary_id,
        )
        return jsonify(
            {
                "success": False,
                "message": "Internal server error.",
                "errors": None,
            }
        ), 500

    logger.info(
        "Staff %s recorded outcome for intervention %s in case %s.",
        user["id"],
        intervention_id,
        summary_id,
    )
    return jsonify(
        {
            "success": True,
            "message": "Intervention outcome recorded successfully.",
            "data": intervention,
        }
    ), 200
