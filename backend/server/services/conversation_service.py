from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Final

from ..db import (
    current_time,
    fetch_account_by_id,
    discard_active_conversation_summary,
    ensure_active_conversation_summary,
    ensure_pending_escalation,
    finalize_active_conversation_summary,
    mark_active_conversation_escalated,
    mark_active_conversation_for_staff_review as mark_active_summary_for_staff_review,
    fetch_open_conversation_case,
    get_staff_by_program,
    get_dashboard_stats,
    get_student_by_id,
    fetch_flagged_conversation,
    fetch_flagged_conversation_transcript,
    fetch_staff_inbox_summary,
    list_flagged_conversations,
    list_staff_flagged_case_summaries,
    list_staff_inbox_summaries,
    list_staff_reviewed_case_history as list_staff_reviewed_case_history_rows,
    list_conversation_summaries_for_programs,
    list_conversation_finalizations_for_analytics,
    list_escalations_for_analytics,
    list_flagged_case_confidentiality_for_analytics,
    list_flagged_case_escalations_for_analytics,
    list_flagged_case_interventions_for_analytics,
    list_flagged_case_referrals_for_analytics,
    list_flagged_case_statuses_for_analytics,
    list_escalations_for_programs,
    list_chatbot_inquiries_for_analytics,
    list_chatbot_feedback_for_programs,
    list_inquiries_for_programs,
    mark_escalation_reviewed,
    save_conversation_summary,
    refresh_open_conversation_summary,
    save_escalation,
    save_inquiry,
    save_notification,
    save_flagged_conversation_transcript,
)

from . import summary_service
from .conversation_history import summary_conversation_evidence
from .conversation_history import transcript_conversation_evidence

logger = logging.getLogger(__name__)

ESCALATION_PENDING: Final[str] = "pending"
INQUIRY_TYPE_AI_CHAT: Final[str] = "ai_chat"
HIGH_RISK_NOTIFICATION_TITLE: Final[str] = "High-risk student conversation detected."
HIGH_RISK_NOTIFICATION_MESSAGE: Final[str] = (
    "Critical priority: a high-risk student conversation requires immediate "
    "Guidance Office review."
)
ACTIVE_CONVERSATION_TYPE: Final[str] = "active"
CASE_PRIORITY_CRITICAL: Final[str] = "critical"
CASE_PRIORITY_HIGH: Final[str] = "high"
CASE_PRIORITY_MEDIUM: Final[str] = "medium"
CASE_PRIORITY_LOW: Final[str] = "low"
def _parse_analytics_filter_date(value: object, field_name: str) -> date | None:
    if value is None or not str(value).strip():
        return None

    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}.") from exc


def _analytics_date_range(
    start_date: object,
    end_date: object,
) -> tuple[date | None, date | None, datetime | None, datetime | None]:
    start = _parse_analytics_filter_date(start_date, "start date")
    end = _parse_analytics_filter_date(end_date, "end date")

    if start and end and start > end:
        raise ValueError("Start date must not be after end date.")

    start_at = datetime.combine(start, time.min) if start else None
    end_at = (
        datetime.combine(end + timedelta(days=1), time.min)
        if end
        else None
    )
    return start, end, start_at, end_at


def _analytics_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _message_volume(rows: list[dict]) -> dict[str, list[dict]]:
    daily: Counter[str] = Counter()
    weekly: Counter[str] = Counter()
    monthly: Counter[str] = Counter()

    for row in rows:
        created_at = _analytics_datetime(row["created_at"])
        daily[created_at.date().isoformat()] += 1
        iso_year, iso_week, _ = created_at.isocalendar()
        weekly[f"{iso_year}-W{iso_week:02d}"] += 1
        monthly[created_at.strftime("%Y-%m")] += 1

    def rows_for(counter: Counter[str], key: str) -> list[dict]:
        return [
            {key: label, "count": count}
            for label, count in sorted(counter.items())
        ]

    return {
        "daily": rows_for(daily, "date"),
        "weekly": rows_for(weekly, "week"),
        "monthly": rows_for(monthly, "month"),
    }


