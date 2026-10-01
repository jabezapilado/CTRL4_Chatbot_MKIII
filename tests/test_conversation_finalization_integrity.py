from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from flask import Flask

from backend.server import db
from backend.server.routes.appointment_routes import appointment_bp
from backend.server.routes.chatbot_routes import chatbot_bp
from backend.server.services import conversation_service
from backend.server.services.summary_service import SummaryService
from backend.server.services.transient_chat_service import TransientChatService


class _Cache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key: str):  # type: ignore[no-untyped-def]
        return self.values.get(key)

    def set(self, key: str, value: object, timeout: int) -> None:
        self.values[key] = value

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


class _FailedLlm:
    def generate(self, _prompt: str):  # type: ignore[no-untyped-def]
        return SimpleNamespace(success=False, error="unavailable")


class _CapturingLlm:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str):  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        return SimpleNamespace(success=True, text="Grounded case summary.")


class ConversationFinalizationIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.app.secret_key = "finalization-integrity"
        self.app.register_blueprint(chatbot_bp)
        self.app.register_blueprint(appointment_bp)

    def _client(self, account_id: int = 1):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["hau_user"] = {
                "id": account_id,
                "email": f"student{account_id}@example.test",
                "full_name": f"Student {account_id}",
                "role": "student",
            }
            session["student_terms_accepted"] = True
        return client

    def test_assistant_greeting_only_skips_summary_and_persistence(self) -> None:
        greeting = [{"from": "bot", "text": "Welcome to CTRL4."}]
        with patch.object(
            conversation_service.summary_service,
            "generate_summary",
        ) as generate, patch.object(
            conversation_service,
            "save_conversation_summary",
        ) as save:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=greeting,
                topic="general",
                language="unknown",
                emotion="neutral",
                flagged=False,
            )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["student_message_count"], 0)
        generate.assert_not_called()
        save.assert_not_called()

    def test_empty_finalization_discards_its_active_placeholder(self) -> None:
        with patch.object(
            conversation_service,
            "discard_active_conversation_summary",
            return_value=True,
        ) as discard:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[],
                topic="general",
                language="unknown",
                emotion="neutral",
                flagged=False,
                active_summary_id=81,
            )

        self.assertEqual(result["status"], "skipped")
        discard.assert_called_once_with(81, 1)

    def test_review_only_flag_creates_case_without_high_risk_notification(self) -> None:
        with patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=SimpleNamespace(
                primary_concern="general",
                conversation_type="general",
                emotion="negative",
                flagged=True,
                appointment_recommendation=False,
                recommendations="Guidance Office review is recommended.",
                suggested_intervention="Guidance Office review is recommended.",
                language="english",
                total_messages=1,
                summary="The student reported a wellbeing concern.",
            ),
        ) as generate, patch.object(
            conversation_service,
            "save_conversation_summary",
            return_value=72,
        ), patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service,
            "save_escalation",
        ) as save_escalation, patch.object(
            conversation_service,
            "_notify_high_risk_conversation_safely",
        ) as notify:
            conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[{"from": "user", "text": "I feel empty."}],
                topic="general",
                language="english",
                emotion="negative",
                flagged=True,
                review_only=True,
            )

        self.assertTrue(generate.call_args.kwargs["review_only"])
        save_escalation.assert_called_once()
        notify.assert_not_called()

    def test_finalize_route_ignores_appointment_only_browser_payload(self) -> None:
        client = self._client()
        with patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.get_visible_history",
            return_value=[],
        ), patch(
            "backend.server.routes.chatbot_routes.finalize_conversation",
            return_value={"status": "skipped", "summary_id": None},
        ) as finalize, patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.clear",
        ) as clear:
            response = client.post(
                "/chat/finalize",
                json={
                    "conversation": [
                        {"from": "bot", "text": "Welcome"},
                        {"from": "bot", "text": "Appointment submitted"},
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["status"], "skipped")
        finalize.assert_called_once()
        self.assertEqual(finalize.call_args.kwargs["conversation"], [])
        clear.assert_called_once()

    def test_successful_appointment_records_only_summary_safe_session_metadata(self) -> None:
        client = self._client()
        payload = {
            "contact_number": "09171234567",
            "appointment_category": "Career / Schooling",
            "appointment_mode": "In-person",
            "preferred_date": "2026-08-08",
            "preferred_time_slot": "10:00 AM",
            "reason": "Private appointment reason",
        }
        with patch(
            "backend.server.routes.appointment_routes.create_student_appointment",
            return_value=52,
        ):
            response = client.post("/api/appointments", json=payload)

        self.assertEqual(response.status_code, 201)
        with client.session_transaction() as session:
            self.assertEqual(
                session["finalization_appointment"],
                {
                    "category": "Career / Schooling",
                    "preferred_date": "2026-08-08",
                    "preferred_time_slot": "10:00 AM",
                },
            )
            self.assertNotIn("Private appointment reason", str(session))

    def test_appointment_only_summary_is_deterministic_and_not_flagged(self) -> None:
        service = SummaryService(_FailedLlm())
        appointment = {
            "category": "Career / Schooling",
            "preferred_date": "2026-08-08",
            "preferred_time_slot": "10:00 AM",
        }

        summary = service.generate_summary(
            student_name="Student",
            conversation=[],
            topic="general",
            language="unknown",
            emotion="neutral",
            flagged=False,
            appointment=appointment,
        )

        self.assertEqual(summary.conversation_type, "appointment")
        self.assertFalse(summary.flagged)
        self.assertEqual(summary.total_messages, 0)
        self.assertIn("Career / Schooling", summary.summary)
        self.assertIn("No additional chatbot conversation occurred", summary.summary)
        for unsupported in ("anxiety", "stress", "counseling", "intervention"):
            self.assertNotIn(unsupported, summary.summary.casefold())

    def test_finalize_route_consumes_and_clears_appointment_metadata(self) -> None:
        client = self._client()
        appointment = {
            "category": "Career / Schooling",
            "preferred_date": "2026-08-08",
            "preferred_time_slot": "10:00 AM",
        }
        with client.session_transaction() as session:
            session["finalization_appointment"] = appointment

        with patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.get_visible_history",
            return_value=[],
        ), patch(
            "backend.server.routes.chatbot_routes.finalize_conversation",
            return_value={"status": "saved", "summary_id": 18},
        ) as finalize, patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.clear",
        ):
            response = client.post("/chat/finalize", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(finalize.call_args.kwargs["appointment"], appointment)
        with client.session_transaction() as session:
            self.assertNotIn("finalization_appointment", session)

    def test_real_student_message_is_the_only_summary_evidence(self) -> None:
        summary = SimpleNamespace(
            primary_concern="appointment",
            conversation_type="general",
            emotion="neutral",
            flagged=False,
            appointment_recommendation=False,
            recommendations="No immediate intervention is required.",
            suggested_intervention="No immediate intervention is required.",
            language="english",
            total_messages=2,
            summary="Student requested an appointment.",
        )
        evidence = [
            {"from": "bot", "text": "Welcome"},
            {"from": "user", "text": "I want to book an appointment."},
            {"from": "bot", "text": "I can help with that."},
        ]
        with patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=summary,
        ) as generate, patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service,
            "save_conversation_summary",
            return_value=17,
        ):
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=evidence,
                topic="appointment",
                language="english",
                emotion="neutral",
                flagged=False,
            )

        forwarded = generate.call_args.kwargs["conversation"]
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["student_message_count"], 1)
        self.assertEqual(result["assistant_message_count"], 1)
        self.assertEqual(
            forwarded,
            [
                {"role": "user", "content": "I want to book an appointment."},
                {"role": "assistant", "content": "I can help with that."},
            ],
        )

    def test_chat_and_appointment_summary_uses_only_confirmed_appointment_facts(self) -> None:
        llm = _CapturingLlm()
        service = SummaryService(llm)
        appointment = {
            "category": "Career / Schooling",
            "preferred_date": "2026-08-08",
            "preferred_time_slot": "10:00 AM",
        }

        service.generate_summary(
            student_name="Student",
            conversation=[{"from": "user", "text": "I want to book an appointment."}],
            topic="appointment",
            language="english",
            emotion="neutral",
            flagged=False,
            appointment=appointment,
        )

        self.assertIn("I want to book an appointment.", llm.prompts[0])
        self.assertIn("Career / Schooling", llm.prompts[0])
        self.assertIn("2026-08-08", llm.prompts[0])
        self.assertNotIn("Private appointment reason", llm.prompts[0])

    def test_empty_new_session_does_not_reuse_previous_account_evidence(self) -> None:
        cache = _Cache()
        transient = TransientChatService(cache=cache, timeout_seconds=60)
        transient.record_exchange("session-one", 1, [], "Real concern", "Reply")
        self.assertTrue(transient.get_visible_history("session-one", 1))
        self.assertEqual(transient.get_visible_history("session-two", 1), [])
        self.assertEqual(transient.get_visible_history("session-one", 2), [])

        with patch.object(conversation_service, "save_conversation_summary") as save:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[],
                topic="general",
                language="unknown",
                emotion="neutral",
                flagged=False,
            )

        self.assertEqual(result["status"], "skipped")
        save.assert_not_called()

    def test_provider_failure_fallback_does_not_invent_clinical_or_academic_claims(self) -> None:
        service = SummaryService(_FailedLlm())
        summary = service.generate_summary(
            student_name="Student",
            conversation=[{"role": "user", "content": "I want to book an appointment."}],
            topic="appointment",
            language="english",
            emotion="neutral",
            flagged=False,
        )

        self.assertEqual(
            summary.summary,
            "The student reported a wellbeing concern during the conversation.",
        )
        for unsupported in ("anxiety", "distress", "overwhelm", "self-doubt", "academic pressure", "coping"):
            self.assertNotIn(unsupported, summary.summary.casefold())

    def test_flagged_finalization_creates_high_priority_staff_notification(self) -> None:
        summary = SimpleNamespace(
            primary_concern="Crisis Concern",
            conversation_type="general",
            emotion="Crisis",
            flagged=True,
            appointment_recommendation=False,
            recommendations="Immediate Guidance Office review is recommended.",
            suggested_intervention="Immediate Guidance Office review is recommended.",
            language="english",
            total_messages=2,
            summary="Clinical crisis summary.",
        )
        with patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=summary,
        ), patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service,
            "save_conversation_summary",
            return_value=44,
        ), patch.object(
            conversation_service,
            "save_escalation",
        ) as save_escalation, patch.object(
            conversation_service,
            "get_student_by_id",
            return_value={"program": "BSCS"},
        ), patch.object(
            conversation_service,
            "get_staff_by_program",
            return_value={"id": 9},
        ), patch.object(
            conversation_service,
            "save_notification",
        ) as save_notification:
            conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[
                    {"from": "user", "text": "I wanna finish my life."},
                    {"from": "bot", "text": "Please contact the Guidance Office."},
                ],
                topic="Crisis Concern",
                language="english",
                emotion="Crisis",
                flagged=True,
            )

        self.assertEqual(save_escalation.call_args.args[0]["status"], "pending")
        notification = save_notification.call_args.args[0]
        self.assertEqual(notification["recipient_account_id"], 9)
        self.assertEqual(notification["title"], "High-risk student conversation detected.")
        self.assertEqual(notification["type"], "high_risk_conversation")

    def test_first_crisis_response_immediately_marks_session_for_pending_review(self) -> None:
        client = self._client()
        crisis_result = SimpleNamespace(
            success=True,
            response="Please contact the Guidance Office immediately.",
            emotion="Crisis",
            sentiment="Negative",
            language="english",
            topic="Crisis Concern",
            state="Crisis",
            escalated=True,
            confidence=0.0,
            intent="emergency",
            normalized_emotion="crisis",
            normalized_topic="crisis",
            metadata={},
        )
        with patch(
            "backend.server.routes.chatbot_routes.ai_service.respond",
            return_value=crisis_result,
        ), patch(
            "backend.server.routes.chatbot_routes.record_chat_inquiry",
        ), patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.record_exchange",
        ), patch(
            "backend.server.routes.chatbot_routes.ensure_staff_visible_active_conversation",
            return_value=81,
        ), patch(
            "backend.server.routes.chatbot_routes.mark_active_conversation_for_immediate_review",
        ) as mark_active, patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.get_transcript_history",
            return_value=[
                {"role": "user", "content": "I wanna finish my life."},
                {"role": "assistant", "content": "Please contact the Guidance Office immediately."},
            ],
        ), patch(
            "backend.server.routes.chatbot_routes.save_flagged_case_transcript",
        ) as save_transcript:
            response = client.post(
                "/chat",
                json={"message": "I wanna finish my life.", "conversation": []},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["data"]["escalated"])
        self.assertEqual(response.get_json()["data"]["topic"], "Crisis Concern")
        with client.session_transaction() as session:
            self.assertTrue(session["conversation_escalated"])
            self.assertEqual(session["active_conversation_summary_id"], 81)
            self.assertEqual(session["conversation_escalation_reason"], "AI safety escalation.")
        mark_active.assert_called_once_with(81, 1, "AI safety escalation.")
        save_transcript.assert_called_once_with(
            81,
            [
                {"role": "user", "content": "I wanna finish my life."},
                {"role": "assistant", "content": "Please contact the Guidance Office immediately."},
            ],
        )

    def test_warning_sign_response_immediately_creates_review_only_case(self) -> None:
        client = self._client()
        warning_result = SimpleNamespace(
            success=True,
            response="You do not have to face this alone.",
            emotion="Sadness",
            sentiment="Negative",
            language="english",
            topic="Counseling",
            state="Exploring Concern",
            escalated=False,
            needs_staff_review=True,
            confidence=0.92,
            intent="unknown",
            normalized_emotion="sadness",
            normalized_topic="counseling",
            metadata={},
        )
        with patch(
            "backend.server.routes.chatbot_routes.ai_service.respond",
            return_value=warning_result,
        ), patch(
            "backend.server.routes.chatbot_routes.record_chat_inquiry",
        ), patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.record_exchange",
        ), patch(
            "backend.server.routes.chatbot_routes.ensure_staff_visible_active_conversation",
            return_value=81,
        ), patch(
            "backend.server.routes.chatbot_routes.mark_active_conversation_for_staff_review",
        ) as mark_for_review, patch(
            "backend.server.routes.chatbot_routes.mark_active_conversation_for_immediate_review",
        ) as mark_immediate, patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.get_transcript_history",
            return_value=[
                {"role": "user", "content": "I feel empty."},
                {"role": "assistant", "content": "You do not have to face this alone."},
            ],
        ), patch(
            "backend.server.routes.chatbot_routes.save_flagged_case_transcript",
        ) as save_transcript:
            response = client.post(
                "/chat",
                json={"message": "I feel empty.", "conversation": []},
            )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["data"]["escalated"])
        self.assertTrue(response.get_json()["data"]["needs_staff_review"])
        mark_for_review.assert_called_once_with(
            81,
            1,
            "Counselor review requested for a reported wellbeing warning sign.",
        )
        mark_immediate.assert_not_called()
        save_transcript.assert_called_once_with(
            81,
            [
                {"role": "user", "content": "I feel empty."},
                {"role": "assistant", "content": "You do not have to face this alone."},
            ],
        )
        with client.session_transaction() as session:
            self.assertTrue(session["conversation_needs_staff_review"])

    def test_first_chat_message_creates_one_staff_visible_active_placeholder(self) -> None:
        client = self._client()
        normal_result = SimpleNamespace(
            success=True,
            response="Let's look at one manageable next step.",
            emotion="Neutral",
            sentiment="Neutral",
            language="english",
            topic="Academics",
            state="Exploring Concern",
            escalated=False,
            confidence=0.9,
            intent="unknown",
            normalized_emotion="neutral",
            normalized_topic="academics",
            metadata={},
        )
        with patch(
            "backend.server.routes.chatbot_routes.ai_service.respond",
            return_value=normal_result,
        ), patch(
            "backend.server.routes.chatbot_routes.record_chat_inquiry",
        ), patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.record_exchange",
        ), patch(
            "backend.server.routes.chatbot_routes.ensure_staff_visible_active_conversation",
            return_value=81,
        ) as ensure_active:
            first = client.post("/chat", json={"message": "I am stressed.", "conversation": []})
            second = client.post("/chat", json={"message": "Still stressed.", "conversation": []})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.get_json()["data"]["feedback_token"])
        self.assertTrue(second.get_json()["data"]["feedback_token"])
        self.assertNotEqual(
            first.get_json()["data"]["feedback_token"],
            second.get_json()["data"]["feedback_token"],
        )
        ensure_active.assert_called_once_with(1)
        with client.session_transaction() as session:
            self.assertEqual(session["active_conversation_summary_id"], 81)
            self.assertEqual(len(session["chatbot_feedback_response_tokens"]), 2)

    def test_finalization_updates_active_placeholder_without_creating_a_duplicate(self) -> None:
        summary = SimpleNamespace(
            primary_concern="Academics",
            conversation_type="general",
            emotion="Neutral",
            flagged=False,
            appointment_recommendation=False,
            recommendations="Continue with one manageable academic next step.",
            suggested_intervention="Monitor routine academic stress.",
            language="english",
            total_messages=2,
            summary="The student discussed routine academic stress.",
        )
        with patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=summary,
        ), patch.object(
            conversation_service,
            "finalize_active_conversation_summary",
            return_value=True,
        ) as finalize_active, patch.object(
            conversation_service,
            "save_conversation_summary",
        ) as save_summary:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[
                    {"from": "user", "text": "I am stressed about school."},
                    {"from": "bot", "text": "Let's make a plan."},
                ],
                topic="Academics",
                language="english",
                emotion="Neutral",
                flagged=False,
                active_summary_id=81,
            )

        self.assertEqual(result["summary_id"], 81)
        finalize_active.assert_called_once()
        save_summary.assert_not_called()

    def test_flagged_finalization_updates_its_active_placeholder_and_escalates(self) -> None:
        summary = SimpleNamespace(
            primary_concern="Crisis Concern",
            conversation_type="general",
            emotion="Crisis",
            flagged=True,
            appointment_recommendation=False,
            recommendations="Immediate Guidance Office review is recommended.",
            suggested_intervention="Immediate Guidance Office review is recommended.",
            language="english",
            total_messages=2,
            summary="The student expressed a high-risk safety concern.",
        )
        with patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=summary,
        ), patch.object(
            conversation_service,
            "finalize_active_conversation_summary",
            return_value=True,
        ) as finalize_active, patch.object(
            conversation_service,
            "save_conversation_summary",
        ) as save_summary, patch.object(
            conversation_service,
            "ensure_pending_escalation",
            return_value=False,
        ) as ensure_escalation, patch.object(
            conversation_service,
            "get_student_by_id",
            return_value=None,
        ):
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[
                    {"from": "user", "text": "I want to hang myself."},
                    {"from": "bot", "text": "Please contact the Guidance Office."},
                ],
                topic="Crisis Concern",
                language="english",
                emotion="Crisis",
                flagged=True,
                active_summary_id=82,
            )

        self.assertEqual(result["summary_id"], 82)
        finalize_active.assert_called_once()
        save_summary.assert_not_called()
        ensure_escalation.assert_called_once()

    def test_later_neutral_message_cannot_clear_high_risk_session_state(self) -> None:
        client = self._client()
        high_risk = SimpleNamespace(
            success=True, response="Safety response.", emotion="Crisis",
            sentiment="Negative", language="english", topic="Crisis Concern",
            state="Crisis", escalated=True, confidence=0.0, intent="emergency",
            normalized_emotion="crisis", normalized_topic="crisis", metadata={},
        )
        neutral = SimpleNamespace(
            success=True, response="You're welcome.", emotion="Neutral",
            sentiment="Neutral", language="english", topic="General",
            state="Closing", escalated=False, confidence=0.9, intent="unknown",
            normalized_emotion="neutral", normalized_topic="general", metadata={},
        )
        with patch(
            "backend.server.routes.chatbot_routes.ai_service.respond",
            side_effect=[high_risk, neutral],
        ), patch(
            "backend.server.routes.chatbot_routes.record_chat_inquiry",
        ), patch(
            "backend.server.routes.chatbot_routes.transient_chat_service.record_exchange",
        ), patch(
            "backend.server.routes.chatbot_routes.ensure_staff_visible_active_conversation",
            return_value=81,
        ), patch(
            "backend.server.routes.chatbot_routes.mark_active_conversation_for_immediate_review",
        ):
            first = client.post("/chat", json={"message": "I want to finish my life.", "conversation": []})
            second = client.post("/chat", json={"message": "okay", "conversation": []})

        self.assertTrue(first.get_json()["data"]["escalated"])
        self.assertFalse(second.get_json()["data"]["escalated"])
        self.assertTrue(second.get_json()["data"]["session_escalated"])
        with client.session_transaction() as session:
            self.assertTrue(session["conversation_escalated"])

    def test_active_crisis_placeholder_is_marked_pending_and_notified_once(self) -> None:
        with patch.object(
            conversation_service,
            "mark_active_conversation_escalated",
            return_value=True,
        ) as mark_active, patch.object(
            conversation_service,
            "ensure_pending_escalation",
            return_value=True,
        ) as ensure_escalation, patch.object(
            conversation_service,
            "_notify_high_risk_conversation_safely",
        ) as notify:
            conversation_service.mark_active_conversation_for_immediate_review(
                81,
                1,
                "AI safety escalation.",
            )

        mark_active.assert_called_once_with(81, 1)
        ensure_escalation.assert_called_once_with(1, 81, "AI safety escalation.")
        notify.assert_called_once_with(1)

    def test_active_warning_sign_placeholder_is_pending_without_high_risk_notification(self) -> None:
        with patch.object(
            conversation_service,
            "mark_active_summary_for_staff_review",
            return_value=True,
        ) as mark_active, patch.object(
            conversation_service,
            "ensure_pending_escalation",
            return_value=True,
        ) as ensure_escalation, patch.object(
            conversation_service,
            "_notify_high_risk_conversation_safely",
        ) as notify:
            conversation_service.mark_active_conversation_for_staff_review(
                81,
                1,
                "Counselor review requested for a reported wellbeing warning sign.",
            )

        mark_active.assert_called_once_with(81, 1)
        ensure_escalation.assert_called_once_with(
            1,
            81,
            "Counselor review requested for a reported wellbeing warning sign.",
        )
        notify.assert_not_called()

    def test_notification_failure_does_not_roll_back_flagged_case_persistence(self) -> None:
        summary = SimpleNamespace(
            primary_concern="Crisis Concern", conversation_type="general",
            emotion="Crisis", flagged=True, appointment_recommendation=False,
            recommendations="Immediate Guidance Office review is recommended.",
            suggested_intervention="Immediate Guidance Office review is recommended.",
            language="english", total_messages=1, summary="Clinical crisis summary.",
        )
        with patch.object(conversation_service.summary_service, "generate_summary", return_value=summary), patch.object(
            conversation_service, "fetch_open_conversation_case", return_value=None
        ), patch.object(
            conversation_service, "save_conversation_summary", return_value=45
        ) as save_summary, patch.object(conversation_service, "save_escalation") as save_escalation, patch.object(
            conversation_service, "get_student_by_id", return_value={"program": "BSCS"}
        ), patch.object(conversation_service, "get_staff_by_program", return_value={"id": 9}), patch.object(
            conversation_service, "save_notification", side_effect=RuntimeError("notification unavailable")
        ):
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[{"from": "user", "text": "I should end everything."}],
                topic="Crisis Concern", language="english", emotion="Crisis", flagged=True,
            )

        self.assertEqual(result["status"], "saved")
        save_summary.assert_called_once()
        save_escalation.assert_called_once()

    def test_routine_follow_up_does_not_mutate_existing_pending_case(self) -> None:
        open_case = {
            "summary_id": 72,
            "summary": "The student expressed suicidal ideation and received a safety response.",
            "total_messages": 2,
        }
        routine_summary = SimpleNamespace(
            primary_concern="Guidance Office",
            conversation_type="general",
            emotion="Neutral",
            flagged=False,
            appointment_recommendation=False,
            recommendations="No escalation was required based on the recorded session.",
            suggested_intervention="No escalation was required based on the recorded session.",
            language="english",
            total_messages=2,
            summary="The student asked about Guidance Office hours.",
        )
        follow_up = [
            {"from": "user", "text": "What are your office hours?"},
            {"from": "bot", "text": "The office is open on weekdays."},
        ]
        with patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=open_case,
        ) as fetch_open, patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=routine_summary,
        ) as generate_summary, patch.object(
            conversation_service.summary_service,
            "refresh_open_case_summary",
        ) as refresh_summary, patch.object(
            conversation_service,
            "refresh_open_conversation_summary",
        ) as refresh_persistence, patch.object(
            conversation_service,
            "save_conversation_summary",
            return_value=73,
        ) as create_summary, patch.object(
            conversation_service,
            "save_escalation",
        ) as save_escalation:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=follow_up,
                topic="Guidance Office",
                language="english",
                emotion="Neutral",
                flagged=False,
            )

        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["summary_id"], 73)
        fetch_open.assert_not_called()
        refresh_summary.assert_not_called()
        refresh_persistence.assert_not_called()
        save_escalation.assert_not_called()
        generate_summary.assert_called_once()
        payload = create_summary.call_args.args[0]
        self.assertFalse(payload["flagged_status"])
        self.assertEqual(payload["summary"], "The student asked about Guidance Office hours.")

    def test_genuine_flagged_follow_up_refreshes_existing_pending_case_without_duplicate(self) -> None:
        open_case = {
            "summary_id": 72,
            "summary": "The student expressed suicidal ideation and received a safety response.",
            "total_messages": 2,
        }
        follow_up = [
            {"from": "user", "text": "I still feel like I might hurt myself."},
            {"from": "bot", "text": "Please contact the Guidance Office immediately."},
        ]
        with patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=open_case,
        ), patch.object(
            conversation_service.summary_service,
            "refresh_open_case_summary",
            return_value=(
                "The student previously expressed suicidal ideation and later reported "
                "continued high-risk safety concerns."
            ),
        ) as refresh_summary, patch.object(
            conversation_service,
            "refresh_open_conversation_summary",
            return_value=True,
        ) as refresh_persistence, patch.object(
            conversation_service,
            "save_conversation_summary",
        ) as create_summary, patch.object(
            conversation_service,
            "save_escalation",
        ) as save_escalation:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=follow_up,
                topic="Crisis Concern",
                language="english",
                emotion="Crisis",
                flagged=True,
            )

        self.assertEqual(result["status"], "updated_open_case")
        self.assertEqual(result["summary_id"], 72)
        self.assertEqual(result["student_message_count"], 1)
        refresh_summary.assert_called_once()
        refresh_persistence.assert_called_once_with(
            72,
            "The student previously expressed suicidal ideation and later reported continued high-risk safety concerns.",
            4,
        )
        create_summary.assert_not_called()
        save_escalation.assert_not_called()

    def test_refresh_open_case_preserves_original_created_at_column(self) -> None:
        cursor = MagicMock()
        cursor.rowcount = 1
        cursor_context = MagicMock()
        cursor_context.__enter__.return_value = cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor_context
        connection_context = MagicMock()
        connection_context.__enter__.return_value = connection

        with patch.object(db, "initialize_database"), patch.object(
            db,
            "_database_connection",
            return_value=connection_context,
        ):
            updated = db.refresh_open_conversation_summary(
                72,
                "Updated active case summary.",
                4,
            )

        self.assertTrue(updated)
        sql, params = cursor.execute.call_args.args
        self.assertNotIn("created_at", sql.casefold())
        self.assertEqual(params, ("Updated active case summary.", 4, 72))
        connection.commit.assert_called_once()

    def test_reviewed_case_allows_the_next_conversation_to_create_a_new_summary(self) -> None:
        summary = SimpleNamespace(
            primary_concern="Guidance Office",
            conversation_type="general",
            emotion="Neutral",
            flagged=False,
            appointment_recommendation=False,
            recommendations="No escalation was required based on the recorded session.",
            suggested_intervention="No escalation was required based on the recorded session.",
            language="english",
            total_messages=2,
            summary="The student asked about office hours.",
        )
        with patch.object(
            conversation_service,
            "fetch_open_conversation_case",
            return_value=None,
        ), patch.object(
            conversation_service.summary_service,
            "generate_summary",
            return_value=summary,
        ), patch.object(
            conversation_service,
            "save_conversation_summary",
            return_value=73,
        ) as create_summary:
            result = conversation_service.finalize_conversation(
                user={"id": 1, "full_name": "Student"},
                conversation=[
                    {"from": "user", "text": "What are your office hours?"},
                    {"from": "bot", "text": "Weekday office hours."},
                ],
                topic="Guidance Office",
                language="english",
                emotion="Neutral",
                flagged=False,
            )

        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["summary_id"], 73)
        create_summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
