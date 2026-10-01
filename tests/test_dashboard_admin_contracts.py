"""Focused contracts for truthful dashboard metrics and admin account controls."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class DashboardDataIntegrityContractTests(unittest.TestCase):
    def test_legacy_placeholder_analytics_and_unsupported_panels_are_absent(self) -> None:
        dashboard = _read("frontend/templates/dashboard.html")

        for value in (
            "Total Resolved",
            "Staff Resolved",
            "72.8% resolution rate",
            "Inquiry Categories",
            "Office Schedule",
            "Recent Flagged Concerns",
            'id="reports-flagged-tbody"',
            'data-view="resolved"',
            'id="view-resolved"',
            "Maria Santos",
            "student@hau.edu.ph",
            "BS Computer Science</strong>",
            "July 28, 2026 • 8:13 AM",
        ):
            with self.subTest(value=value):
                self.assertNotIn(value, dashboard)

    def test_staff_lists_use_response_envelopes_and_privacy_projected_fields(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")

        self.assertIn("/api/staff/inbox", dashboard)
        self.assertIn("(inbox.data?.items || []).map(mapInboxItem)", dashboard)
        self.assertIn("function inboxItemsForCurrentFilter", dashboard)
        self.assertIn("summary_preview", dashboard)
        self.assertIn("Summary Preview", template)
        self.assertNotIn("Persisted Emotion Result", template)
        self.assertNotIn("/api/inquiries", dashboard)
        self.assertNotIn("conversation_json", dashboard)
        self.assertIn("Total Inquiries Today", template)
        self.assertIn("Flagged Cases / Negative Emotion", template)
        self.assertIn("Routine / Auto-Resolved Conversations", template)
        self.assertIn("Chatbot Status", template)
        self.assertIn("function loadInboxStatistics()", dashboard)
        self.assertIn("/api/dashboard/chatbot/analytics", dashboard)
        self.assertIn("/api/staff/inbox/${encodeURIComponent(summaryId)}/history", dashboard)
        self.assertIn('id="case-history-card"', template)
        self.assertIn("Reviewed Case History", template)
        self.assertNotIn("Avg. Response Time", template)

    def test_reports_continue_to_use_only_the_four_approved_aggregate_endpoints(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        expected_endpoints = (
            "/api/dashboard/appointments/analytics",
            "/api/dashboard/chatbot/analytics",
            "/api/dashboard/counselor-workload",
            "/api/dashboard/flagged-cases/analytics",
        )
        for endpoint in expected_endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, dashboard)

        self.assertNotIn("reports-flagged-tbody", dashboard)
        self.assertNotIn("total_appointments || 0", dashboard)
        self.assertNotIn("total_flagged_cases || 0", dashboard)
        self.assertIn("function loadInboxStatistics()", dashboard)
        self.assertIn("function todayAnalyticsQuery()", dashboard)
        self.assertIn("/api/flagged-conversations", dashboard)
        self.assertIn('cache: "no-store"', dashboard)

    def test_chatbot_feedback_uses_a_scoped_staff_endpoint_without_chat_transcripts(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")
        conversation_routes = _read("backend/server/routes/conversation_routes.py")

        self.assertIn('data-view="feedback"', template)
        self.assertIn('id="feedback-tbody"', template)
        self.assertIn('id="feedback-filter"', template)
        self.assertIn('id="feedback-context-filter"', template)
        self.assertIn('id="feedback-search-input"', template)
        self.assertIn('id="feedback-retry"', template)
        self.assertIn('id="feedback-insights"', template)
        self.assertIn("Reply context", template)
        self.assertIn("/api/staff/chatbot-feedback", dashboard)
        self.assertIn("function renderChatbotFeedback()", dashboard)
        self.assertIn("function feedbackItemsForCurrentFilter()", dashboard)
        self.assertIn("function bindFeedbackControls()", dashboard)
        self.assertIn("function renderFeedbackInsights()", dashboard)
        self.assertIn("function sortDashboardRecords(records", dashboard)
        self.assertIn("def staff_chatbot_feedback()", conversation_routes)
        self.assertIn("summarize_staff_chatbot_feedback", conversation_routes)
        self.assertIn('require_role("staff")', conversation_routes)
        self.assertNotIn("response_text", template)
        self.assertNotIn("student_message", template)

    def test_flagged_and_feedback_tables_offer_scoped_filters_and_priority_sorts(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('id="flagged-filter"', template)
        self.assertIn('id="flagged-search-input"', template)
        self.assertIn('id="flagged-table"', template)
        self.assertIn('id="flagged-insights"', template)
        self.assertIn('id="flagged-pending-count"', template)
        self.assertIn('id="flagged-reviewed-count"', template)
        self.assertIn('value="pending">Pending review', template)
        self.assertIn('value="reviewed">Reviewed', template)
        self.assertIn('value="priority-critical">Critical priority', template)
        self.assertIn('data-sort-key="priority"', template)
        self.assertIn('id="feedback-table"', template)
        self.assertIn('id="inbox-table"', template)
        self.assertIn('data-sort-key="student"', template)
        self.assertIn("let inboxSort = { key: \"priority\", direction: \"desc\" };", dashboard)
        self.assertIn("let feedbackSort = { key: \"student\", direction: \"asc\" };", dashboard)
        self.assertIn("let flaggedSort = { key: \"priority\", direction: \"desc\" };", dashboard)
        self.assertIn("function createCasePriorityBadge(priority)", dashboard)
        self.assertIn("function flaggedItemsForCurrentFilter()", dashboard)
        self.assertIn("function renderFlaggedInsights()", dashboard)
        self.assertIn("/api/flagged-conversations", dashboard)
        self.assertIn("Pending flagged-case count", dashboard)
        self.assertIn("createInboxStatusBadge(conversation)", dashboard)
        self.assertIn("function inboxSortValue(item", dashboard)
        self.assertIn("function bindFlaggedControls()", dashboard)
        self.assertIn(".table-sort", stylesheet)


class AdministratorAccountManagementContractTests(unittest.TestCase):
    def test_admin_portal_uses_only_registered_account_operations_and_safe_dom_rendering(self) -> None:
        template = _read("frontend/templates/admin.html")
        script = _read("frontend/static/js/admin.js")
        stylesheet = _read("frontend/static/css/admin.css")

        for identifier in (
            "create-account-btn",
            "download-account-template-btn",
            "import-accounts-btn",
            "account-import-dialog",
            "account-import-form",
            "account-dialog",
            "account-filter-form",
            "account-list-body",
            "account-status-filter",
            "program-catalog-list",
            "create-program-btn",
            "program-dialog",
            "program-form",
            "admin-program-table",
            "data-account-sort=\"account_number\"",
            "data-program-sort=\"display_name\"",
        ):
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, template)

        for endpoint in (
            '"/api/accounts"',
            'return `/api/accounts/staff/${account.id}`',
            'return `/api/accounts/admin/${account.id}`',
            'return `/api/accounts/${account.id}`',
            "/api/accounts/import/students",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertIn(endpoint, script)

        self.assertNotIn("/api/dashboard", script)
        self.assertNotIn("/api/flagged-conversations", script)
        self.assertNotIn('"BS Computer Science"', script)
        self.assertIn("function loadPrograms()", script)
        self.assertIn("/api/accounts/programs", script)
        self.assertNotIn("configuredPrograms", script)
        self.assertNotIn("account-consultation-rooms", template)
        self.assertNotIn("account-consultation-schedules", template)
        self.assertNotIn("account-support-statement", template)
        self.assertNotIn("account-office", template)
        self.assertIn("Program Management", template)
        self.assertIn("function renderProgramCatalog", script)
        self.assertIn("function loadPrograms", script)
        self.assertIn("function openProgramForm", script)
        self.assertIn("function saveProgram", script)
        self.assertIn("function downloadStudentAccountTemplate", script)
        self.assertIn("function downloadImportedCredentials", script)
        self.assertNotIn("window.prompt", script)
        self.assertIn("function sortRecords", script)
        self.assertIn("numeric: true", script)
        self.assertNotIn("password_hash", script)
        self.assertNotIn("account.password", script)
        self.assertNotIn(".innerHTML", script)
        self.assertNotIn("onclick=", template)
        self.assertIn("textContent", script)
        self.assertIn(".admin-sort-button", stylesheet)
        self.assertIn(".admin-program-table", stylesheet)
        self.assertIn("@media (max-width: 760px)", stylesheet)
        self.assertIn("@media (max-width: 480px)", stylesheet)

    def test_admin_route_and_account_contract_remain_admin_only(self) -> None:
        routes = _read("backend/server/routes/frontend_routes.py")
        account_routes = _read("backend/server/routes/account_routes.py")

        self.assertIn('if path == "/admin" and role != ROLE_ADMIN:', routes)
        self.assertIn("return redirect(role_landing_path(user))", routes)
        self.assertGreaterEqual(account_routes.count('require_role("admin")'), 7)
        self.assertIn('require_role("staff")', account_routes)

    def test_admin_search_includes_name_and_email_without_relaxing_identifier_scope(self) -> None:
        database = _read("backend/server/db.py")

        self.assertIn("role = 'admin'", database)
        self.assertIn("OR email LIKE %s", database)
        self.assertNotIn("password_hash LIKE", database)

    def test_current_documentation_describes_the_account_management_portal(self) -> None:
        api_reference = _read("docs/architecture/api_reference.md")
        project_context = _read("docs/architecture/project_context.md")

        self.assertIn("Account-management portal only", api_reference)
        self.assertNotIn("Account-listing page only", api_reference)
        self.assertIn("names and emails for every account role", project_context)


if __name__ == "__main__":
    unittest.main()