def get_chatbot_analytics_service(
    staff_account: dict,
    *,
    start_date: object = None,
    end_date: object = None,
) -> dict:
    """Return aggregate-only analytics for the staff member's program scope."""
    start, end, start_at, end_at = _analytics_date_range(
        start_date,
        end_date,
    )
    programs = sorted(_staff_assigned_programs(staff_account))
    inquiries = list_chatbot_inquiries_for_analytics(start_at, end_at, programs)
    finalizations = list_conversation_finalizations_for_analytics(
        start_at,
        end_at,
        programs,
    )
    escalations = list_escalations_for_analytics(start_at, end_at, programs)

    emotion_results = Counter(
        str(inquiry.get("emotion_result") or "").strip()
        for inquiry in inquiries
    )
    emotion_results.pop("", None)
    finalized_lengths = [
        int(finalization["total_messages"])
        for finalization in finalizations
    ]

    return {
        "filters": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
        },
        "total_chatbot_messages": len(inquiries),
        "message_volume": _message_volume(inquiries),
        "conversation_finalization_count": len(finalizations),
        "escalation_count": len(escalations),
        "persisted_emotion_result_distribution": [
            {"emotion_result": label, "count": count}
            for label, count in sorted(emotion_results.items())
        ],
        "average_finalized_conversation_length": (
            round(sum(finalized_lengths) / len(finalized_lengths), 2)
            if finalized_lengths
            else None
        ),
    }


def get_flagged_case_analytics_service(
    staff_account: dict,
    *,
    start_date: object = None,
    end_date: object = None,
) -> dict:
    """Return aggregate-only flagged-case analytics for the staff program scope."""
    start, end, start_at, end_at = _analytics_date_range(
        start_date,
        end_date,
    )
    programs = sorted(_staff_assigned_programs(staff_account))
    case_statuses = list_flagged_case_statuses_for_analytics(
        start_at,
        end_at,
        programs,
    )
    referrals = list_flagged_case_referrals_for_analytics(
        start_at,
        end_at,
        programs,
    )
    interventions = list_flagged_case_interventions_for_analytics(
        start_at,
        end_at,
        programs,
    )
    confidentiality_records = list_flagged_case_confidentiality_for_analytics(
        start_at,
        end_at,
        programs,
    )
    escalations = list_flagged_case_escalations_for_analytics(
        start_at,
        end_at,
        programs,
    )

    status_distribution = Counter(
        str(case.get("status") or "").strip()
        for case in case_statuses
    )
    status_distribution.pop("", None)

    return {
        "filters": {
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
        },
        "total_flagged_cases": len(case_statuses),
        "pending_flagged_case_reviews": status_distribution[ESCALATION_PENDING],
        "reviewed_flagged_cases": status_distribution["reviewed"],
        "referral_count": len(referrals),
        "intervention_count": len(interventions),
        "current_confidential_case_count": sum(
            str(record.get("confidentiality_status") or "").strip().lower()
            == "confidential"
            for record in confidentiality_records
        ),
        "escalation_trends": _message_volume(escalations),
        "persisted_case_status_distribution": [
            {"status": status, "count": count}
            for status, count in sorted(status_distribution.items())
        ],
    }


def get_staff_dashboard_stats(staff_account: dict) -> dict:
    """Return dashboard counters limited to the staff member's program scope."""
    return get_dashboard_stats(sorted(_staff_assigned_programs(staff_account)))

