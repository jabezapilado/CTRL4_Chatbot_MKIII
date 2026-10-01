import unittest
from pathlib import Path
from flask import Flask
from unittest.mock import patch

from backend.server.services import conversation_service


ROOT = Path(__file__).resolve().parents[1]


class ConversationServiceTests(unittest.TestCase):
    @staticmethod
    def _staff_account(programs):  # type: ignore[no-untyped-def]
        return {"id": 3, "role": "staff", "assigned_programs": programs}

    @staticmethod
    def _inbox_row(summary_id, student_number, program="BSCS", **updates):  # type: ignore[no-untyped-def]
        row = {
            "summary_id": summary_id,
            "student_name": f"Student {student_number}",
            "student_number": student_number,
            "program": program,
            "primary_concern": "academic",
            "emotion_results": "neutral",
            "flagged_status": False,
            "recommendations": "Approved recommendation.",
            "suggested_intervention": None,
            "language_used": "english",
            "total_messages": 4,
            "summary": "Approved AI summary.",
            "created_at": f"2026-08-06T10:0{summary_id}:00",
            "escalation_status": None,
            "has_referral": False,
            "has_intervention": False,
            "conversation_json": [{"from": "user", "text": "private"}],
            "account_id": 99,
        }
        row.update(updates)
        return row

    def test_inbox_groups_repeated_summary_rows_per_student(self):
        rows = [
            self._inbox_row(12, "2026-00001", summary="Newest summary."),
            self._inbox_row(11, "2026-00001", summary="Older summary."),
            self._inbox_row(13, "2026-00002", program="BSIT"),
        ]
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS", "BSIT"]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
            return_value=rows,
        ):
            items = conversation_service.list_staff_inbox_items({"id": 3})

        self.assertEqual([item["summary_id"] for item in items], [12, 13])
        self.assertEqual(len(items), 2)
        self.assertNotIn("conversation_json", items[0])
        self.assertNotIn("account_id", items[0])

    def test_inbox_query_prioritizes_pending_flagged_cases_over_newer_routine_summaries(self):
        source = (ROOT / "backend/server/db.py").read_text(encoding="utf-8")
        self.assertIn("pending_escalations.status = 'pending'", source)
        self.assertIn("selected_summary_id", source)

    def test_staff_case_priority_is_derived_from_existing_safety_state(self):
        critical = self._inbox_row(
            21,
            "2026-00021",
            flagged_status=True,
            escalation_reason="AI safety escalation.",
        )
        high = self._inbox_row(
            22,
            "2026-00022",
            flagged_status=True,
            escalation_reason="Warning sign requires Guidance Office review.",
        )
        active = self._inbox_row(23, "2026-00023", conversation_type="active")
        routine = self._inbox_row(24, "2026-00024")

        self.assertEqual(conversation_service._case_priority(critical), "critical")
        self.assertEqual(conversation_service._case_priority(high), "high")
        self.assertEqual(conversation_service._case_priority(active), "medium")
        self.assertEqual(conversation_service._case_priority(routine), "low")

    def test_inbox_query_keeps_a_reviewed_case_until_a_later_summary_exists(self):
        source = (ROOT / "backend/server/db.py").read_text(encoding="utf-8")
        self.assertIn("reviewed_escalations.status = 'reviewed'", source)
        self.assertIn("later_summaries.created_at > reviewed_escalations.reviewed_at", source)

    def test_inbox_fails_closed_for_unassigned_staff_programs(self):
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account([]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
        ) as list_inbox:
            items = conversation_service.list_staff_inbox_items({"id": 3})

        self.assertEqual(items, [])
        list_inbox.assert_not_called()

    def test_flagged_case_list_keeps_reviewed_cases_scoped_to_staff_programs(self):
        pending = self._inbox_row(
            41,
            "2026-00011",
            flagged_status=True,
            escalation_status="pending",
        )
        reviewed = self._inbox_row(
            39,
            "2026-00011",
            flagged_status=True,
            escalation_status="reviewed",
        )
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_flagged_case_summaries",
            return_value=[pending, reviewed],
        ) as list_cases:
            items = conversation_service.list_staff_flagged_case_items({"id": 3})

        list_cases.assert_called_once_with(["bscs"])
        self.assertEqual([item["summary_id"] for item in items], [41, 39])
        self.assertEqual(
            [item["review_status"] for item in items], ["pending", "reviewed"]
        )
        self.assertTrue(all(item["flagged_status"] for item in items))

    def test_flagged_case_query_is_program_scoped_and_retains_reviewed_cases(self):
        source = (ROOT / "backend/server/db.py").read_text(encoding="utf-8")
        self.assertIn("def list_staff_flagged_case_summaries", source)
        self.assertIn("escalations.status IN ('pending', 'reviewed')", source)
        self.assertIn("accounts.program IN ({placeholders})", source)

    def test_chatbot_feedback_is_program_scoped_and_excludes_raw_chat_fields(self):
        feedback_row = {
            "feedback_id": 41,
            "conversation_summary_id": 28,
            "student_name": "Student 2026-00005",
            "student_number": "2026-00005",
            "program": "BSCS",
            "category": "not_helpful",
            "comment": "Too generic.",
            "response_context": "academics",
            "created_at": "2026-08-10T10:00:00",
            "response_text": "Private assistant text",
            "student_message": "Private student text",
        }
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_chatbot_feedback_for_programs",
            return_value=[feedback_row],
        ) as list_feedback:
            items = conversation_service.list_staff_chatbot_feedback({"id": 3})

        list_feedback.assert_called_once_with(["bscs"])
        self.assertEqual(items[0]["feedback_id"], 41)
        self.assertEqual(items[0]["comment"], "Too generic.")
        self.assertEqual(items[0]["response_context"], "academics")
        self.assertNotIn("response_text", items[0])
        self.assertNotIn("student_message", items[0])

    def test_chatbot_feedback_insights_group_non_helpful_ratings_by_safe_context(self):
        insights = conversation_service.summarize_staff_chatbot_feedback(
            [
                {"category": "helpful", "response_context": "academics"},
                {"category": "not_helpful", "response_context": "academics"},
                {"category": "not_helpful", "response_context": "academics"},
                {"category": "safety_concern", "response_context": "safety"},
            ]
        )

        self.assertEqual(insights["total"], 4)
        self.assertEqual(insights["needs_attention"], 3)
        self.assertEqual(insights["safety_concerns"], 1)
        self.assertEqual(
            insights["patterns"][0],
            {"category": "not_helpful", "response_context": "academics", "count": 2},
        )

    def test_inbox_detail_denies_out_of_scope_and_projects_summary_only(self):
        row = self._inbox_row(18, "2026-00003", program="BSIT", summary="")
        with patch.object(
            conversation_service,
            "fetch_staff_inbox_summary",
            return_value=row,
        ), patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ):
            denied = conversation_service.get_staff_inbox_item({"id": 3}, 18)

        self.assertIsNone(denied)

        with patch.object(
            conversation_service,
            "fetch_staff_inbox_summary",
            return_value=row,
        ), patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSIT"]),
        ):
            detail = conversation_service.get_staff_inbox_item({"id": 3}, 18)

        self.assertIn("could not be generated", detail["summary"])
        self.assertNotIn("conversation_json", detail)
        self.assertNotIn("account_id", detail)

    def test_flagged_transcript_is_staff_scoped_and_projects_only_messages(self):
        row = self._inbox_row(
            18,
            "2026-00003",
            program="BSIT",
            flagged_status=True,
            escalation_status="pending",
        )
        transcript = {
            "transcript_json": (
                '[{"role":"user","content":"I need help."},'
                '{"role":"assistant","content":"I am here with you."},'
                '{"role":"system","content":"internal"}]'
            )
        }
        with patch.object(
            conversation_service,
            "fetch_staff_inbox_summary",
            return_value=row,
        ), patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSIT"]),
        ), patch.object(
            conversation_service,
            "fetch_flagged_conversation_transcript",
            return_value=transcript,
        ) as fetch_transcript:
            items = conversation_service.get_staff_flagged_case_transcript(
                {"id": 3},
                18,
            )

        fetch_transcript.assert_called_once_with(18)
        self.assertEqual(
            items,
            [
                {"role": "student", "content": "I need help."},
                {"role": "assistant", "content": "I am here with you."},
            ],
        )

        with patch.object(
            conversation_service,
            "fetch_staff_inbox_summary",
            return_value=row,
        ), patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "fetch_flagged_conversation_transcript",
        ) as denied_fetch:
            denied = conversation_service.get_staff_flagged_case_transcript(
                {"id": 3},
                18,
            )

        self.assertIsNone(denied)
        denied_fetch.assert_not_called()

    def test_transcript_persistence_uses_only_server_owned_conversation_evidence(self):
        with patch.object(
            conversation_service,
            "save_flagged_conversation_transcript",
        ) as save_transcript:
            conversation_service.save_flagged_case_transcript(
                21,
                [
                    {"role": "assistant", "content": "Welcome."},
                    {"role": "user", "content": "I need help."},
                    {"role": "assistant", "content": "I am here with you."},
                ],
            )

        save_transcript.assert_called_once_with(
            21,
            [
                {"role": "user", "content": "I need help."},
                {"role": "assistant", "content": "I am here with you."},
            ],
        )

    def test_inbox_uses_case_level_review_status(self):
        row = self._inbox_row(
            21,
            "2026-00004",
            flagged_status=True,
            escalation_status="pending",
        )
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
            return_value=[row],
        ):
            item = conversation_service.list_staff_inbox_items({"id": 3})[0]

        self.assertEqual(item["review_status"], "pending")
        self.assertTrue(item["flagged_status"])

    def test_active_placeholder_is_visible_without_an_ai_summary(self):
        active = self._inbox_row(
            28,
            "2026-00005",
            conversation_type="active",
            primary_concern="Conversation in progress",
            emotion_results="Pending",
            summary="Conversation in progress",
            total_messages=0,
        )
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
            return_value=[active],
        ):
            item = conversation_service.list_staff_inbox_items({"id": 3})[0]

        self.assertEqual(item["summary_id"], 28)
        self.assertEqual(item["review_status"], "active")
        self.assertEqual(item["summary_preview"], "Conversation in progress")
        self.assertFalse(item["flagged_status"])

    def test_active_placeholder_is_not_hidden_by_an_older_pending_flagged_case(self):
        pending = self._inbox_row(
            27,
            "2026-00005",
            flagged_status=True,
            escalation_status="pending",
        )
        active = self._inbox_row(
            28,
            "2026-00005",
            conversation_type="active",
            primary_concern="Conversation in progress",
            summary="Conversation in progress",
        )
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
            return_value=[pending, active],
        ):
            items = conversation_service.list_staff_inbox_items({"id": 3})

        self.assertEqual([item["summary_id"] for item in items], [27, 28])
        self.assertEqual(items[0]["review_status"], "pending")
        self.assertEqual(items[1]["review_status"], "active")

    def test_active_placeholder_with_a_pending_escalation_is_pending_review(self):
        active_crisis = self._inbox_row(
            28,
            "2026-00005",
            conversation_type="active",
            flagged_status=True,
            escalation_status="pending",
        )
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_inbox_summaries",
            return_value=[active_crisis],
        ):
            item = conversation_service.list_staff_inbox_items({"id": 3})[0]

        self.assertTrue(item["flagged_status"])
        self.assertEqual(item["review_status"], "pending")

    def test_reviewed_case_history_preserves_multiple_cases_when_routine_is_current(self):
        routine_current = self._inbox_row(
            41,
            "2026-00004",
            flagged_status=False,
            escalation_status=None,
        )
        reviewed_rows = [
            {
                "summary_id": 39,
                "student_name": "Student 2026-00004",
                "student_number": "2026-00004",
                "program": "BSCS",
                "primary_concern": "crisis",
                "emotion_results": "Crisis",
                "flagged_status": True,
                "summary": "Earlier reviewed crisis summary.",
                "created_at": "2026-08-05T10:00:00",
                "escalation_status": "reviewed",
                "reviewed_at": "2026-08-05T11:00:00",
                "account_id": 99,
                "conversation_json": [{"text": "private"}],
            },
            {
                "summary_id": 37,
                "student_name": "Student 2026-00004",
                "student_number": "2026-00004",
                "program": "BSCS",
                "primary_concern": "safety",
                "emotion_results": "Crisis",
                "flagged_status": True,
                "summary": "Older reviewed safety summary.",
                "created_at": "2026-08-04T10:00:00",
                "escalation_status": "reviewed",
                "reviewed_at": "2026-08-04T11:00:00",
                "account_id": 99,
                "conversation_json": [{"text": "private"}],
            },
        ]
        with patch.object(
            conversation_service,
            "get_staff_inbox_item",
            return_value=routine_current,
        ), patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_staff_reviewed_case_history_rows",
            return_value=reviewed_rows,
        ) as list_history:
            history = conversation_service.list_staff_reviewed_case_history(
                {"id": 3},
                41,
            )

        self.assertEqual([item["summary_id"] for item in history], [39, 37])
        self.assertEqual(history[0]["review_status"], "reviewed")
        self.assertEqual(history[0]["reviewed_at"], "2026-08-05T11:00:00")
        self.assertNotIn("account_id", history[0])
        self.assertNotIn("conversation_json", history[0])
        self.assertNotIn("summary", history[0])
        list_history.assert_called_once_with(41, ["bscs"])

    def test_reviewed_case_history_fails_closed_when_anchor_is_out_of_scope(self):
        with patch.object(
            conversation_service,
            "get_staff_inbox_item",
            return_value=None,
        ), patch.object(
            conversation_service,
            "list_staff_reviewed_case_history_rows",
        ) as list_history:
            history = conversation_service.list_staff_reviewed_case_history(
                {"id": 3},
                41,
            )

        self.assertIsNone(history)
        list_history.assert_not_called()

    def test_flagged_case_analytics_retains_reviewed_history(self):
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=self._staff_account(["BSCS"]),
        ), patch.object(
            conversation_service,
            "list_flagged_case_statuses_for_analytics",
            return_value=[{"status": "reviewed"}],
        ), patch.object(
            conversation_service,
            "list_flagged_case_referrals_for_analytics",
            return_value=[],
        ), patch.object(
            conversation_service,
            "list_flagged_case_interventions_for_analytics",
            return_value=[],
        ), patch.object(
            conversation_service,
            "list_flagged_case_confidentiality_for_analytics",
            return_value=[],
        ), patch.object(
            conversation_service,
            "list_flagged_case_escalations_for_analytics",
            return_value=[],
        ):
            analytics = conversation_service.get_flagged_case_analytics_service({"id": 3})

        self.assertEqual(analytics["total_flagged_cases"], 1)
        self.assertEqual(analytics["pending_flagged_case_reviews"], 0)
        self.assertEqual(analytics["reviewed_flagged_cases"], 1)

    def test_analytics_and_dashboard_stats_use_the_staff_program_scope(self):
        profile = self._staff_account(["BSCS"])
        with patch.object(
            conversation_service,
            "fetch_account_by_id",
            return_value=profile,
        ), patch.object(
            conversation_service,
            "list_chatbot_inquiries_for_analytics",
            return_value=[],
        ) as inquiries, patch.object(
            conversation_service,
            "list_conversation_finalizations_for_analytics",
            return_value=[],
        ) as finalizations, patch.object(
            conversation_service,
            "list_escalations_for_analytics",
            return_value=[],
        ) as chatbot_escalations, patch.object(
            conversation_service,
            "list_flagged_case_statuses_for_analytics",
            return_value=[],
        ) as statuses, patch.object(
            conversation_service,
            "list_flagged_case_referrals_for_analytics",
            return_value=[],
        ) as referrals, patch.object(
            conversation_service,
            "list_flagged_case_interventions_for_analytics",
            return_value=[],
        ) as interventions, patch.object(
            conversation_service,
            "list_flagged_case_confidentiality_for_analytics",
            return_value=[],
        ) as confidentiality, patch.object(
            conversation_service,
            "list_flagged_case_escalations_for_analytics",
            return_value=[],
        ) as flagged_escalations, patch.object(
            conversation_service,
            "get_dashboard_stats",
            return_value={},
        ) as stats:
            conversation_service.get_chatbot_analytics_service({"id": 3})
            conversation_service.get_flagged_case_analytics_service({"id": 3})
            conversation_service.get_staff_dashboard_stats({"id": 3})

        for query in (inquiries, finalizations, chatbot_escalations):
            self.assertEqual(query.call_args.args[2], ["bscs"])
        for query in (
            statuses,
            referrals,
            interventions,
            confidentiality,
            flagged_escalations,
        ):
            self.assertEqual(query.call_args.args[2], ["bscs"])
        stats.assert_called_once_with(["bscs"])

    def test_staff_inbox_routes_require_staff_and_keep_standard_envelopes(self):
        from backend.server.routes.conversation_routes import conversation_bp

        app = Flask(__name__)
        app.secret_key = "conversation-route-test"
        app.register_blueprint(conversation_bp)

        def client_for(role):  # type: ignore[no-untyped-def]
            client = app.test_client()
            with client.session_transaction() as session:
                session["hau_user"] = {
                    "id": 3,
                    "email": f"{role}@example.test",
                    "role": role,
                }
            return client

        item = {
            "summary_id": 30,
            "student_name": "Student One",
            "student_number": "2026-00001",
            "program": "BSCS",
            "primary_concern": "academic",
            "review_status": "routine",
            "summary_preview": "Approved summary.",
        }
        with patch.object(
            conversation_service,
            "list_staff_inbox_items",
            return_value=[item],
        ), patch.object(
            conversation_service,
            "get_staff_inbox_item",
            return_value=item,
        ):
            from backend.server.routes import conversation_routes

            with patch.object(
                conversation_routes,
                "list_staff_inbox_items",
                return_value=[item],
            ), patch.object(
                conversation_routes,
                "get_staff_inbox_item",
                return_value=item,
            ):
                response = client_for("staff").get("/api/staff/inbox")
                detail = client_for("staff").get("/api/staff/inbox/30")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["data"]["items"], [item])
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.headers.get("Cache-Control"), "no-store")

        self.assertEqual(client_for("student").get("/api/staff/inbox").status_code, 403)
        self.assertEqual(client_for("admin").get("/api/staff/inbox").status_code, 403)

    def test_flagged_route_returns_pending_and_reviewed_program_scoped_cases(self):
        from backend.server.routes.conversation_routes import conversation_bp
        from backend.server.routes import conversation_routes

        app = Flask(__name__)
        app.secret_key = "flagged-route-test"
        app.register_blueprint(conversation_bp)
        client = app.test_client()
        with client.session_transaction() as session:
            session["hau_user"] = {
                "id": 3,
                "email": "staff@example.test",
                "role": "staff",
            }

        reviewed = {
            "summary_id": 32,
            "flagged_status": True,
            "review_status": "reviewed",
        }
        pending = {
            "summary_id": 33,
            "flagged_status": True,
            "review_status": "pending",
        }
        with patch.object(
            conversation_routes,
            "list_staff_flagged_case_items",
            return_value=[pending, reviewed],
        ):
            response = client.get("/api/flagged-conversations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["items"], [pending, reviewed])
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_staff_detail_excludes_transcript_and_linkage_fields(self):
        row = {
            "id": 8,
            "account_id": 42,
            "summary_id": 8,
            "primary_concern": "mental_health",
            "conversation_type": "general",
            "emotion_results": "distressed",
            "appointment_recommendation": "Guidance Office follow-up",
            "recommendations": "Contact the Guidance Office.",
            "suggested_intervention": "Contact the Guidance Office.",
            "language_used": "english",
            "total_messages": 2,
            "summary": "A confidential summary.",
            "created_at": "2026-08-05T10:00:00",
            "escalation_status": "pending",
            "escalation_reason": "Detected distressed emotion.",
            "reviewed_at": None,
        }

        with patch.object(
            conversation_service,
            "fetch_flagged_conversation",
            return_value=row,
        ):
            conversation = conversation_service.get_staff_flagged_conversation(8)

        self.assertNotIn("account_id", conversation)
        self.assertNotIn("summary_id", conversation)
        self.assertNotIn("transcript", conversation)

    def test_normalized_emotion_does_not_create_an_escalation_reason(self):
        reason = conversation_service.determine_escalation_reason(
            escalated=False,
            normalized_emotion="distressed",
        )

        self.assertIsNone(reason)
        self.assertFalse(
            conversation_service.should_escalate_conversation(
                escalated=False,
                normalized_emotion="distressed",
            )
        )
        self.assertTrue(
            conversation_service.should_escalate_conversation(
                escalated=True,
                normalized_emotion="negative",
            )
        )

    def test_review_is_idempotent_for_an_already_reviewed_conversation(self):
        reviewed = {"id": 8, "escalation_status": "reviewed"}

        with patch.object(
            conversation_service,
            "get_staff_flagged_conversation",
            return_value=reviewed,
        ) as get_conversation, patch.object(
            conversation_service,
            "mark_escalation_reviewed",
        ) as mark_reviewed:
            result = conversation_service.mark_staff_flagged_conversation_reviewed(8)

        self.assertEqual(result, reviewed)
        get_conversation.assert_called_once_with(8)
        mark_reviewed.assert_not_called()

    def test_review_rejects_non_pending_escalation(self):
        with patch.object(
            conversation_service,
            "get_staff_flagged_conversation",
            return_value={"id": 8, "escalation_status": "resolved"},
        ), self.assertRaisesRegex(
            ValueError,
            "cannot be marked as reviewed",
        ):
            conversation_service.mark_staff_flagged_conversation_reviewed(8)


if __name__ == "__main__":
    unittest.main()
