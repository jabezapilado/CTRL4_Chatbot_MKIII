"""Dependency-free regression checks for Issue #71 security boundaries."""

from __future__ import annotations

import unittest
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


class SecurityPrivacyContractTests(unittest.TestCase):
    def test_server_side_session_wiring_and_fixation_rotation_are_present(self) -> None:
        config = _source("backend/server/config.py")
        app_factory = _source("backend/server/__init__.py")
        auth = _source("backend/server/auth.py")

        self.assertIn('self.SESSION_TYPE = os.getenv("CHATBOT_SESSION_TYPE", "cachelib")', config)
        self.assertIn("self.SESSION_CACHE_DIR", config)
        self.assertIn("SESSION_COOKIE_HTTPONLY = True", config)
        self.assertIn("SESSION_COOKIE_SAMESITE = \"Lax\"", config)
        self.assertIn("PERMANENT_SESSION_LIFETIME = timedelta(hours=8)", config)
        self.assertIn("from flask_session import Session", app_factory)
        self.assertIn("from cachelib.file import FileSystemCache", app_factory)
        self.assertIn('app.config["SESSION_CACHELIB"] = FileSystemCache(', app_factory)
        self.assertIn("Session(app)", app_factory)
        self.assertIn("install_csrf_protection(app)", app_factory)
        self.assertNotIn("flask_cors", app_factory)
        self.assertIn("session.clear()", auth)
        self.assertIn("_rotate_authenticated_session()", auth)
        self.assertIn("regenerate(session)", auth)

    def test_csrf_and_same_origin_cors_controls_are_wired_centrally(self) -> None:
        csrf = _source("backend/server/csrf.py")
        security = _source("frontend/static/js/security.js")
        app_factory = _source("backend/server/__init__.py")
        auth = _source("backend/server/auth.py")

        self.assertIn('CSRF_HEADER_NAME = "X-CSRF-Token"', csrf)
        self.assertIn('SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})', csrf)
        self.assertIn('request.endpoint != "auth.login"', csrf)
        self.assertIn("hmac.compare_digest", csrf)
        self.assertIn('headers.set("X-CSRF-Token", csrfToken)', security)
        self.assertIn("isSameOrigin(input)", security)
        self.assertIn('.fetch("/auth/session-status"', security)
        self.assertIn("showStudentSessionReplacementNotice();", security)
        self.assertNotIn("CORS(app)", app_factory)

        for template_name in (
            "login.html",
            "chatbot.html",
            "appointment.html",
            "dashboard.html",
            "admin.html",
        ):
            template = _source(f"frontend/templates/{template_name}")
            with self.subTest(template=template_name):
                self.assertIn('name="csrf-token" content="{{ csrf_token }}"', template)
                self.assertIn("js/security.js", template)

        chatbot_template = _source("frontend/templates/chatbot.html")
        self.assertIn('data-student-session-monitor="true"', chatbot_template)
        self.assertNotIn('href="/case-status"', chatbot_template)

        self.assertIn('@auth_bp.get("/auth/session-status")', auth)

    def test_chat_logging_never_interpolates_protected_payloads(self) -> None:
        chatbot_routes = _source("backend/server/routes/chatbot_routes.py")
        ai_service = _source("backend/server/services/ai_service.py")
        prompt_builder = _source("backend/server/services/prompt_builder.py")

        for source in (chatbot_routes, ai_service, prompt_builder):
            self.assertNotIn("AIService failed for message", source)
            self.assertNotIn("processing message: %r", source)
            self.assertNotIn("Conversation Debug", source)
            self.assertNotIn("logger.exception(", source)

        self.assertIn("exception_type=%s", chatbot_routes)
        self.assertIn("exception_type=%s", ai_service)
        self.assertNotIn("for user %s", chatbot_routes)

    def test_chat_browser_storage_only_clears_legacy_protected_keys(self) -> None:
        chat = _source("frontend/static/js/chat.js")
        auth = _source("frontend/static/js/auth.js")

        for key in (
            "hau_escalations",
            "hau_escalation_event",
            "hau_escalation_staff_msg",
            "hau_escalation_user_msg",
        ):
            self.assertIn(key, chat)
            self.assertNotIn(f'localStorage.setItem("{key}"', chat)
            self.assertNotIn(f'localStorage.getItem("{key}"', chat)

        self.assertIn('sessionStorage.removeItem("current_escalation")', chat)
        self.assertNotIn('sessionStorage.setItem("current_escalation"', chat)
        self.assertIn("hau_escalations", auth)

    def test_legacy_takeover_surface_is_removed(self) -> None:
        frontend_routes = _source("backend/server/routes/frontend_routes.py")
        chat = _source("frontend/static/js/chat.js")
        auth = _source("frontend/static/js/auth.js")

        self.assertFalse((PROJECT_ROOT / "frontend/templates/chatbot_admin.html").exists())
        self.assertFalse((PROJECT_ROOT / "frontend/static/js/chat_admin.js").exists())
        self.assertNotIn("chatbot_admin", frontend_routes)
        self.assertNotIn("hau_takeover_case", chat)
        self.assertNotIn("hau_takeover_case", auth)

    def test_dashboard_protects_persisted_values_in_html_and_dom_renderers(self) -> None:
        dashboard = _source("frontend/static/js/dashboard.js")

        self.assertIn("function escapeHtml(value)", dashboard)
        self.assertNotIn("option.innerHTML", dashboard)
        self.assertNotIn('onclick="', dashboard)

        self.assertIn("function renderInquiryTable()", dashboard)
        self.assertIn("studentName.textContent = item.studentName", dashboard)
        self.assertIn("studentNumber.textContent = item.studentNumber", dashboard)
        self.assertIn("previewText.textContent = item.summary", dashboard)
        self.assertIn("function openInboxItem", dashboard)
        self.assertNotIn("conversation_json", dashboard)
        self.assertIn("function renderFlaggedConversationTranscript", dashboard)
        self.assertIn("content.textContent = item.content || \"\"", dashboard)
        self.assertIn("cell.textContent = value", dashboard)

        # Persisted case-management values use textContent / DOM construction.
        for renderer in (
            "function renderCaseNotes",
            "function renderReferrals",
            "function renderInterventions",
            "function renderCaseConfidentiality",
        ):
            with self.subTest(renderer=renderer):
                self.assertIn(renderer, dashboard)

    def test_hostile_dashboard_value_is_escaped_as_text(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is unavailable for the frontend safety check.")

        script = """
const fs = require('fs');
const source = fs.readFileSync('frontend/static/js/dashboard.js', 'utf8');
const start = source.indexOf('function escapeHtml(value)');
const end = source.indexOf('\\nfunction escapeAppointmentText', start);
if (start < 0 || end < 0) process.exit(2);
const context = {};
require('vm').runInNewContext(source.slice(start, end), context);
const hostile = '<img src=x onerror=alert(1)>';
const escaped = context.escapeHtml(hostile);
if (escaped !== '&lt;img src=x onerror=alert(1)&gt;') process.exit(3);
"""
        result = subprocess.run(
            [node, "-e", script],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_student_and_notification_privacy_boundaries_remain_intact(self) -> None:
        from backend.server.services import appointment_service, notification_service

        with patch.object(
            appointment_service,
            "list_student_appointments",
            return_value=[
                {
                    "id": 4,
                    "account_id": 12,
                    "status": "pending",
                    "counselor_notes": "Private counselor note.",
                }
            ],
        ) as list_appointments:
            appointments = appointment_service.list_student_appointments_service(
                {"id": 12, "role": "student"}
            )

        list_appointments.assert_called_once_with(12)
        self.assertNotIn("counselor_notes", appointments[0])

        with patch.object(
            notification_service,
            "list_notifications_for_recipient",
            return_value=[{"id": 5, "title": "Appointment update"}],
        ) as list_notifications:
            notifications = notification_service.list_notifications_service(
                {"id": 12, "role": "student"}
            )

        self.assertEqual(notifications, [{"id": 5, "title": "Appointment update"}])
        list_notifications.assert_called_once_with(12)


if __name__ == "__main__":
    unittest.main()