_INQUIRY_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "inquiry_type",
    "emotion_result",
    "escalated",
    "appointment_recommended",
    "created_at",
)
_SUMMARY_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "primary_concern",
    "conversation_type",
    "emotion_results",
    "flagged_status",
    "appointment_recommendation",
    "recommendations",
    "suggested_intervention",
    "language_used",
    "total_messages",
    "summary",
    "created_at",
)
_ESCALATION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "status",
    "intervention_notes",
    "created_at",
    "resolved_at",
)
_FLAGGED_CONVERSATION_FIELDS: Final[tuple[str, ...]] = (
    "id",
    "primary_concern",
    "conversation_type",
    "emotion_results",
    "appointment_recommendation",
    "recommendations",
    "suggested_intervention",
    "language_used",
    "total_messages",
    "summary",
    "created_at",
    "escalation_status",
    "escalation_reason",
    "reviewed_at",
)
_STAFF_INBOX_FIELDS: Final[tuple[str, ...]] = (
    "summary_id",
    "student_name",
    "student_number",
    "program",
    "primary_concern",
    "emotion_results",
    "flagged_status",
    "case_priority",
    "review_status",
    "created_at",
    "summary_preview",
    "has_referral",
    "has_intervention",
)
_STAFF_INBOX_DETAIL_FIELDS: Final[tuple[str, ...]] = (
    *_STAFF_INBOX_FIELDS,
    "summary",
    "recommendations",
    "suggested_intervention",
    "language_used",
    "total_messages",
    "escalation_status",
    "escalation_reason",
)
_STAFF_CASE_HISTORY_FIELDS: Final[tuple[str, ...]] = (
    "summary_id",
    "student_name",
    "student_number",
    "program",
    "primary_concern",
    "emotion_results",
    "flagged_status",
    "review_status",
    "created_at",
    "reviewed_at",
    "summary_preview",
)
_STAFF_CHATBOT_FEEDBACK_FIELDS: Final[tuple[str, ...]] = (
    "feedback_id",
    "conversation_summary_id",
    "student_name",
    "student_number",
    "program",
    "category",
    "comment",
    "response_context",
    "created_at",
)


def _project_fields(row: dict, fields: tuple[str, ...]) -> dict:
    return {field: row.get(field) for field in fields}


def _staff_assigned_programs(staff_account: dict) -> set[str]:
    account = fetch_account_by_id(int(staff_account["id"]), role="staff")
    if not account:
        return set()

    programs = account.get("assigned_programs")
    if isinstance(programs, bytes):
        try:
            programs = programs.decode("utf-8")
        except UnicodeDecodeError:
            return set()
    if isinstance(programs, str):
        try:
            programs = json.loads(programs)
        except json.JSONDecodeError:
            return set()
    if not isinstance(programs, list):
        return set()
    return {
        str(program).strip().casefold()
        for program in programs
        if str(program).strip()
    }


def _inbox_review_status(row: dict) -> str:
    escalation_status = str(row.get("escalation_status") or "").strip().lower()
    if escalation_status in {"pending", "reviewed"}:
        return escalation_status
    if str(row.get("conversation_type") or "").strip().lower() == ACTIVE_CONVERSATION_TYPE:
        return "active"
    return "routine"


def _summary_preview(value: object) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return (
            "An AI summary could not be generated. Review the available case "
            "metadata and contact the student through the approved Guidance Office process."
        )
    return text[:240] + ("..." if len(text) > 240 else "")


def _case_priority(row: dict) -> str:
    """Derive staff-only urgency from persisted safety and review state."""
    if bool(row.get("flagged_status")):
        safety_metadata = " ".join(
            str(row.get(key) or "")
            for key in ("escalation_reason", "primary_concern")
        ).lower()
        if "ai safety escalation" in safety_metadata:
            return CASE_PRIORITY_CRITICAL
        return CASE_PRIORITY_HIGH
    if str(row.get("conversation_type") or "").strip().lower() == ACTIVE_CONVERSATION_TYPE:
        return CASE_PRIORITY_MEDIUM
    return CASE_PRIORITY_LOW


def _project_staff_inbox_row(row: dict, *, detail: bool = False) -> dict:
    projected = {
        "summary_id": row.get("summary_id"),
        "student_name": row.get("student_name"),
        "student_number": row.get("student_number"),
        "program": row.get("program"),
        "primary_concern": row.get("primary_concern"),
        "conversation_type": row.get("conversation_type"),
        "emotion_results": row.get("emotion_results"),
        "flagged_status": bool(row.get("flagged_status")),
        "case_priority": _case_priority(row),
        "review_status": _inbox_review_status(row),
        "created_at": row.get("created_at"),
        "summary_preview": _summary_preview(row.get("summary")),
        "has_referral": bool(row.get("has_referral")),
        "has_intervention": bool(row.get("has_intervention")),
    }
    if detail:
        projected.update(
            {
                "summary": row.get("summary") or (
                    "An AI summary could not be generated. Review the available case "
                    "metadata and contact the student through the approved Guidance Office process."
                ),
                "recommendations": row.get("recommendations"),
                "suggested_intervention": row.get("suggested_intervention"),
                "language_used": row.get("language_used"),
                "total_messages": row.get("total_messages"),
                "escalation_status": row.get("escalation_status"),
                "escalation_reason": row.get("escalation_reason"),
            }
        )
    return _project_fields(
        projected,
        _STAFF_INBOX_DETAIL_FIELDS if detail else _STAFF_INBOX_FIELDS,
    )


