"""Lightweight contracts for the staff dashboard responsive-layout fixes."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class FrontendLayoutContractTests(unittest.TestCase):
    def test_chatbot_feedback_uses_reply_icons_and_a_modal_dialog(self) -> None:
        chat = _read("frontend/static/js/chat.js")
        stylesheet = _read("frontend/static/css/chatbot.css")

        self.assertIn("createThumbIcon(kind)", chat)
        self.assertIn("function createThumbIcon(direction)", chat)
        self.assertIn("openFeedbackDialog(feedbackToken, kind", chat)
        self.assertIn('title.textContent = "Share feedback"', chat)
        self.assertIn("chatbot-feedback-modal", stylesheet)
        self.assertIn("chatbot-feedback-dialog", stylesheet)
        self.assertIn(".chatbot-feedback-icon.selected", stylesheet)
        self.assertIn("border: 1.5px solid var(--gray-400);", stylesheet)
        self.assertNotIn("--gray-300", stylesheet)

    def test_staff_feedback_view_aligns_its_copy_with_the_dashboard_panel(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('class="stat-grid feedback-stat-grid"', template)
        self.assertIn('id="feedback-pattern-detail"', template)
        self.assertIn("#view-feedback > .panel > .sub", stylesheet)
        self.assertIn(".feedback-stat-grid", stylesheet)
        self.assertIn("padding: 9px 20px 7px;", stylesheet)

    def test_notifications_mount_in_the_dashboard_header(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        notifications = _read("frontend/static/js/notifications.js")
        stylesheet = _read("frontend/static/css/notifications.css")

        self.assertIn('data-notifications-mount', template)
        self.assertIn('const headerMount = document.querySelector("[data-notifications-mount]")', notifications)
        self.assertIn("notifications-widget--header", notifications)
        self.assertIn("function positionHeaderPanel()", notifications)
        self.assertIn('panel.classList.add("notifications-panel--header")', notifications)
        self.assertIn("document.body.appendChild(panel);", notifications)
        self.assertIn('document.addEventListener("pointerdown"', notifications)
        self.assertIn("!root.contains(event.target) && !panel.contains(event.target)", notifications)
        self.assertIn('event.key === "Escape"', notifications)
        self.assertIn('toggle.setAttribute("aria-label", "Notifications")', notifications)
        self.assertIn("notifications-icon", notifications)
        self.assertIn("Notification%20Bell2.svg", notifications)
        self.assertIn('const item = document.createElement("button")', notifications)
        self.assertIn("void openNotification(notification, item)", notifications)
        self.assertIn("function notificationDestination(notification)", notifications)
        self.assertIn('return "/dashboard#flagged"', notifications)
        self.assertIn('return "/dashboard#appointments:requests"', notifications)
        self.assertIn('return "/appointment"', notifications)
        self.assertIn("const markedRead = await markNotificationRead(notification.id)", notifications)
        self.assertNotIn('markRead.textContent = "Mark as read"', notifications)
        self.assertNotIn('readState.textContent = "Read"', notifications)
        self.assertIn(".notifications-panel--header", stylesheet)
        self.assertIn(".notifications-icon", stylesheet)
        self.assertIn(".notification-item:focus-visible", stylesheet)

    def test_mobile_header_spacing_and_chatbot_status_indicator_are_present(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('id="inbox-status-indicator"', template)
        self.assertIn("const setChatbotStatus", dashboard)
        self.assertIn("chatbot-status-indicator", stylesheet)
        self.assertIn("padding: 14px 16px 14px 72px;", stylesheet)

    def test_manual_appointment_is_a_reachable_section_and_keeps_its_api(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")

        self.assertIn('id="manual-appointment-panel"', template)
        self.assertIn('data-dashboard-section="manual"', template)
        self.assertIn('data-dashboard-section-target="manual"', template)
        self.assertIn('`${API_BASE}/api/appointments/manual`', dashboard)
        self.assertIn('method: "POST"', dashboard)

    def test_section_navigation_is_responsive_and_uses_no_inline_handlers(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('data-dashboard-section-nav="appointments"', template)
        self.assertIn('data-dashboard-section-nav="reports"', template)
        self.assertIn("function bindDashboardSectionNavigation()", dashboard)
        self.assertIn("function restoreDashboardLocation()", dashboard)
        self.assertIn("window.addEventListener(\"hashchange\", restoreDashboardLocation)", dashboard)
        self.assertIn("window.history.pushState({ viewId, sectionId: sectionId || null }, \"\", hash)", dashboard)
        self.assertIn('switchView("inbox", false);', dashboard)
        self.assertIn('id="dashboard-home"', template)
        self.assertIn('aria-label="Go to Inbox home"', template)
        self.assertIn("dashboardHome?.addEventListener", dashboard)
        self.assertIn(".sidebar-home", stylesheet)
        self.assertIn("function setSidebarOpen(open", dashboard)
        self.assertIn('event.key === "Escape"', dashboard)
        self.assertIn('aria-controls="sidebar"', template)
        self.assertIn('id="sidebar-close"', template)
        self.assertNotIn("onclick=", template)
        self.assertIn("@media (max-width: 900px)", stylesheet)
        self.assertIn("@media (max-width: 480px)", stylesheet)

    def test_no_obsolete_frontend_mutations_or_unsafe_manual_search_rendering(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")

        self.assertNotIn("POST /api/inquiries", dashboard)
        self.assertNotIn("PATCH /api/conversation-summaries/", dashboard)
        self.assertIn("name.textContent = student.full_name", dashboard)
        self.assertNotIn("option.innerHTML", dashboard)
        self.assertIn("function appendTableEmptyState", dashboard)

    def test_inbox_uses_summary_projection_without_raw_chat_or_takeover_navigation(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")
        frontend_routes = _read("backend/server/routes/frontend_routes.py")

        self.assertIn("/api/staff/inbox", dashboard)
        self.assertIn("function inboxItemsForCurrentFilter", dashboard)
        self.assertIn("function openInboxItem", dashboard)
        self.assertNotIn("conversation_json", dashboard)
        self.assertNotIn("/api/inquiries", dashboard)
        self.assertNotIn("chatbot_admin", template)
        self.assertNotIn('"/chatbot_admin"', frontend_routes)
        self.assertNotIn("def chatbot_admin", frontend_routes)
        self.assertIn('id="inbox-search-input"', template)
        self.assertIn('id="inbox-filter"', template)

    def test_dashboard_uses_parallel_loads_and_a_targeted_flagged_case_refresh(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")

        self.assertIn("let dashboardLoadPromise = null;", dashboard)
        self.assertIn("async function loadDashboardData()", dashboard)
        self.assertIn("await Promise.all([", dashboard)
        self.assertIn("async function ensureReportsLoaded()", dashboard)
        self.assertIn('if (viewId === "reports")', dashboard)
        self.assertIn("async function refreshReviewableCaseLists()", dashboard)
        self.assertIn("Promise.allSettled([", dashboard)
        self.assertIn("refreshReviewableCaseLists(),", dashboard)
        self.assertIn("openFlaggedConversationDetails(conversation, updatedDetail)", dashboard)
        self.assertNotIn(
            "conversation.status = reviewed.data.escalation_status;\n"
            "        await loadBackendData();",
            dashboard,
        )

    def test_current_reviewed_case_history_item_is_visibly_inactive(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn("const isCurrentCase = String(item.summary_id) === String(summaryId);", dashboard)
        self.assertIn('open.disabled = isCurrentCase;', dashboard)
        self.assertIn('open.textContent = isCurrentCase ? "Current" : "Open";', dashboard)
        self.assertIn(".case-history-row--current", stylesheet)
        self.assertIn(".case-history-actions .action-link:disabled", stylesheet)

    def test_inbox_dashboard_uses_balanced_desktop_layout(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn("min-height: 100dvh", stylesheet)
        self.assertIn("height: 100dvh", stylesheet)
        self.assertIn('class="inbox-toolbar-controls"', template)
        self.assertIn('class="search-box inbox-search-box"', template)
        self.assertIn("max-height: clamp(260px, 36dvh, 460px);", stylesheet)
        self.assertIn(".inbox-table {", stylesheet)
        self.assertIn("table-layout: fixed;", stylesheet)
        self.assertIn(".inbox-table th:nth-child(5)", stylesheet)
        self.assertIn("width: 23%;", stylesheet)
        self.assertRegex(
            stylesheet,
            r"\.inbox-table th:nth-child\(7\),\s*"
            r"\.inbox-table td:nth-child\(7\) \{\s*width: 15%;",
        )
        self.assertRegex(
            stylesheet,
            r"\.inbox-table td:nth-child\(7\) \{[^}]*"
            r"overflow-wrap: anywhere;[^}]*white-space: normal;",
        )
        self.assertRegex(
            stylesheet,
            r"\.inbox-table th:nth-child\(8\),\s*"
            r"\.inbox-table td:nth-child\(8\) \{\s*"
            r"width: 6%;\s*overflow: hidden;",
        )
        self.assertIn("white-space: nowrap;", stylesheet)
        self.assertIn("padding-right: 22px;", stylesheet)
        self.assertIn("line-clamp: 2;", stylesheet)
        self.assertIn(".inbox-table thead th", stylesheet)
        self.assertIn("position: sticky;", stylesheet)
        self.assertIn('row.className = "inbox-record";', dashboard)
        self.assertIn('student.dataset.label = "Student";', dashboard)
        self.assertIn('preview.dataset.label = "Summary Preview";', dashboard)
        self.assertIn('action.dataset.label = "Action";', dashboard)
        self.assertRegex(
            stylesheet,
            r"@media \(max-width: 1279px\) \{\s*"
            r"#view-inbox \.table-wrap \{\s*max-height: none;",
        )
        self.assertIn("min-width: 0;\n    table-layout: auto;", stylesheet)
        self.assertIn("content: attr(data-label);", stylesheet)
        self.assertIn("grid-template-columns: 92px minmax(0, 1fr);", stylesheet)
        self.assertIn(".inbox-table .action-link", stylesheet)

    def test_mobile_sidebar_swaps_hamburger_for_existing_close_button(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('id="sidebar-toggle"', template)
        self.assertIn('id="sidebar-close"', template)
        self.assertIn(
            'document.body.classList.toggle("sidebar-drawer-open", open);',
            dashboard,
        )
        self.assertIn("body.sidebar-drawer-open .sidebar-toggle", stylesheet)
        self.assertIn("width: min(280px, calc(100vw - 44px));", stylesheet)
        self.assertIn("flex: 0 0 44px;", stylesheet)

    def test_dashboard_header_and_stat_cards_keep_consistent_alignment(self) -> None:
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn("padding: 12px 28px;", stylesheet)
        self.assertIn("grid-template-columns: repeat(4, minmax(190px, 1fr));", stylesheet)
        self.assertIn("grid-template-columns: repeat(2, minmax(220px, 1fr));", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", stylesheet)
        self.assertIn("min-height: 100px;", stylesheet)
        self.assertIn("min-height: 32px;", stylesheet)
        self.assertIn("min-height: 40px;", stylesheet)

    def test_reports_page_uses_scoped_compact_analytics_layout(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('id="view-reports"', template)
        self.assertIn('id="reports-overview-kpis"', template)
        self.assertIn("class=\"reports-summary-note\"", template)
        self.assertIn('id="reports-case-priority-graph"', template)
        self.assertIn('id="reports-appointment-status-graph"', template)
        self.assertIn('id="chatbot-analytics-emotion-graph"', template)
        self.assertIn('id="chatbot-analytics-daily-graph"', template)
        self.assertIn('id="counselor-workload-program-graph"', template)
        self.assertIn('id="flagged-case-status-graph"', template)
        self.assertIn("function renderStudentReports()", dashboard)
        self.assertIn("function renderStudentReportGraph", dashboard)
        self.assertIn("Follow-up details", template)
        self.assertIn("Overview Export", template)
        self.assertIn("Download Overview CSV", template)
        self.assertIn("Download Visual Overview", template)
        self.assertIn("function downloadVisualOverview()", dashboard)
        self.assertIn('link.download = "guidance-overview-visual.html"', dashboard)
        self.assertIn('link.download = "guidance-overview-summary.csv"', dashboard)
        self.assertIn('"Student Overview"', dashboard)
        self.assertIn('data-dashboard-section-nav="reports"', template)
        self.assertIn("#view-reports #reports-overview-kpis", stylesheet)
        self.assertIn("#view-reports .dashboard-section-nav", stylesheet)
        self.assertIn("min-height: 34px;", stylesheet)
        self.assertIn("#view-reports .form-grid", stylesheet)
        self.assertIn(
            "grid-template-columns: repeat(2, minmax(170px, 220px)) minmax(260px, 1fr);",
            stylesheet,
        )
        self.assertIn('#view-reports .form-group input[type="date"]', stylesheet)
        self.assertIn("#view-reports .panel > .action-row", stylesheet)
        self.assertIn("#view-reports .inquiry-table", stylesheet)
        self.assertIn("table-layout: fixed;", stylesheet)
        self.assertIn("#view-reports .inquiry-table .table-empty-state", stylesheet)
        self.assertIn("#view-reports [data-dashboard-section] > .stat-grid", stylesheet)

    def test_settings_page_uses_scoped_compact_form_layout(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('id="view-settings"', template)
        self.assertIn('data-dashboard-section-nav="settings"', template)
        self.assertIn('data-dashboard-section-target="global"', template)
        self.assertIn('data-dashboard-section-target="staff"', template)
        self.assertIn('data-dashboard-section="global"', template)
        self.assertIn('data-dashboard-section="staff"', template)
        self.assertIn('settings: "global"', _read("frontend/static/js/dashboard.js"))
        self.assertIn('class="settings-scope settings-scope-global"', template)
        self.assertIn("Global Office Settings", template)
        self.assertIn("Changes here apply to both counselors", template)
        self.assertIn('class="settings-scope settings-scope-personal"', template)
        self.assertIn('class="settings-staff-stack" data-dashboard-section="staff"', template)
        self.assertIn("My Staff Settings", template)
        self.assertIn("currently signed-in counselor", template)
        self.assertIn('class="settings-panel appointment-settings-panel"', template)
        self.assertIn("Shared Appointment Booking Rules", template)
        self.assertIn("Each counselor sets their own", template)
        self.assertIn("My Appointment Availability", template)
        self.assertIn("This applies only to students routed to", template)
        self.assertNotIn('id="appointment-availability-windows"', template)
        self.assertIn('id="counselor-profile-appointment-slots"', template)
        self.assertIn('id="counselor-profile-consultation-modes"', template)
        self.assertNotIn('id="settings-appointment-slots"', template)
        self.assertNotIn('id="settings-consultation-modes"', template)
        self.assertNotIn("appointment-availability-windows", _read("frontend/static/js/dashboard.js"))
        self.assertNotIn(
            "officeAvailability?.some",
            _read("frontend/static/js/appointment.js"),
        )
        self.assertIn('class="settings-panel faq-management-panel"', template)
        self.assertIn('class="settings-panel counselor-profile-panel"', template)
        self.assertIn(
            'class="settings-panel settings-password-panel settings-standalone-panel"',
            template,
        )
        self.assertIn('class="sub password-helper"', template)
        self.assertEqual(template.count("data-settings-collapsible"), 5)
        self.assertEqual(template.count("<summary>"), 5)
        self.assertIn(
            'class="settings-panel" data-settings-collapsible open>', template
        )
        self.assertIn(
            'class="settings-panel counselor-profile-panel"\n'
            '                data-settings-collapsible\n'
            '                open',
            template,
        )
        self.assertNotIn(
            'class="settings-panel appointment-settings-panel"\n'
            '                data-settings-collapsible\n'
            '                open',
            template,
        )
        self.assertNotIn(
            'class="settings-panel faq-management-panel"\n'
            '                data-settings-collapsible\n'
            '                open',
            template,
        )
        self.assertNotIn(
            'id="student-password-panel"\n'
            '                data-settings-collapsible\n'
            '                open',
            template,
        )
        self.assertIn('class="settings-collapsible-body"', template)
        self.assertNotIn('id="student-password-panel"\n              style=', template)
        self.assertNotIn('id="change-password-btn"\n                style=', template)
        self.assertEqual(template.count('id="save-settings-btn"'), 1)
        self.assertIn("Save Global Office Settings", template)
        self.assertEqual(template.count('id="save-counselor-profile"'), 1)
        self.assertIn("Save My Staff Settings", template)
        self.assertIn('class="settings-scope-heading-copy"', template)
        self.assertIn("availability, start times, and consultation modes", template)
        dashboard_script = _read("frontend/static/js/dashboard.js")
        settings_meta = dashboard_script.split('  settings: {', 1)[1].split(
            '  "case-details": {', 1
        )[0]
        self.assertIn('actions: "",', settings_meta)
        self.assertNotIn('data-dashboard-action="save-settings"', dashboard_script)
        self.assertIn("#view-settings .settings-panel", stylesheet)
        self.assertIn("#view-settings .settings-section-nav", stylesheet)
        self.assertIn("#view-settings .settings-scope", stylesheet)
        self.assertIn("#view-settings .settings-scope > * + *", stylesheet)
        self.assertIn("#view-settings .settings-scope-global,", stylesheet)
        self.assertIn("#view-settings [data-dashboard-section][hidden]", stylesheet)
        self.assertIn("#view-settings .settings-scope > .settings-grid", stylesheet)
        self.assertIn("#view-settings .settings-global-actions", stylesheet)
        self.assertIn("#view-settings .settings-scope-heading-copy", stylesheet)
        self.assertIn("#view-settings .settings-standalone-panel", stylesheet)
        self.assertIn("[data-settings-collapsible] > summary", stylesheet)
        self.assertIn(".settings-collapsible-indicator", stylesheet)
        self.assertNotIn("settings-scope-badge", template)
        self.assertNotIn("settings-scope-badge", stylesheet)
        self.assertIn("#view-settings .field-grid-2", stylesheet)
        self.assertIn("grid-template-columns: repeat(2, minmax(220px, 1fr));", stylesheet)
        self.assertIn("#view-settings .appointment-availability-window", stylesheet)
        self.assertIn("#view-settings .counselor-schedule-row", stylesheet)
        self.assertIn("#view-settings .faq-editor-card", stylesheet)
        self.assertIn(
            '#view-settings .faq-active-toggle input[type="checkbox"]',
            stylesheet,
        )
        self.assertIn("accent-color: var(--orange);", stylesheet)
        self.assertIn("#view-settings .settings-password-panel", stylesheet)
        self.assertIn("#view-settings .password-helper", stylesheet)
        self.assertIn("box-shadow: 0 0 0 3px rgba(211, 84, 0, 0.12);", stylesheet)

    def test_staff_sidebar_uses_compact_aligned_flex_layout(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('class="sidebar"', template)
        self.assertIn("height: 100dvh;", stylesheet)
        self.assertIn("overflow-y: auto;", stylesheet)
        self.assertIn("margin-bottom: auto;", stylesheet)
        self.assertIn("min-height: 36px;", stylesheet)
        self.assertIn(".nav-item span:first-child", stylesheet)
        self.assertIn("min-width: 17px;", stylesheet)
        self.assertIn("height: 17px;", stylesheet)
        self.assertIn("#dashboard-logout", stylesheet)

    def test_case_details_layout_preserves_scoped_readable_cards(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('class="case-profile-identity"', template)
        self.assertIn('class="case-profile-heading"', template)
        self.assertIn("#view-case-details .case-layout", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(300px, 340px);", stylesheet)
        self.assertIn("#view-case-details .case-side-panel", stylesheet)
        self.assertIn("min-width: 300px;", stylesheet)
        self.assertIn("#view-case-details .case-message-box", stylesheet)
        self.assertIn("line-height: 1.58;", stylesheet)
        self.assertIn("#view-case-details .case-meta-cell", stylesheet)
        self.assertIn("min-height: 72px;", stylesheet)
        self.assertIn("#view-case-details .insight-row", stylesheet)
        self.assertIn("min-height: 42px;", stylesheet)
        self.assertIn("#view-case-details .case-confidentiality-card", stylesheet)
        self.assertIn("#view-case-details .staff-notes-card textarea", stylesheet)

    def test_flagged_cases_table_matches_compact_dashboard_layout(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        dashboard = _read("frontend/static/js/dashboard.js")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('class="panel flagged-panel"', template)
        self.assertIn('class="inquiry-table flagged-table"', template)
        self.assertIn('id="flagged-filter"', template)
        self.assertIn('id="flagged-search-input"', template)
        self.assertIn('class="stat-grid flagged-stat-grid"', template)
        self.assertIn("flagged-student-name", dashboard)
        self.assertIn("flagged-student-number", dashboard)
        self.assertIn("flagged-summary-preview", dashboard)
        self.assertIn("#view-flagged .flagged-panel > .sub", stylesheet)
        self.assertIn(".flagged-table {", stylesheet)
        self.assertIn("table-layout: fixed;", stylesheet)
        self.assertIn("min-width: 980px;", stylesheet)
        self.assertIn(".flagged-table th:nth-child(2)", stylesheet)
        self.assertIn("width: 10%;", stylesheet)
        self.assertIn(".table-sort", stylesheet)
        self.assertIn(".flagged-stat-grid", stylesheet)
        self.assertIn(".flagged-summary-preview", stylesheet)
        self.assertIn("line-clamp: 2;", stylesheet)
        self.assertIn(".flagged-table .table-empty-state", stylesheet)

    def test_appointments_page_uses_compact_scoped_cards_and_details(self) -> None:
        template = _read("frontend/templates/dashboard.html")
        stylesheet = _read("frontend/static/css/dashboard.css")

        self.assertIn('class="stat-grid appointment-stat-grid"', template)
        self.assertIn('class="panel appointment-panel appointment-list-panel"', template)
        self.assertIn('class="search-box appointment-search-box"', template)
        self.assertIn("#view-appointments .appointment-panel > .sub", stylesheet)
        self.assertIn(".appointment-stat-grid", stylesheet)
        self.assertIn("grid-template-columns: repeat(3, minmax(190px, 1fr));", stylesheet)
        self.assertIn("#view-appointments .form-grid", stylesheet)
        self.assertIn(
            "grid-template-columns: repeat(2, minmax(170px, 220px)) minmax(240px, 1fr);",
            stylesheet,
        )
        self.assertIn('#view-appointments .form-group input[type="date"]', stylesheet)
        self.assertIn("#view-appointments .appointment-card-footer .btn", stylesheet)
        self.assertIn(".appointment-meta-grid", stylesheet)
        self.assertIn("grid-template-columns: repeat(4, minmax(120px, 1fr));", stylesheet)
        self.assertIn("#view-appointment-details .case-layout", stylesheet)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(300px, 340px);", stylesheet)
        self.assertIn("#view-appointment-details .staff-notes-card textarea", stylesheet)

    def test_phone_tablet_desktop_responsive_guardrails_are_present(self) -> None:
        dashboard = _read("frontend/static/css/dashboard.css")
        appointment = _read("frontend/static/css/appointment.css")
        chatbot = _read("frontend/static/css/chatbot.css")
        admin = _read("frontend/static/css/admin.css")

        self.assertIn("@media (max-width: 700px)", dashboard)
        self.assertIn(".dash-main {\n    overflow-x: clip;", dashboard)
        self.assertIn("#view-appointment-details .case-side-panel", dashboard)
        self.assertIn("grid-template-columns: minmax(0, 1fr);", dashboard)
        self.assertIn("#view-appointments .appointment-card-footer .btn", dashboard)

        self.assertIn("overflow-x: hidden;", appointment)
        self.assertIn("min-height: 100dvh;", appointment)
        self.assertIn("@media (max-width: 960px) and (orientation: landscape)", appointment)
        self.assertIn("max-height: calc(100dvh - 32px);", appointment)

        self.assertIn("min-width: 0;", chatbot)
        self.assertIn("@media (max-width: 900px) and (orientation: landscape)", chatbot)
        self.assertIn("max-width: 100vw;", chatbot)

        self.assertIn("max-height: min(90dvh, 900px);", admin)
        self.assertIn(".admin-program-table {", admin)
        self.assertIn("@media (max-width: 900px) and (orientation: landscape)", admin)

    def test_case_staff_actions_match_routine_or_flagged_status(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")

        self.assertIn('id="case-staff-actions-note"', template)
        self.assertIn("No immediate intervention is required.", dashboard)
        self.assertIn(
            "Immediate Guidance Office review is recommended.",
            dashboard,
        )
        chat = _read("frontend/static/js/chat.js")
        safety = _read("backend/server/services/safety_service.py")
        self.assertNotIn("appendEscalationNotice", chat)
        self.assertIn("Your conversation has been referred to the Guidance Office", safety)

    def test_case_details_separates_persisted_emotion_from_safety_risk(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")

        self.assertIn("function displayCaseEmotion(detail)", dashboard)
        self.assertIn("function safetyRiskPresentation(detail)", dashboard)
        self.assertIn("function applySafetyRisk(detail)", dashboard)
        self.assertIn('return capitalize(detail.emotion_results || "Unavailable");', dashboard)
        self.assertIn('id="case-safety-risk"', template)
        self.assertIn("No immediate safety concern", dashboard)
        self.assertIn("Elevated concern", dashboard)
        self.assertIn("Immediate safety concern", dashboard)
        self.assertIn("safety escalation|crisis|self[ -]?harm|suicid|high-risk", dashboard)

    def test_appointment_times_are_controlled_selects_with_touched_validation(self) -> None:
        template = _read("frontend/templates/appointment.html")
        appointment = _read("frontend/static/js/appointment.js")
        dashboard = _read("frontend/static/js/dashboard.js")

        self.assertIn('<select\n                  id="prefTime"'.replace("\\n", "\n"), template)
        self.assertIn('<select\n                id="rescheduleTime"'.replace("\\n", "\n"), template)
        self.assertNotIn('type="text"\n                  id="prefTime"'.replace("\\n", "\n"), template)
        self.assertIn("function populateSlotSelect", appointment)
        self.assertIn("function loadSlotOptions", appointment)
        self.assertIn("const touchedFields = new Set()", appointment)
        self.assertIn("Select an available time slot", appointment)
        self.assertIn("No available time slots for the selected date.", appointment)
        self.assertIn('<select id="manual-appointment-time" disabled>', dashboard)
        self.assertIn("function populateManualSlotSelect", dashboard)

    def test_manual_autocomplete_and_counselor_profile_use_safe_controls(self) -> None:
        dashboard = _read("frontend/static/js/dashboard.js")
        template = _read("frontend/templates/dashboard.html")

        self.assertIn("Search by name, student number, or email", dashboard)
        self.assertIn("manual-student-search-results", dashboard)
        self.assertIn("studentSearchResults.addEventListener(\"keydown\"", dashboard)
        self.assertIn("student_number: selectedStudent.student_number", dashboard)
        self.assertNotIn("account_id: selectedStudent.id", dashboard)
        self.assertIn("My Counselor Profile", template)
        self.assertIn("counselor-profile-rooms", template)
        self.assertIn("counselor-schedule-list", template)

    def test_chat_message_pane_keeps_footer_controls_in_the_flex_layout(self) -> None:
        template = _read("frontend/templates/chatbot.html")
        chat = _read("frontend/static/js/chat.js")
        stylesheet = _read("frontend/static/css/chatbot.css")

        self.assertIn('id="chat-area"', template)
        self.assertIn('id="quick-replies"', template)
        self.assertIn('class="input-bar"', template)
        self.assertIn('class="header-actions"', template)
        self.assertIn('data-notifications-mount', template)
        self.assertIn(".chat-area {\n  flex: 1;\n  min-height: 0;", stylesheet)
        self.assertIn(".quick-replies {\n  display: flex;", stylesheet)
        self.assertIn(".chatbot-page {\n  overflow: hidden;", stylesheet)
        self.assertIn("height: var(--chat-visible-height, 100dvh);", stylesheet)
        self.assertIn("overscroll-behavior-y: contain;", stylesheet)
        self.assertIn("font-size: 16px;", stylesheet)
        self.assertIn('class="chatbot-page"', template)
        self.assertIn(
            'maximum-scale=1.0, user-scalable=no, viewport-fit=cover',
            template,
        )
        self.assertIn("height: 100dvh;", stylesheet)
        self.assertIn("touch-action: manipulation;", stylesheet)
        self.assertIn("data-quick-message", template)
        self.assertNotIn("qrBar.style.display", chat)
        self.assertIn('id="active-chat-state"', template)
        self.assertIn('document.getElementById("active-chat-state")', chat)
        self.assertIn("restoreVisibleChat(activeChat)", chat)
        self.assertIn("function setChatTurnPending(isPending)", chat)
        self.assertIn("if (isAwaitingReply || input.disabled) return;", chat)
        self.assertEqual(chat.count('aria-label="CTRL4 assistant">🦊</div>'), 2)

        self.assertIn("MIN_NORMAL_REPLY_TYPING_MS = 1200", chat)
        self.assertIn("MAX_NORMAL_REPLY_TYPING_MS = 2200", chat)
        self.assertIn("if (!result.escalated)", chat)
        self.assertIn("await waitForMinimumTypingTime", chat)
        self.assertIn("Safety replies must never wait", chat)
        self.assertIn("function syncChatVisibleViewport()", chat)
        self.assertIn("let lastViewportMetrics = {};", chat)
        self.assertIn("Apply each viewport event immediately", chat)
        self.assertNotIn("let viewportSyncFrame = null;", chat)
        self.assertIn('"--chat-visible-offset-top"', chat)
        self.assertIn('"--chat-visible-offset-left"', chat)
        self.assertIn("window.visualViewport?.addEventListener(\"resize\"", chat)
        self.assertIn("var(--chat-visible-offset-top, 0px)", stylesheet)
        self.assertIn("var(--chat-visible-offset-left, 0px)", stylesheet)
        self.assertIn("bindChatVisibleViewport();", chat)
        self.assertIn("function dismissMobileKeyboardFromChat(event)", chat)
        self.assertIn('?.addEventListener("click", dismissMobileKeyboardFromChat)', chat)
        self.assertIn("Use a completed click rather than", chat)
        self.assertIn('event.target.closest("button, a, input, textarea', chat)
        self.assertIn("input.blur();", chat)
        self.assertIn("bindMobileKeyboardDismissal();", chat)
        self.assertIn('autocomplete="off"', template)
        self.assertIn('enterkeyhint="send"', template)
        self.assertIn("touch-action: pan-y;", stylesheet)
        self.assertIn(".send-btn:disabled", stylesheet)
        self.assertIn(".qr-btn:disabled", stylesheet)
        self.assertIn("max-width: min(88%, calc(100% - 40px));", stylesheet)
        self.assertIn("env(safe-area-inset-bottom)", stylesheet)
        self.assertIn("@media (max-width: 560px) {\n  .page {\n    height: 100vh;\n    height: 100dvh;", stylesheet)
        self.assertIn("@media (max-width: 360px)", stylesheet)
        self.assertNotIn("localStorage.setItem", chat)
        self.assertNotIn("sessionStorage.setItem", chat)
        self.assertIn('transient_chat_service.clear(getattr(session, "sid", ""), user.get("id"))', _read("backend/server/auth.py"))
        self.assertIn('response.headers["Cache-Control"] = "no-store"', _read("backend/server/routes/frontend_routes.py"))

    def test_student_idle_chat_finalizes_before_sign_out_without_changing_staff_sessions(self) -> None:
        chat = _read("frontend/static/js/chat.js")
        auth = _read("frontend/static/js/auth.js")
        student_guide = _read("docs/guides/student_guide.md")

        self.assertIn("const STUDENT_INACTIVITY_TIMEOUT = 20 * 60 * 1000;", chat)
        self.assertIn("function checkInactivityAfterVisibilityChange()", chat)
        self.assertIn('document.addEventListener("visibilitychange", checkInactivityAfterVisibilityChange);', chat)
        self.assertIn("const finalized = await finalizeConversation({ resetUI: false });", chat)
        self.assertIn("finalize: false,", chat)
        self.assertIn('reason: "inactive",', chat)
        self.assertIn("window.endAuthenticatedSession = endAuthenticatedSession;", auth)
        self.assertIn("server-owned inactivity finalizer", student_guide)

    def test_terms_dialog_is_centered_in_the_viewport(self) -> None:
        stylesheet = _read("frontend/static/css/chatbot.css")

        self.assertIn(
            ".terms-dialog {\n  position: fixed;\n  inset: 0;\n  margin: auto;",
            stylesheet,
        )

    def test_successful_student_registration_hides_the_completed_form(self) -> None:
        template = _read("frontend/templates/student_registration.html")
        stylesheet = _read("frontend/static/css/login.css")

        self.assertIn('form.hidden = true;', template)
        self.assertIn('successBox.hidden = false;', template)
        self.assertIn(".login-notice[hidden]", stylesheet)
        self.assertIn(".login-form[hidden]", stylesheet)
        self.assertIn("display: none !important;", stylesheet)


if __name__ == "__main__":
    unittest.main()
