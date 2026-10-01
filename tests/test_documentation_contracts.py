"""Lightweight current-documentation contracts for Issue #74."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _read(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8")


class DocumentationContractTests(unittest.TestCase):
    def test_current_docs_keep_canonical_roles_and_appointment_statuses(self) -> None:
        current = "\n".join(
            _read(name)
            for name in (
                "architecture/project_architecture.md",
                "architecture/security_architecture.md",
                "architecture/api_reference.md",
                "architecture/project_context.md",
            )
        )

        for role in ("student", "staff", "admin"):
            self.assertIn(f"`{role}`", current)

        for status in ("pending", "confirmed", "cancelled", "rejected", "completed"):
            self.assertIn(f"`{status}`", current)

        self.assertIn("interval-overlap", _read("architecture/project_architecture.md"))
        self.assertNotIn("approved →", _read("architecture/project_architecture.md"))
        self.assertNotIn("did_not_attend", _read("architecture/api_reference.md"))

    def test_api_reference_covers_current_route_inventory(self) -> None:
        reference = _read("architecture/api_reference.md")
        endpoints = (
            "/auth/login",
            "/auth/logout",
            "/health",
            "/api/accounts",
            "/api/accounts/search",
            "/api/accounts/staff/<account_id>",
            "/api/accounts/admin/<account_id>",
            "/api/appointments",
            "/api/appointments/my",
            "/api/appointments/my/<appointment_id>/cancel",
            "/api/appointments/my/<appointment_id>/reschedule",
            "/api/appointments/manual",
            "/api/appointments/<appointment_id>",
            "/api/appointments/<appointment_id>/notes",
            "/chat",
            "/chat/feedback",
            "/chat/finalize",
            "/api/notifications",
            "/api/notifications/<notification_id>/read",
            "/api/settings",
            "/api/staff/chatbot-feedback",
            "/api/staff/inbox/<summary_id>/history",
            "/api/inquiries",
            "/api/conversation-summaries",
            "/api/escalations",
            "/api/flagged-conversations",
            "/api/flagged-conversations/<summary_id>",
            "/api/flagged-conversations/<summary_id>/transcript",
            "/api/flagged-conversations/<summary_id>/review",
            "/api/flagged-conversations/<summary_id>/confidentiality",
            "/api/flagged-conversations/<summary_id>/notes",
            "/api/flagged-conversations/<summary_id>/notes/<note_id>",
            "/api/flagged-conversations/<summary_id>/referrals",
            "/api/flagged-conversations/<summary_id>/referrals/<referral_id>/status",
            "/api/flagged-conversations/<summary_id>/referrals/<referral_id>/notes",
            "/api/flagged-conversations/<summary_id>/interventions",
            "/api/flagged-conversations/<summary_id>/interventions/<intervention_id>/progress",
            "/api/flagged-conversations/<summary_id>/interventions/<intervention_id>/outcome",
            "/api/dashboard/appointments/analytics",
            "/api/dashboard/chatbot/analytics",
            "/api/dashboard/counselor-workload",
            "/api/dashboard/flagged-cases/analytics",
            "/api/dashboard/stats",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.assertIn(f"`{endpoint}", reference)

    def test_current_docs_do_not_make_prohibited_current_claims(self) -> None:
        current = "\n".join(
            _read(name)
            for name in (
                "architecture/project_architecture.md",
                "architecture/security_architecture.md",
                "architecture/api_reference.md",
                "guides/student_guide.md",
                "guides/guidance_staff_guide.md",
                "guides/administrator_guide.md",
            )
        )

        prohibited_claims = (
            "Administrators may manage reports",
            "Administrators may configure the system",
            "Administrators may oversee flagged cases",
            "client-side signed-cookie session storage",
            "historical intent distribution",
            "historical topic distribution",
            "normalized historical emotion distribution",
        )
        for claim in prohibited_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, current)

        self.assertIn("retained only for flagged cases", current)
        self.assertIn("client-side CSV", current)

    def test_documentation_index_uses_current_locations(self) -> None:
        index = _read("README.md")
        required_links = (
            "architecture/project_architecture.md",
            "architecture/security_architecture.md",
            "architecture/api_reference.md",
            "architecture/project_context.md",
            "deployment/installation_guide.md",
            "deployment/deployment_guide.md",
            "guides/student_guide.md",
            "guides/guidance_staff_guide.md",
            "guides/administrator_guide.md",
            "research/emotion_label_lineage_report.md",
            "models/README.md",
            "roadmap/mkiii_roadmap.md",
            "archive/README.md",
        )
        for link in required_links:
            with self.subTest(link=link):
                self.assertIn(f"]({link})", index)

        old_current_paths = (
            "01_project_architecture.md",
            "06_deployment_guide.md",
            "10_security_architecture.md",
            "API_REFERENCE.md",
            "INSTALLATION_GUIDE.md",
            "PROJECT_CONTEXT.md",
        )
        for path in old_current_paths:
            with self.subTest(path=path):
                self.assertFalse((DOCS / path).exists())


if __name__ == "__main__":
    unittest.main()