def list_staff_inbox_items(staff_account: dict) -> list[dict]:
    """Return current active/finalized Inbox items within the staff program scope."""
    programs = _staff_assigned_programs(staff_account)
    if not programs:
        return []

    rows = list_staff_inbox_summaries(sorted(programs))
    # The database query groups by account; preserve a service-owned final guard
    # in case legacy data or a future join ever returns a duplicate summary row.
    unique: dict[tuple[object, str], dict] = {}
    for row in rows:
        student_key = row.get("student_account_id") or row.get("student_number")
        if not student_key:
            continue
        item_kind = (
            "active"
            if str(row.get("conversation_type") or "").strip().lower()
            == ACTIVE_CONVERSATION_TYPE
            else "current"
        )
        unique.setdefault((student_key, item_kind), row)
    return [_project_staff_inbox_row(row) for row in unique.values()]


def list_staff_flagged_case_items(staff_account: dict) -> list[dict]:
    """Return all pending and reviewed flagged cases in the staff program scope."""
    programs = _staff_assigned_programs(staff_account)
    if not programs:
        return []
    return [
        _project_staff_inbox_row(row)
        for row in list_staff_flagged_case_summaries(sorted(programs))
    ]


def get_staff_inbox_item(staff_account: dict, summary_id: int) -> dict | None:
    row = fetch_staff_inbox_summary(summary_id)
    if row is None:
        return None
    programs = _staff_assigned_programs(staff_account)
    if str(row.get("program") or "").strip().casefold() not in programs:
        return None
    return _project_staff_inbox_row(row, detail=True)


def save_flagged_case_transcript(
    summary_id: int,
    conversation: object,
) -> None:
    """Persist server-owned evidence only after a case has been flagged."""
    transcript = transcript_conversation_evidence(conversation)
    if transcript:
        save_flagged_conversation_transcript(summary_id, transcript)


def get_staff_flagged_case_transcript(
    staff_account: dict,
    summary_id: int,
) -> list[dict[str, str]] | None:
    """Return raw messages only to staff authorized for this flagged case."""
    item = get_staff_inbox_item(staff_account, summary_id)
    if item is None or not item.get("flagged_status"):
        return None

    record = fetch_flagged_conversation_transcript(summary_id)
    if record is None:
        return []

    try:
        entries = json.loads(str(record.get("transcript_json") or "[]"))
    except (TypeError, ValueError):
        logger.error("Stored flagged-case transcript could not be decoded.")
        return []

    if not isinstance(entries, list):
        return []

    projected: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip().lower()
        content = entry.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        text = content.strip()
        if text:
            projected.append(
                {
                    "role": "student" if role == "user" else "assistant",
                    "content": text,
                }
            )
    return projected


def list_staff_reviewed_case_history(
    staff_account: dict,
    summary_id: int,
) -> list[dict] | None:
    """Return privacy-safe reviewed cases for one authorized student's history."""
    if get_staff_inbox_item(staff_account, summary_id) is None:
        return None

    programs = _staff_assigned_programs(staff_account)
    rows = list_staff_reviewed_case_history_rows(summary_id, sorted(programs))
    return [
        _project_fields(
            {
                "summary_id": row.get("summary_id"),
                "student_name": row.get("student_name"),
                "student_number": row.get("student_number"),
                "program": row.get("program"),
                "primary_concern": row.get("primary_concern"),
                "emotion_results": row.get("emotion_results"),
                "flagged_status": bool(row.get("flagged_status")),
                "review_status": _inbox_review_status(row),
                "created_at": row.get("created_at"),
                "reviewed_at": row.get("reviewed_at"),
                "summary_preview": _summary_preview(row.get("summary")),
            },
            _STAFF_CASE_HISTORY_FIELDS,
        )
        for row in rows
    ]


