"""Opt-in Flask integration coverage for the public system contracts.

Run this suite only against an isolated MySQL database:

    CTRL4_RUN_SYSTEM_INTEGRATION_TESTS=1 \
    CTRL4_SYSTEM_INTEGRATION_DB=<isolated database name> \
    CHATBOT_DB_NAME=<same isolated database name> \
    python3 -m unittest tests.test_system_integration_runtime -v

The suite mocks service results at route boundaries.  It verifies application
wiring, server-side sessions, RBAC, response envelopes, and privacy projections
without creating workflow records or relying on production data.
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


_RUNTIME_DEPENDENCIES = (
    "flask",
    "mysql.connector",
    "dotenv",
)


def _runtime_is_available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in _RUNTIME_DEPENDENCIES)


def _isolated_database_is_configured() -> bool:
    expected_database = os.getenv("CTRL4_SYSTEM_INTEGRATION_DB", "").strip()
    active_database = os.getenv("CHATBOT_DB_NAME", "").strip()
    return bool(expected_database) and active_database == expected_database


@unittest.skipUnless(
    _runtime_is_available() and _isolated_database_is_configured()
    and os.getenv("CTRL4_RUN_SYSTEM_INTEGRATION_TESTS") == "1",
    "requires Flask runtime dependencies and an explicitly configured isolated MySQL database",
)
class SystemRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from backend.server import create_app

        cls.app = create_app()
        cls.app.config.update(TESTING=True)

    def _client_for(self, role: str, account_id: int = 1):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["hau_user"] = {
                "id": account_id,
                "email": f"{role}{account_id}@example.test",
                "role": role,
            }
            session["_csrf_token"] = "system-integration-csrf-token"
        return client

    @staticmethod
    def _csrf_headers(client) -> dict[str, str]:
        with client.session_transaction() as session:
            return {"X-CSRF-Token": session["_csrf_token"]}

    def _assert_envelope(self, response, status: int) -> dict:
        self.assertEqual(response.status_code, status)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("success", payload)
        self.assertIn("message", payload)
        if payload["success"]:
            self.assertIn("data", payload)
        else:
            self.assertIn("errors", payload)
        return payload

    def test_unauthenticated_api_access_uses_the_standard_error_envelope(self) -> None:
        response = self.app.test_client().get("/api/appointments")
        payload = self._assert_envelope(response, 401)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["message"], "Login required.")
        self.assertIsNone(payload["errors"])

    def test_authentication_creates_and_clears_the_server_side_session(self) -> None:
        from backend.server import auth

        user = {"id": 7, "email": "student7@example.test", "role": "student"}
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["_csrf_token"] = "login-csrf-token"
        with patch.object(auth, "login_service", return_value=user):
            login_payload = self._assert_envelope(
                client.post(
                    "/auth/login",
                    json={"email": user["email"], "password": "not-persisted"},
                    headers=self._csrf_headers(client),
                ),
                200,
            )

        self.assertEqual(login_payload["data"], user)
        with client.session_transaction() as session:
            self.assertEqual(session["hau_user"], user)
            self.assertTrue(session.permanent)

        logout_payload = self._assert_envelope(
            client.post("/auth/logout", headers=self._csrf_headers(client)),
            200,
        )
        self.assertIsNone(logout_payload["data"])
        with client.session_transaction() as session:
            self.assertNotIn("hau_user", session)

    def test_student_and_staff_appointment_boundaries(self) -> None:
        from backend.server.routes import appointment_routes

        appointment = {"id": 11, "status": "pending"}
        with patch.object(
            appointment_routes,
            "list_staff_appointments_service",
            return_value=[appointment],
        ), patch.object(
            appointment_routes,
            "list_student_appointments_service",
            return_value=[appointment],
        ):
            staff_payload = self._assert_envelope(
                self._client_for("staff").get("/api/appointments"),
                200,
            )
            self.assertEqual(staff_payload["data"]["items"], [appointment])

            denied_payload = self._assert_envelope(
                self._client_for("student").get("/api/appointments"),
                403,
            )
            self.assertFalse(denied_payload["success"])

            student_payload = self._assert_envelope(
                self._client_for("student").get("/api/appointments/my"),
                200,
            )
            self.assertEqual(student_payload["data"]["items"], [appointment])

    def test_staff_analytics_are_authorized_and_keep_the_response_contract(self) -> None:
        from backend.server.routes import dashboard_routes

        analytics = {
            "appointments": {"total": 1},
            "chatbot": {"total_messages": 1},
            "workload": {"authorized_appointment_count": 1},
            "flagged_cases": {"total_flagged_cases": 1},
        }
        patches = (
            patch.object(
                dashboard_routes,
                "get_appointment_analytics_service",
                return_value=analytics["appointments"],
            ),
            patch.object(
                dashboard_routes,
                "get_chatbot_analytics_service",
                return_value=analytics["chatbot"],
            ),
            patch.object(
                dashboard_routes,
                "get_counselor_workload_analytics_service",
                return_value=analytics["workload"],
            ),
            patch.object(
                dashboard_routes,
                "get_flagged_case_analytics_service",
                return_value=analytics["flagged_cases"],
            ),
        )

        with patches[0], patches[1], patches[2], patches[3]:
            endpoints = (
                "/api/dashboard/appointments/analytics",
                "/api/dashboard/chatbot/analytics",
                "/api/dashboard/counselor-workload",
                "/api/dashboard/flagged-cases/analytics",
            )
            for endpoint in endpoints:
                with self.subTest(endpoint=endpoint):
                    self._assert_envelope(
                        self._client_for("staff").get(
                            f"{endpoint}?start_date=2026-01-01&end_date=2026-01-31"
                        ),
                        200,
                    )
                    denied = self._assert_envelope(
                        self._client_for("student").get(endpoint),
                        403,
                    )
                    self.assertFalse(denied["success"])

    def test_fresh_seed_pending_case_is_visible_to_its_assigned_counselor(self) -> None:
        from backend.server import db
        from backend.server.config import Config

        config = Config()
        db.seed_database()
        student = db.fetch_account_by_email(config.SEED_STUDENT_EMAIL)
        staff = db.fetch_account_by_email(config.SEED_STAFF_EMAIL)
        self.assertIsNotNone(student)
        self.assertIsNotNone(staff)

        summary_id = db.save_conversation_summary(
            {
                "account_id": student["id"],
                "primary_concern": "Crisis Concern",
                "conversation_type": "general",
                "emotion_results": "Crisis",
                "flagged_status": True,
                "appointment_recommendation": False,
                "recommendations": "Immediate Guidance Office review is recommended.",
                "suggested_intervention": "Immediate Guidance Office review is recommended.",
                "language_used": "english",
                "total_messages": 1,
                "summary": "A current abstract crisis summary.",
            }
        )
        db.save_escalation(
            {
                "account_id": student["id"],
                "summary_id": summary_id,
                "status": "pending",
                "escalation_reason": "AI safety escalation.",
            }
        )

        client = self._client_for("staff", account_id=staff["id"])
        inbox = self._assert_envelope(client.get("/api/staff/inbox"), 200)
        flagged = self._assert_envelope(
            client.get("/api/flagged-conversations"),
            200,
        )

        inbox_item = next(
            item
            for item in inbox["data"]["items"]
            if item["summary_id"] == summary_id
        )
        self.assertEqual(inbox_item["review_status"], "pending")
        self.assertTrue(inbox_item["flagged_status"])
        self.assertEqual(flagged["data"]["items"], [inbox_item])
        self.assertNotIn("conversation_json", inbox_item)

    def test_case_modules_are_staff_only(self) -> None:
        from backend.server.routes import conversation_routes

        with patch.object(
            conversation_routes,
            "get_staff_case_confidentiality",
            return_value={"status": "confidential"},
        ), patch.object(
            conversation_routes,
            "list_staff_case_notes",
            return_value=[],
        ), patch.object(
            conversation_routes,
            "list_staff_referrals",
            return_value=[],
        ), patch.object(
            conversation_routes,
            "list_staff_interventions",
            return_value=[],
        ):
            self.assertEqual(
                self._client_for("student").get("/api/student/cases").status_code,
                404,
            )
            self.assertEqual(
                self._client_for("student").get("/case-status").status_code,
                404,
            )

            self._assert_envelope(
                self._client_for("student").get(
                    "/api/flagged-conversations/9/notes"
                ),
                403,
            )
            for suffix in ("notes", "referrals", "interventions"):
                with self.subTest(module=suffix):
                    self._assert_envelope(
                        self._client_for("staff").get(
                            f"/api/flagged-conversations/9/{suffix}"
                        ),
                        200,
                    )
            self._assert_envelope(
                self._client_for("staff").get(
                    "/api/flagged-conversations/9/confidentiality"
                ),
                200,
            )

    def test_notifications_are_recipient_scoped_by_the_service_boundary(self) -> None:
        from backend.server.routes import notification_routes

        with patch.object(
            notification_routes,
            "list_notifications_service",
            return_value=[{"title": "Appointment update", "is_read": False}],
        ) as list_notifications:
            payload = self._assert_envelope(
                self._client_for("student", account_id=13).get("/api/notifications"),
                200,
            )

        self.assertEqual(payload["data"]["items"][0]["title"], "Appointment update")
        list_notifications.assert_called_once_with(
            {
                "id": 13,
                "email": "student13@example.test",
                "role": "student",
            }
        )

    def test_chat_escalation_and_finalization_keep_session_owned_state(self) -> None:
        from backend.server.routes import chatbot_routes

        chat_result = SimpleNamespace(
            success=True,
            response="Please contact the Guidance Office.",
            emotion="negative",
            sentiment="negative",
            language="english",
            escalated=False,
            confidence=0.92,
            normalized_emotion="distressed",
        )
        client = self._client_for("student", account_id=7)
        with patch.object(
            chatbot_routes.ai_service,
            "respond",
            return_value=chat_result,
        ), patch.object(chatbot_routes, "record_chat_inquiry"), patch.object(
            chatbot_routes,
            "should_escalate_conversation",
            return_value=True,
        ), patch.object(
            chatbot_routes,
            "determine_escalation_reason",
            return_value="Detected distressed emotion.",
        ), patch.object(
            chatbot_routes,
            "finalize_conversation",
            return_value={"status": "saved"},
        ):
            chat_payload = self._assert_envelope(
                client.post(
                    "/chat",
                    json={"message": "I need help", "conversation": []},
                    headers=self._csrf_headers(client),
                ),
                200,
            )
            self.assertEqual(chat_payload["data"]["response"], chat_result.response)

            with client.session_transaction() as session:
                self.assertTrue(session.get("conversation_escalated"))

            finalized = self._assert_envelope(
                client.post(
                    "/chat/finalize",
                    json={"conversation": [{"role": "user", "content": "I need help"}]},
                    headers=self._csrf_headers(client),
                ),
                200,
            )
            self.assertEqual(finalized["data"], {"status": "saved"})
            with client.session_transaction() as session:
                self.assertNotIn("conversation_escalated", session)
                self.assertNotIn("conversation_escalation_reason", session)


if __name__ == "__main__":
    unittest.main()
