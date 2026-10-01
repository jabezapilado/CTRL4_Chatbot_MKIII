"""Safe in-memory normalization for browser conversation history.

Browser clients from earlier releases send ``{from, text}`` entries while the
prompt pipeline uses ``{role, content}``.  This module defines the latter as
the canonical, transient shape without persisting or exposing transcripts.
"""

from __future__ import annotations

from typing import Final


# Keep enough active-session continuity for a longer guidance conversation
# without increasing the maximum history text budget (100 * 480 = 48,000
# characters, the same upper bound as the previous 24 * 2,000 limit).
# This state remains server-session-scoped and is cleared on finalization,
# logout, expiry, or a device replacement.
MAX_HISTORY_MESSAGES: Final[int] = 100
MAX_HISTORY_MESSAGE_CHARACTERS: Final[int] = 480

_ROLE_ALIASES: Final[dict[str, str]] = {
    "user": "user",
    "student": "user",
    "assistant": "assistant",
    "bot": "assistant",
}


def normalize_conversation_history(entries: object) -> list[dict[str, str]]:
    """Return bounded valid history in the canonical ``role``/``content`` form.

    Malformed entries and blank messages are ignored.  The original browser
    payload is never mutated, stored, or logged.
    """

    if not isinstance(entries, list):
        return []

    normalized: list[dict[str, str]] = []
    for entry in entries[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(entry, dict):
            continue

        raw_role = entry.get("role", entry.get("from", ""))
        role = _ROLE_ALIASES.get(str(raw_role).strip().lower())
        if role is None:
            continue

        raw_content = entry.get("content", entry.get("text", ""))
        if not isinstance(raw_content, str):
            continue

        content = raw_content.strip()
        if not content:
            continue

        normalized.append(
            {
                "role": role,
                "content": content[:MAX_HISTORY_MESSAGE_CHARACTERS],
            }
        )

    return normalized


def summary_conversation_evidence(entries: object) -> list[dict[str, str]]:
    """Return canonical evidence beginning with the first student message."""
    evidence: list[dict[str, str]] = []
    has_student_message = False
    for item in normalize_conversation_history(entries):
        if item["role"] == "user":
            has_student_message = True
            evidence.append(item)
        elif has_student_message:
            evidence.append(item)
    return evidence


def transcript_conversation_evidence(entries: object) -> list[dict[str, str]]:
    """Return the retained raw transcript beginning with a student message.

    This is intentionally separate from prompt/summary normalization: it keeps
    the original server-captured message text for an authorized flagged-case
    review while still bounding the number of retained exchanges.
    """
    if not isinstance(entries, list):
        return []

    evidence: list[dict[str, str]] = []
    has_student_message = False
    for item in entries[-MAX_HISTORY_MESSAGES:]:
        if not isinstance(item, dict):
            continue
        raw_role = item.get("role", item.get("from", ""))
        role = _ROLE_ALIASES.get(str(raw_role).strip().lower())
        content = item.get("content", item.get("text", ""))
        if role is None or not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        if role == "user":
            has_student_message = True
        if has_student_message:
            evidence.append({"role": role, "content": text})
    return evidence


__all__ = [
    "MAX_HISTORY_MESSAGES",
    "MAX_HISTORY_MESSAGE_CHARACTERS",
    "normalize_conversation_history",
    "summary_conversation_evidence",
    "transcript_conversation_evidence",
]