def list_staff_inquiries(staff_account: dict) -> list[dict]:
    """Return the staff-permitted inquiry history without account linkage data."""
    programs = _staff_assigned_programs(staff_account)
    return [
        _project_fields(row, _INQUIRY_FIELDS)
        for row in list_inquiries_for_programs(sorted(programs))
    ]


def list_staff_conversation_summaries(staff_account: dict) -> list[dict]:
    """Return the staff-permitted counselor summaries without account linkage data."""
    programs = _staff_assigned_programs(staff_account)
    return [
        _project_fields(row, _SUMMARY_FIELDS)
        for row in list_conversation_summaries_for_programs(sorted(programs))
    ]


def list_staff_escalations(staff_account: dict) -> list[dict]:
    """Return the staff-permitted escalations without internal linkage data."""
    programs = _staff_assigned_programs(staff_account)
    return [
        _project_fields(row, _ESCALATION_FIELDS)
        for row in list_escalations_for_programs(sorted(programs))
    ]


def list_staff_chatbot_feedback(staff_account: dict) -> list[dict]:
    """Return privacy-safe feedback for students in the counselor's programs."""
    programs = _staff_assigned_programs(staff_account)
    return [
        _project_fields(row, _STAFF_CHATBOT_FEEDBACK_FIELDS)
        for row in list_chatbot_feedback_for_programs(sorted(programs))
    ]


def summarize_staff_chatbot_feedback(items: list[dict]) -> dict:
    """Build improvement signals from privacy-projected feedback only."""
    helpful_categories = {"helpful", "clear_useful"}
    category_counts: dict[str, int] = {}
    pattern_counts: dict[tuple[str, str], int] = {}

    for item in items:
        category = str(item.get("category") or "other")
        category_counts[category] = category_counts.get(category, 0) + 1
        if category not in helpful_categories:
            response_context = str(item.get("response_context") or "uncategorized")
            key = (category, response_context)
            pattern_counts[key] = pattern_counts.get(key, 0) + 1

    categories = sorted(
        (
            {"category": category, "count": count}
            for category, count in category_counts.items()
        ),
        key=lambda row: (-row["count"], row["category"]),
    )
    patterns = sorted(
        (
            {
                "category": category,
                "response_context": response_context,
                "count": count,
            }
            for (category, response_context), count in pattern_counts.items()
        ),
        key=lambda row: (-row["count"], row["category"], row["response_context"]),
    )
    return {
        "total": len(items),
        "needs_attention": sum(
            count
            for category, count in category_counts.items()
            if category not in helpful_categories
        ),
        "safety_concerns": category_counts.get("safety_concern", 0),
        "categories": categories,
        "patterns": patterns[:3],
    }


def determine_escalation_reason(
    *,
    escalated: bool,
    normalized_emotion: str | None,
) -> str | None:
    """Return a reason only for an explicit SafetyService escalation."""
    del normalized_emotion
    if escalated:
        return "AI safety escalation."
    return None


def list_staff_flagged_conversations() -> list[dict]:
    """Return staff-visible pending flagged conversation summaries only."""
    return [
        _project_fields(row, _FLAGGED_CONVERSATION_FIELDS)
        for row in list_flagged_conversations()
        if str(row.get("escalation_status") or "").strip().lower()
        == ESCALATION_PENDING
    ]


def get_staff_flagged_conversation(summary_id: int) -> dict | None:
    """Return one staff-visible flagged conversation summary."""
    row = fetch_flagged_conversation(summary_id)
    if row is None:
        return None

    return _project_fields(row, _FLAGGED_CONVERSATION_FIELDS)


def mark_staff_flagged_conversation_reviewed(summary_id: int) -> dict | None:
    """Mark a pending flagged conversation as reviewed without altering history."""
    conversation = get_staff_flagged_conversation(summary_id)
    if conversation is None:
        return None

    if conversation["escalation_status"] == "reviewed":
        return conversation
    if conversation["escalation_status"] != ESCALATION_PENDING:
        raise ValueError("Flagged conversation cannot be marked as reviewed.")
    if not mark_escalation_reviewed(summary_id):
        raise ValueError("Flagged conversation cannot be marked as reviewed.")

    return get_staff_flagged_conversation(summary_id)


def record_chat_inquiry(
    *,
    account_id: int,
    emotion: str,
    escalated: bool,
) -> None:
    """Persist the metadata generated by a successful chatbot response."""
    save_inquiry(
        {
            "account_id": account_id,
            "inquiry_type": INQUIRY_TYPE_AI_CHAT,
            "emotion_result": emotion,
            "escalated": escalated,
            "appointment_recommended": False,
            "created_at": current_time(),
        }
    )


def ensure_staff_visible_active_conversation(account_id: int) -> int:
    """Create or reuse the Inbox placeholder after the first stored exchange."""
    return ensure_active_conversation_summary(account_id)


def mark_active_conversation_for_immediate_review(
    summary_id: int,
    account_id: int,
    escalation_reason: str,
) -> None:
    """Expose an active safety escalation to authorized staff without a transcript."""
    if not mark_active_conversation_escalated(summary_id, account_id):
        return
    if ensure_pending_escalation(account_id, summary_id, escalation_reason):
        _notify_high_risk_conversation_safely(account_id)


def mark_active_conversation_for_staff_review(
    summary_id: int,
    account_id: int,
    review_reason: str,
) -> None:
    """Expose an active warning-sign case without sending a high-risk alert."""
    if not mark_active_summary_for_staff_review(summary_id, account_id):
        return
    ensure_pending_escalation(account_id, summary_id, review_reason)


def should_escalate_conversation(
    *,
    escalated: bool,
    normalized_emotion: str | None,
) -> bool:
    """Escalate only for explicit safety risk, never an emotion label alone."""
    del normalized_emotion
    return bool(escalated)


def _meaningful_summary_evidence(conversation: object) -> list[dict[str, str]]:
    """Return canonical transient evidence only when a student actually spoke."""
    return summary_conversation_evidence(conversation)


def _appointment_context(appointment: object) -> dict[str, str] | None:
    if not isinstance(appointment, dict):
        return None

    context = {
        key: str(appointment.get(key) or "").strip()
        for key in ("category", "preferred_date", "preferred_time_slot")
    }
    return context if all(context.values()) else None


def _save_escalation(
    summary_id: int,
    account_id: int,
    escalation_reason: str,
) -> None:
    save_escalation(
        {
            "account_id": account_id,
            "summary_id": summary_id,
            "status": ESCALATION_PENDING,
            "escalation_reason": escalation_reason,
            "created_at": current_time(),
        }
    )


def _notify_high_risk_conversation_safely(account_id: int) -> None:
    """Notify the student's routed counselor without affecting case persistence."""
    try:
        student = get_student_by_id(account_id) or {}
        program = str(student.get("program") or "").strip()
        counselor = get_staff_by_program(program) if program else None
        if not counselor:
            return
        save_notification(
            {
                "recipient_account_id": int(counselor["id"]),
                "title": HIGH_RISK_NOTIFICATION_TITLE,
                "message": HIGH_RISK_NOTIFICATION_MESSAGE,
                "type": "high_risk_conversation",
                "created_at": current_time(),
            }
        )
    except Exception:
        logger.exception("Failed to persist high-risk conversation notification.")


def finalize_conversation(
    *,
    user: dict,
    conversation: list[dict],
    topic: str,
    language: str,
    emotion: str,
    flagged: bool,
    review_only: bool = False,
    escalation_reason: str | None = None,
    appointment: object = None,
    active_summary_id: int | None = None,
) -> dict:
    evidence = _meaningful_summary_evidence(conversation)
    appointment_context = _appointment_context(appointment)
    if not evidence and not appointment_context:
        if active_summary_id:
            discard_active_conversation_summary(active_summary_id, user["id"])
        logger.info("Conversation finalization skipped (no student-authored evidence).")
        return {
            "success": True,
            "status": "skipped",
            "reason": "no_meaningful_student_message",
            "summary_id": None,
            "student_message_count": 0,
            "assistant_message_count": 0,
        }

    if active_summary_id:
        logger.info("Active conversation finalization started (flagged=%s).", flagged)
        summary = summary_service.generate_summary(
            student_name=user["full_name"],
            conversation=evidence,
            topic=topic,
            language=language,
            emotion=emotion,
            flagged=flagged,
            review_only=review_only,
            appointment=appointment_context,
        )
        summary_payload = {
            "account_id": user["id"],
            "primary_concern": summary.primary_concern,
            "conversation_type": summary.conversation_type,
            "emotion_results": summary.emotion,
            "flagged_status": summary.flagged,
            "appointment_recommendation": summary.appointment_recommendation,
            "recommendations": summary.recommendations,
            "suggested_intervention": summary.suggested_intervention,
            "language_used": summary.language,
            "total_messages": summary.total_messages,
            "summary": summary.summary,
            "created_at": current_time(),
        }
        if finalize_active_conversation_summary(
            active_summary_id,
            user["id"],
            summary_payload,
        ):
            if summary.flagged and ensure_pending_escalation(
                user["id"],
                active_summary_id,
                escalation_reason
                or determine_escalation_reason(
                    escalated=True,
                    normalized_emotion=summary.emotion,
                )
                or "AI safety escalation.",
            ) and not review_only:
                _notify_high_risk_conversation_safely(user["id"])
            if summary.flagged and not flagged:
                save_flagged_case_transcript(active_summary_id, evidence)
            logger.info("Active conversation finalization completed.")
            return {
                "success": True,
                "summary_id": active_summary_id,
                "status": "saved",
                "student_message_count": sum(item["role"] == "user" for item in evidence),
                "assistant_message_count": sum(item["role"] == "assistant" for item in evidence),
                "appointment_recorded": appointment_context is not None,
            }

    open_case = fetch_open_conversation_case(user["id"]) if flagged else None
    if open_case is not None:
        refreshed_summary = summary_service.refresh_open_case_summary(
            prior_summary=open_case.get("summary"),
            conversation=evidence,
        )
        previous_total = int(open_case.get("total_messages") or 0)
        updated = refresh_open_conversation_summary(
            int(open_case["summary_id"]),
            refreshed_summary,
            previous_total + len(evidence),
        )
        if not updated:
            raise RuntimeError("Open flagged case could not be refreshed.")

        if active_summary_id and int(open_case["summary_id"]) != active_summary_id:
            discard_active_conversation_summary(active_summary_id, user["id"])

        logger.info("Open flagged conversation summary refreshed.")
        return {
            "success": True,
            "summary_id": int(open_case["summary_id"]),
            "status": "updated_open_case",
            "student_message_count": sum(item["role"] == "user" for item in evidence),
            "assistant_message_count": sum(item["role"] == "assistant" for item in evidence),
            "appointment_recorded": appointment_context is not None,
        }

    logger.info("Conversation finalization started (flagged=%s).", flagged)
    summary = summary_service.generate_summary(
        student_name=user["full_name"],
        conversation=evidence,
        topic=topic,
        language=language,
        emotion=emotion,
        flagged=flagged,
        review_only=review_only,
        appointment=appointment_context,
    )

    summary_payload = {
        "account_id": user["id"],
        "primary_concern": summary.primary_concern,
        "conversation_type": summary.conversation_type,
        "emotion_results": summary.emotion,
        "flagged_status": summary.flagged,
        "appointment_recommendation": summary.appointment_recommendation,
        "recommendations": summary.recommendations,
        "suggested_intervention": summary.suggested_intervention,
        "language_used": summary.language,
        "total_messages": summary.total_messages,
        "summary": summary.summary,
        "created_at": current_time(),
    }
    summary_id = save_conversation_summary(summary_payload)

    if summary.flagged:
        _save_escalation(
            summary_id,
            user["id"],
            escalation_reason
            or determine_escalation_reason(
                escalated=True,
                normalized_emotion=summary.emotion,
            )
            or "AI safety escalation.",
        )
        if not review_only:
            _notify_high_risk_conversation_safely(user["id"])
        if not flagged:
            save_flagged_case_transcript(summary_id, evidence)

    logger.info("Conversation finalization completed.")

    return {
        "success": True,
        "summary_id": summary_id,
        "status": "saved",
        "student_message_count": sum(
            item["role"] == "user" for item in evidence
        ),
        "assistant_message_count": sum(
            item["role"] == "assistant" for item in evidence
        ),
        "appointment_recorded": appointment_context is not None,
    }
