"""Opt-in performance and reliability checks for GitHub Issue #72.

This suite uses only a newly created, explicitly named isolated MySQL database.
It refuses the configured development database and never drops or truncates a
database.  Run it in a fresh process so configuration is loaded from the
environment before the Flask application is imported:

    CTRL4_RUN_PERFORMANCE_TESTS=1 \\
    CTRL4_PERFORMANCE_DB=ctrl4_perf_issue72_YYYYMMDD \\
    CHATBOT_DB_NAME=ctrl4_perf_issue72_YYYYMMDD \\
    ./.venv/bin/python -m unittest tests.test_performance_reliability_runtime -v

The database must not already contain tables.  The suite creates the current
schema, seeds synthetic records at the Issue #72 representative scale, and
leaves the isolated database intact for post-run inspection.
"""

from __future__ import annotations

import json
import math
import os
import re
import resource
import statistics
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "backend" / "sql" / "schema.sql"
PERFORMANCE_DATABASE_PREFIX = "ctrl4_perf_"
PERFORMANCE_PASSWORD = "performance-test-password"
PROGRAMS = (
    "BS Computer Science",
    "BS Information Technology - Web Development",
    "BS Information Technology - Network Administration",
    "BS Cybersecurity",
    "BS EMC - Digital Animation",
)


def _percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * 0.95) - 1]


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "median_ms": round(statistics.median(values) * 1000, 2),
        "p95_ms": round(_percentile_95(values) * 1000, 2),
        "samples": len(values),
    }


class _FakeLanguage:
    def detect(self, _message: str):
        from backend.server.services.language_service import LanguagePrediction

        return LanguagePrediction(language="english", confidence=1.0)


class _FakeSafety:
    def check(self, message: str, *, language: str):
        from backend.server.services.safety_service import SafetyResult

        if message == "PERFORMANCE_SAFETY_SHORT_CIRCUIT":
            return SafetyResult(
                safe=False,
                should_escalate=True,
                response="Performance safety response.",
                reason="performance_test",
            )
        return SafetyResult(safe=True, should_escalate=False)


class _FakeEmotion:
    def predict(self, _message: str):
        from backend.server.services.emotion_service import EmotionPrediction

        return EmotionPrediction(
            emotion="Neutral",
            sentiment="Neutral",
            confidence=1.0,
            is_negative=False,
            normalized_emotion="neutral",
        )


class _FakeRag:
    ready = False

    def retrieve(self, _message: str):
        return []


class _FakePromptBuilder:
    def build(self, _input: object) -> str:
        return "deterministic performance-test prompt"


class _FakeProvider:
    """A deterministic test-only provider; no external LLM is contacted."""

    def generate(self, _prompt: str):
        from backend.server.llm_providers.base_provider import LLMResponse

        return LLMResponse(
            success=True,
            text="This is a deterministic safe chatbot response for testing.",
        )


class _FakeLLM:
    def __init__(self) -> None:
        self.provider = _FakeProvider()

    def generate(self, prompt: str):
        return self.provider.generate(prompt)


class _FakeIntent:
    def detect(self, _message: str) -> str:
        return "faq"


class _FakeTopic:
    def classify(self, _message: str) -> str:
        return "general_inquiry"


class _FakeMetadata:
    def extract(self, _message: str):
        from backend.server.services.metadata_service import ConversationMetadata

        return ConversationMetadata()


class _FakeResponseSafety:
    def validate(self, _response: str, _documents: object):
        from backend.server.services.response_safety_service import ResponseSafetyResult

        return ResponseSafetyResult(allowed=True)


@unittest.skipUnless(
    os.getenv("CTRL4_RUN_PERFORMANCE_TESTS") == "1",
    "requires CTRL4_RUN_PERFORMANCE_TESTS=1 and an isolated MySQL database",
)
class PerformanceReliabilityRuntimeTests(unittest.TestCase):
    """Measured local runtime coverage using the approved Issue #72 profile."""

    results: dict[str, Any] = {}
    app: Any
    student_ids: list[int]
    staff_ids: list[int]
    _session_directory: tempfile.TemporaryDirectory[str]
    _chat_patch: Any

    @classmethod
    def setUpClass(cls) -> None:
        cls._require_isolated_database()
        cls._bootstrap_schema_and_seed()

        cls._session_directory = tempfile.TemporaryDirectory()
        os.environ["CHATBOT_SESSION_FILE_DIR"] = cls._session_directory.name
        os.environ["CHATBOT_LLM_PROVIDER"] = "gemini"
        os.environ["CHATBOT_GEMINI_API_KEY"] = ""
        os.environ["CHATBOT_RAG_AUTO_BUILD_ON_START"] = "false"

        from backend.server import create_app
        from backend.server.routes import chatbot_routes

        cls.app = create_app()
        cls.app.config.update(TESTING=True)
        cls._fake_ai = cls._deterministic_ai_service()
        cls._chat_patch = patch.object(
            chatbot_routes,
            "ai_service",
            cls._fake_ai,
        )
        cls._chat_patch.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._chat_patch.stop()
        cls._session_directory.cleanup()
        if cls.results:
            print("\nIssue #72 measured results:\n" + json.dumps(cls.results, indent=2))

    @classmethod
    def _require_isolated_database(cls) -> None:
        database = os.getenv("CTRL4_PERFORMANCE_DB", "").strip()
        configured_database = os.getenv("CHATBOT_DB_NAME", "").strip()
        if not database or database != configured_database:
            raise RuntimeError(
                "CTRL4_PERFORMANCE_DB must exactly match CHATBOT_DB_NAME."
            )
        if not database.startswith(PERFORMANCE_DATABASE_PREFIX):
            raise RuntimeError(
                f"The isolated database name must start with {PERFORMANCE_DATABASE_PREFIX!r}."
            )
        if not re.fullmatch(r"[A-Za-z0-9_]+", database):
            raise RuntimeError("The isolated database name contains unsupported characters.")

    @classmethod
    def _mysql_connection(cls, *, database: str | None = None):
        import mysql.connector

        kwargs: dict[str, object] = {
            "host": os.getenv("CHATBOT_DB_HOST", "127.0.0.1"),
            "port": int(os.getenv("CHATBOT_DB_PORT", "3306")),
            "user": os.getenv("CHATBOT_DB_USER", "root"),
            "password": os.getenv("CHATBOT_DB_PASSWORD", ""),
        }
        if database:
            kwargs["database"] = database
        return mysql.connector.connect(**kwargs)

    @classmethod
    def _bootstrap_schema_and_seed(cls) -> None:
        database = os.environ["CTRL4_PERFORMANCE_DB"]
        with cls._mysql_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                    (database,),
                )
                if cursor.fetchone():
                    cursor.execute(
                        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s",
                        (database,),
                    )
                    if int(cursor.fetchone()[0]):
                        raise RuntimeError(
                            "The isolated performance database already contains tables; "
                            "use a new database name instead of overwriting it."
                        )
                else:
                    cursor.execute(
                        f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
            connection.commit()

        statements = SCHEMA_PATH.read_text(encoding="utf-8").split(";")
        with cls._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    normalized = statement.strip()
                    upper = normalized.upper()
                    if not normalized or upper.startswith("CREATE DATABASE") or upper.startswith("USE "):
                        continue
                    cursor.execute(normalized)
            connection.commit()

        cls._seed_synthetic_records(database)

    @classmethod
    def _seed_synthetic_records(cls, database: str) -> None:
        from werkzeug.security import generate_password_hash

        now = datetime.now().replace(microsecond=0)
        password_hash = generate_password_hash(PERFORMANCE_PASSWORD)
        schedule = json.dumps([
            {"room": "Performance Room", "days": "Monday-Friday", "time": "8:00 AM - 5:00 PM"}
        ])
        availability = json.dumps({
            "officeAvailability": [{"days": "Monday-Friday", "time": "8:00 AM - 5:00 PM"}],
            "holidays": [],
            "academicCalendarExclusions": [],
            "unavailableDates": [],
        })

        with cls._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                students = [
                    (
                        f"student{index:03d}@performance.test",
                        password_hash,
                        f"Synthetic Student {index:03d}",
                        f"2026-{index:05d}",
                        None,
                        "Male" if index % 2 else "Female",
                        PROGRAMS[(index - 1) % len(PROGRAMS)],
                        None,
                        None,
                        None,
                        None,
                        None,
                        "student",
                        "active",
                        now - timedelta(days=index % 365),
                    )
                    for index in range(1, 101)
                ]
                staff = [
                    (
                        f"staff{index:03d}@performance.test",
                        password_hash,
                        f"Synthetic Staff {index:03d}",
                        None,
                        f"PERF-STF-{index:03d}",
                        "Female",
                        None,
                        json.dumps([PROGRAMS[index - 1]]),
                        "Guidance Office",
                        None,
                        json.dumps(["Performance Room"]),
                        schedule,
                        "staff",
                        "active",
                        now,
                    )
                    for index in range(1, 6)
                ]
                admin = [
                    (
                        "admin@performance.test", password_hash, "Synthetic Administrator",
                        None, None, "Prefer not to say", None, None, None, None,
                        None, None, "admin", "active", now,
                    )
                ]
                cursor.executemany(
                    """
                    INSERT INTO accounts (
                        email, password_hash, full_name, student_number, staff_number,
                        gender, program, assigned_programs, office, support_statement,
                        consultation_rooms, consultation_schedules, role, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    students + staff + admin,
                )
                cursor.execute("SELECT id FROM accounts WHERE role = 'student' ORDER BY id")
                cls.student_ids = [int(row[0]) for row in cursor.fetchall()]
                cursor.execute("SELECT id FROM accounts WHERE role = 'staff' ORDER BY id")
                cls.staff_ids = [int(row[0]) for row in cursor.fetchall()]

                appointments = []
                statuses = ("pending", "confirmed", "cancelled", "rejected", "completed")
                for index in range(1000):
                    created = now - timedelta(days=364 - (index % 365), minutes=index)
                    appointments.append((
                        cls.student_ids[index % len(cls.student_ids)], "09170000000",
                        "Academic", "in_person", created.date(), "9:00 AM",
                        "Synthetic appointment", statuses[index % len(statuses)], None,
                        "chatbot", created, created,
                    ))
                cursor.executemany(
                    """
                    INSERT INTO appointments (
                        account_id, contact_number, appointment_category, appointment_mode,
                        preferred_date, preferred_time_slot, reason, status, counselor_notes,
                        appointment_source, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    appointments,
                )

                inquiries = [
                    (
                        cls.student_ids[index % len(cls.student_ids)], "ai_chat",
                        ("Neutral", "Positive", "Sadness", "Fear")[index % 4],
                        1 if index % 50 == 0 else 0, 0,
                        now - timedelta(days=364 - (index % 365), minutes=index),
                    )
                    for index in range(5000)
                ]
                cursor.executemany(
                    """
                    INSERT INTO inquiries (
                        account_id, inquiry_type, emotion_result, escalated,
                        appointment_recommended, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    inquiries,
                )

                summaries = [
                    (
                        cls.student_ids[index % len(cls.student_ids)], "Synthetic concern",
                        "general", "neutral", 1 if index < 100 else 0,
                        "No appointment recommendation", "Synthetic recommendation", None,
                        "english", (index % 12) + 1, "Synthetic summary",
                        now - timedelta(days=364 - (index % 365), minutes=index),
                    )
                    for index in range(500)
                ]
                cursor.executemany(
                    """
                    INSERT INTO conversation_summaries (
                        account_id, primary_concern, conversation_type, emotion_results,
                        flagged_status, appointment_recommendation, recommendations,
                        suggested_intervention, language_used, total_messages, summary, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    summaries,
                )
                cursor.execute("SELECT id FROM conversation_summaries ORDER BY id")
                summary_ids = [int(row[0]) for row in cursor.fetchall()]

                escalations = [
                    (
                        cls.student_ids[index % len(cls.student_ids)], summary_ids[index],
                        "pending" if index % 2 else "reviewed", "Synthetic reason", None,
                        now - timedelta(days=99 - index), None, None,
                    )
                    for index in range(100)
                ]
                cursor.executemany(
                    """
                    INSERT INTO escalations (
                        account_id, summary_id, status, escalation_reason, intervention_notes,
                        created_at, resolved_at, reviewed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    escalations,
                )
                referrals = [
                    (
                        summary_ids[index], cls.staff_ids[index % len(cls.staff_ids)],
                        "Guidance Office", "Synthetic referral", "pending" if index % 2 else "in_progress",
                        now - timedelta(days=99 - index), now - timedelta(days=99 - index),
                    )
                    for index in range(100)
                ]
                cursor.executemany(
                    """
                    INSERT INTO referrals (
                        conversation_summary_id, staff_account_id, destination, referral_reason,
                        status, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    referrals,
                )
                interventions = [
                    (
                        summary_ids[index], cls.staff_ids[index % len(cls.staff_ids)],
                        "Counseling", "Synthetic objective",
                        "completed" if index % 3 == 0 else "ongoing", None,
                        now - timedelta(days=99 - index), now - timedelta(days=99 - index),
                    )
                    for index in range(100)
                ]
                cursor.executemany(
                    """
                    INSERT INTO interventions (
                        conversation_summary_id, staff_account_id, intervention_type, objective,
                        progress_status, outcome, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    interventions,
                )
                confidentiality = [
                    (
                        summary_ids[index], cls.staff_ids[index % len(cls.staff_ids)],
                        "confidential", "Synthetic confidentiality", now, now,
                    )
                    for index in range(50)
                ]
                cursor.executemany(
                    """
                    INSERT INTO case_confidentiality (
                        conversation_summary_id, staff_account_id, confidentiality_status,
                        confidentiality_reason, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    confidentiality,
                )
                notifications = [
                    (cls.student_ids[index % len(cls.student_ids)], "Synthetic notification",
                     "Synthetic notification message", "performance", 0, now - timedelta(minutes=index))
                    for index in range(100)
                ]
                cursor.executemany(
                    """
                    INSERT INTO notifications (
                        recipient_account_id, title, message, type, is_read, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    notifications,
                )
                notes = [
                    (summary_ids[index], cls.staff_ids[index % len(cls.staff_ids)],
                     "Synthetic case note", now, now)
                    for index in range(100)
                ]
                cursor.executemany(
                    """
                    INSERT INTO case_notes (
                        conversation_summary_id, staff_account_id, note_text, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    notes,
                )
                cursor.execute(
                    "INSERT INTO settings (setting_key, setting_value, updated_at) VALUES (%s, %s, %s)",
                    ("appointmentAvailability", availability, now),
                )
            connection.commit()

    @classmethod
    def _deterministic_ai_service(cls):
        from backend.server.services.ai_service import AIService

        return AIService(
            safety=_FakeSafety(), language=_FakeLanguage(), emotion=_FakeEmotion(),
            rag=_FakeRag(), prompt_builder=_FakePromptBuilder(), llm=_FakeLLM(),
            intent=_FakeIntent(), topic_classifier=_FakeTopic(),
            metadata_extractor=_FakeMetadata(), response_safety=_FakeResponseSafety(),
        )

    @classmethod
    def _next_weekday(cls, offset: int) -> str:
        candidate = date.today() + timedelta(days=7 + offset)
        while candidate.weekday() > 4:
            candidate += timedelta(days=1)
        return candidate.isoformat()

    def _client_for(self, role: str, account_id: int) -> Any:
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["hau_user"] = {
                "id": account_id,
                "email": f"{role}{account_id}@performance.test",
                "role": role,
            }
            session["_csrf_token"] = "performance-csrf-token"
            session.permanent = True
        return client

    def _request(self, role: str, account_id: int, method: str, path: str, json_data: dict | None = None):
        client = self._client_for(role, account_id)
        started = time.perf_counter()
        headers = {}
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            headers = {"X-CSRF-Token": "performance-csrf-token"}
        response = client.open(path, method=method, json=json_data, headers=headers)
        elapsed = time.perf_counter() - started
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertIn("success", payload)
        self.assertIn("message", payload)
        if payload["success"]:
            self.assertIn("data", payload)
        else:
            self.assertIn("errors", payload)
        return response, elapsed

    def _measure(self, name: str, action: Callable[[], tuple[Any, float]], expected_status: int, limit_ms: float) -> None:
        samples: list[float] = []
        for _ in range(5):
            response, elapsed = action()
            self.assertEqual(response.status_code, expected_status)
            samples.append(elapsed)
        measured = _summary(samples)
        self.results[name] = measured
        self.assertLessEqual(measured["median_ms"], limit_ms, name)

    def _concurrent(self, name: str, workers: int, action: Callable[[int], tuple[Any, float]], expected_status: int, p95_limit_ms: float) -> None:
        memory_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        started_cpu = time.process_time()
        started_wall = time.perf_counter()
        errors: list[str] = []
        timings: list[float] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(action, index) for index in range(workers)]
            for future in as_completed(futures):
                try:
                    response, elapsed = future.result()
                    if response.status_code != expected_status:
                        errors.append(f"HTTP {response.status_code}: {response.get_json()}")
                    else:
                        timings.append(elapsed)
                except Exception as exc:  # Report an implementation failure precisely.
                    errors.append(f"{type(exc).__name__}: {exc}")
        elapsed_wall = time.perf_counter() - started_wall
        measured = _summary(timings) if timings else {"median_ms": 0.0, "p95_ms": 0.0, "samples": 0}
        measured.update({
            "workers": workers,
            "successes": len(timings),
            "errors": len(errors),
            "process_cpu_percent_estimate": round(
                ((time.process_time() - started_cpu) / elapsed_wall) * 100, 2
            ) if elapsed_wall else 0.0,
            "max_rss_raw_before": memory_before,
            "max_rss_raw_after": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        })
        self.results[name] = measured
        self.assertFalse(errors, f"{name} failures: {errors}")
        self.assertEqual(len(timings), workers)
        self.assertLessEqual(measured["p95_ms"], p95_limit_ms, name)

    def test_01_synthetic_fixture_matches_the_approved_scale(self) -> None:
        database = os.environ["CTRL4_PERFORMANCE_DB"]
        expected = {
            "accounts": 106,
            "appointments": 1000,
            "inquiries": 5000,
            "conversation_summaries": 500,
            "escalations": 100,
            "referrals": 100,
            "interventions": 100,
            "case_confidentiality": 50,
        }
        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                for table, minimum in expected.items():
                    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                    self.assertGreaterEqual(int(cursor.fetchone()[0]), minimum)
        health = self.app.test_client().get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertTrue(health.get_json()["success"])
        self.results["fixture"] = expected

    def test_02_single_request_latency_and_chatbot_pipeline(self) -> None:
        student = self.student_ids[0]
        staff = self.staff_ids[0]
        self._measure(
            "login", lambda: self._login_measurement(), 200, 500,
        )
        self._measure(
            "appointment_list", lambda: self._request("staff", staff, "GET", "/api/appointments"), 200, 500,
        )
        self._measure(
            "notification_list", lambda: self._request("student", student, "GET", "/api/notifications"), 200, 500,
        )
        for name, endpoint in (
            ("appointment_analytics", "/api/dashboard/appointments/analytics"),
            ("chatbot_analytics", "/api/dashboard/chatbot/analytics"),
            ("counselor_workload", "/api/dashboard/counselor-workload"),
            ("flagged_case_analytics", "/api/dashboard/flagged-cases/analytics"),
        ):
            self._measure(name, lambda endpoint=endpoint: self._request("staff", staff, "GET", endpoint), 200, 1000)

        valid_dates = iter(self._next_weekday(7 * (1 + index)) for index in range(5))
        self._measure(
            "appointment_create",
            lambda: self._request(
                "student",
                student,
                "POST",
                "/api/appointments",
                self._appointment_payload(next(valid_dates), "9:00 AM"),
            ),
            201,
            750,
        )
        conflict_date = self._next_weekday(7 * 30)
        self._insert_blocked_appointment(student, conflict_date, "10:00 AM")
        self._measure(
            "appointment_conflict",
            lambda: self._request("student", student, "POST", "/api/appointments", self._appointment_payload(conflict_date, "10:00 AM")),
            409,
            750,
        )
        self._measure(
            "chatbot_safety_short_circuit",
            lambda: self._request("student", student, "POST", "/chat", {"message": "PERFORMANCE_SAFETY_SHORT_CIRCUIT"}),
            200,
            1000,
        )
        self._measure(
            "chatbot_fake_provider",
            lambda: self._request("student", student, "POST", "/chat", {"message": "How can I contact the Guidance Office?"}),
            200,
            2000,
        )
        response, elapsed = self._load_reports(staff)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(elapsed * 1000, 3000, "combined_reports_single_user")
        self.results["combined_reports_single_user"] = {
            "completion_ms": round(elapsed * 1000, 2),
        }
        self._assert_fake_pipeline_timing()

    def test_03_required_concurrent_workflows(self) -> None:
        staff = self.staff_ids[0]
        student = self.student_ids[1]
        self._concurrent(
            "ordinary_reads_10_users", 10,
            lambda _index: self._request("staff", staff, "GET", "/api/appointments"),
            200, 1500,
        )
        for name, endpoint in (
            ("appointment_analytics_10_users", "/api/dashboard/appointments/analytics"),
            ("chatbot_analytics_10_users", "/api/dashboard/chatbot/analytics"),
            ("counselor_workload_10_users", "/api/dashboard/counselor-workload"),
            ("flagged_case_analytics_10_users", "/api/dashboard/flagged-cases/analytics"),
        ):
            self._concurrent(
                name, 10,
                lambda _index, endpoint=endpoint: self._request("staff", staff, "GET", endpoint),
                200, 3000,
            )
        self._concurrent(
            "appointment_creation_10_users", 10,
            lambda index: self._request(
                "student", self.student_ids[10 + index], "POST", "/api/appointments",
                self._appointment_payload(self._next_weekday(7 * (50 + index)), "9:00 AM"),
            ),
            201, 2000,
        )
        self._assert_single_success_for_blocked_slot(student)

    def test_04_combined_reports_at_five_users(self) -> None:
        staff = self.staff_ids[0]

        def load_reports(_index: int):
            return self._load_reports(staff)

        self._concurrent("combined_reports_5_users", 5, load_reports, 200, 5000)

    def test_05_atomic_appointment_regressions(self) -> None:
        student = self.student_ids[20]
        staff = self.staff_ids[0]

        equivalent_date = self._next_weekday(7 * 200)
        first, _ = self._request(
            "student", student, "POST", "/api/appointments",
            self._appointment_payload(equivalent_date, "8:00 AM"),
        )
        equivalent, _ = self._request(
            "student", student, "POST", "/api/appointments",
            self._appointment_payload(equivalent_date, "08:00 AM"),
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(equivalent.status_code, 409)
        self.assertEqual(equivalent.get_json()["message"], "This schedule is already taken.")

        for index, status in enumerate(("pending", "confirmed")):
            conflict_date = self._next_weekday(7 * (210 + index))
            self._insert_appointment(student, conflict_date, "10:00 AM", status)
            response, _ = self._request(
                "student", student, "POST", "/api/appointments",
                self._appointment_payload(conflict_date, "10:00 AM"),
            )
            self.assertEqual(response.status_code, 409, status)
            self.assertEqual(response.get_json()["message"], "This schedule is already taken.")

        for index, status in enumerate(("cancelled", "rejected", "completed")):
            terminal_date = self._next_weekday(7 * (220 + index))
            self._insert_appointment(student, terminal_date, "10:00 AM", status)
            response, _ = self._request(
                "student", student, "POST", "/api/appointments",
                self._appointment_payload(terminal_date, "10:00 AM"),
            )
            self.assertEqual(response.status_code, 201, status)

        manual_date = self._next_weekday(7 * 230)
        manual_payload = {
            "account_id": student,
            "appointment_category": "Academic",
            "appointment_mode": "in_person",
            "preferred_date": manual_date,
            "preferred_time_slot": "1:00 PM",
            "reason": "Synthetic manual appointment",
            "appointment_source": "staff_manual",
        }
        manual_results = self._concurrent_statuses(
            10,
            lambda _index: self._request(
                "staff", staff, "POST", "/api/appointments/manual", manual_payload,
            ),
        )
        self.assertEqual(manual_results.count(201), 1)
        self.assertEqual(manual_results.count(409), 9)

        original_date = self._next_weekday(7 * 240)
        original_id = self._insert_appointment(student, original_date, "9:00 AM", "pending")
        replacement_date = self._next_weekday(7 * 241)
        reschedule_results = self._concurrent_statuses(
            10,
            lambda _index: self._request(
                "student", student, "POST",
                f"/api/appointments/my/{original_id}/reschedule",
                {"preferred_date": replacement_date, "preferred_time_slot": "2:00 PM"},
            ),
        )
        self.assertEqual(reschedule_results.count(201), 1)
        self.assertEqual(
            self._count_blocking_appointments(replacement_date, "2:00 PM"), 1,
        )
        self.assertEqual(self._appointment_status(original_id), "cancelled")

        failed_original_date = self._next_weekday(7 * 250)
        failed_original_id = self._insert_appointment(
            student, failed_original_date, "9:00 AM", "pending",
        )
        blocked_replacement_date = self._next_weekday(7 * 251)
        self._insert_appointment(student, blocked_replacement_date, "2:00 PM", "pending")
        failure, _ = self._request(
            "student", student, "POST",
            f"/api/appointments/my/{failed_original_id}/reschedule",
            {"preferred_date": blocked_replacement_date, "preferred_time_slot": "2:00 PM"},
        )
        self.assertEqual(failure.status_code, 409)
        self.assertEqual(self._appointment_status(failed_original_id), "pending")

        self._assert_lock_cleanup_and_rollback(student)
        self.results["atomic_regressions"] = {
            "equivalent_formats": "one success, one conflict",
            "blocking_statuses": "pending and confirmed rejected",
            "terminal_statuses": "cancelled, rejected, and completed allowed",
            "manual_same_slot": {"successes": 1, "conflicts": 9},
            "reschedule_same_slot": {"successes": 1},
            "failed_reschedule_preserves_original": True,
            "lock_cleanup_and_rollback": True,
        }

    def test_06_existing_booking_validation_contracts(self) -> None:
        student = self.student_ids[20]
        staff = self.staff_ids[0]
        missing, _ = self._request("student", student, "POST", "/api/appointments", {})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.get_json()["message"], "Missing required fields.")
        self.assertEqual(
            missing.get_json()["errors"],
            [
                "contact_number",
                "appointment_category",
                "appointment_mode",
                "preferred_date",
                "preferred_time_slot",
                "reason",
            ],
        )

        database = os.environ["CTRL4_PERFORMANCE_DB"]
        valid_schedule = json.dumps([
            {"room": "Performance Room", "days": "Monday-Friday", "time": "8:00 AM - 5:00 PM"}
        ])
        valid_availability = json.dumps({
            "officeAvailability": [{"days": "Monday-Friday", "time": "8:00 AM - 5:00 PM"}],
            "holidays": [],
            "academicCalendarExclusions": [],
            "unavailableDates": [],
        })
        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE accounts SET consultation_schedules = %s WHERE id = %s",
                    (json.dumps([]), staff),
                )
                cursor.execute(
                    "UPDATE settings SET setting_value = %s WHERE setting_key = %s",
                    (json.dumps({}), "appointmentAvailability"),
                )
            connection.commit()
        try:
            schedule_first, _ = self._request(
                "student", student, "POST", "/api/appointments",
                self._appointment_payload(self._next_weekday(7 * 270), "4:00 PM"),
            )
            self.assertEqual(schedule_first.status_code, 400)
            self.assertEqual(
                schedule_first.get_json()["message"],
                "The selected date and time are outside the counselor's consultation schedule.",
            )
        finally:
            with self._mysql_connection(database=database) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE accounts SET consultation_schedules = %s WHERE id = %s",
                        (valid_schedule, staff),
                    )
                connection.commit()

        try:
            unavailable, _ = self._request(
                "student", student, "POST", "/api/appointments",
                self._appointment_payload(self._next_weekday(7 * 271), "4:00 PM"),
            )
            self.assertEqual(unavailable.status_code, 400)
            self.assertEqual(
                unavailable.get_json()["message"],
                "The Guidance Office is unavailable for the selected date and time.",
            )
        finally:
            with self._mysql_connection(database=database) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE settings SET setting_value = %s WHERE setting_key = %s",
                        (valid_availability, "appointmentAvailability"),
                    )
                connection.commit()

    def _load_reports(self, staff_account_id: int):
        endpoints = (
            "/api/dashboard/appointments/analytics",
            "/api/dashboard/chatbot/analytics",
            "/api/dashboard/counselor-workload",
            "/api/dashboard/flagged-cases/analytics",
        )
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(executor.map(
                lambda endpoint: self._request("staff", staff_account_id, "GET", endpoint)[0],
                endpoints,
            ))
        elapsed = time.perf_counter() - started
        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["success"])
        return responses[0], elapsed

    def _login_measurement(self):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session["_csrf_token"] = "performance-login-csrf-token"
        started = time.perf_counter()
        response = client.post(
            "/auth/login",
            json={"email": "student001@performance.test", "password": PERFORMANCE_PASSWORD},
            headers={"X-CSRF-Token": "performance-login-csrf-token"},
        )
        return response, time.perf_counter() - started

    @staticmethod
    def _appointment_payload(preferred_date: str, preferred_time_slot: str) -> dict[str, str]:
        return {
            "contact_number": "09170000000",
            "appointment_category": "Academic",
            "appointment_mode": "in_person",
            "preferred_date": preferred_date,
            "preferred_time_slot": preferred_time_slot,
            "reason": "Synthetic performance appointment",
        }

    def _insert_blocked_appointment(self, student_id: int, preferred_date: str, preferred_time_slot: str) -> None:
        self._insert_appointment(student_id, preferred_date, preferred_time_slot, "pending")

    def _insert_appointment(
        self,
        student_id: int,
        preferred_date: str,
        preferred_time_slot: str,
        status: str,
    ) -> int:
        database = os.environ["CTRL4_PERFORMANCE_DB"]
        now = datetime.now().replace(microsecond=0)
        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO appointments (
                        account_id, contact_number, appointment_category, appointment_mode,
                        preferred_date, preferred_time_slot, reason, status, counselor_notes,
                        appointment_source, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s)
                    """,
                    (student_id, "09170000000", "Academic", "in_person", preferred_date,
                     preferred_time_slot, "Synthetic blocking appointment", status,
                     "chatbot", now, now),
                )
                appointment_id = int(cursor.lastrowid)
            connection.commit()
        return appointment_id

    def _concurrent_statuses(
        self,
        workers: int,
        action: Callable[[int], tuple[Any, float]],
    ) -> list[int]:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(action, index) for index in range(workers)]
            return [future.result()[0].status_code for future in as_completed(futures)]

    def _appointment_status(self, appointment_id: int) -> str:
        database = os.environ["CTRL4_PERFORMANCE_DB"]
        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT status FROM appointments WHERE id = %s", (appointment_id,))
                return str(cursor.fetchone()[0])

    def _count_blocking_appointments(self, preferred_date: str, preferred_time_slot: str) -> int:
        database = os.environ["CTRL4_PERFORMANCE_DB"]
        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM appointments
                    WHERE preferred_date = %s
                      AND preferred_time_slot = %s
                      AND status IN ('pending', 'confirmed')
                    """,
                    (preferred_date, preferred_time_slot),
                )
                return int(cursor.fetchone()[0])

    def _assert_lock_cleanup_and_rollback(self, student_id: int) -> None:
        from backend.server import db

        database = os.environ["CTRL4_PERFORMANCE_DB"]
        success_date = self._next_weekday(7 * 260)
        payload = {
            "account_id": student_id,
            "contact_number": "09170000000",
            "appointment_category": "Academic",
            "appointment_mode": "in_person",
            "preferred_date": success_date,
            "preferred_time_slot": "3:00 PM",
            "reason": "Atomic lock cleanup verification",
            "status": "pending",
            "counselor_notes": None,
            "appointment_source": "chatbot",
            "created_at": datetime.now().replace(microsecond=0),
            "updated_at": datetime.now().replace(microsecond=0),
        }
        normalized = "03:00 PM"
        equivalents = ("03:00 PM", "3:00 PM")
        db.save_appointment_if_available(
            payload,
            normalized_time_slot=normalized,
            equivalent_time_slots=equivalents,
        )
        with self.assertRaises(db.AppointmentConflictPersistenceError):
            db.save_appointment_if_available(
                payload,
                normalized_time_slot=normalized,
                equivalent_time_slots=equivalents,
            )

        failing_date = self._next_weekday(7 * 261)
        failing_payload = {**payload, "preferred_date": failing_date}
        failing_payload.pop("reason")
        with self.assertRaises(KeyError):
            db.save_appointment_if_available(
                failing_payload,
                normalized_time_slot=normalized,
                equivalent_time_slots=equivalents,
            )

        with self._mysql_connection(database=database) as connection:
            with connection.cursor() as cursor:
                for check_date in (success_date, failing_date):
                    lock_name = db._appointment_conflict_lock_name(check_date, normalized)
                    cursor.execute("SELECT IS_FREE_LOCK(%s)", (lock_name,))
                    self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    "SELECT COUNT(*) FROM appointments WHERE preferred_date = %s",
                    (failing_date,),
                )
                self.assertEqual(cursor.fetchone()[0], 0)

    def _assert_single_success_for_blocked_slot(self, student_id: int) -> None:
        """Verify concurrent duplicates remain constrained by the existing conflict rule."""
        duplicate_date = self._next_weekday(7 * 80)
        payload = self._appointment_payload(duplicate_date, "11:00 AM")
        outcomes: list[int] = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(
                    self._request, "student", student_id, "POST", "/api/appointments", payload,
                )
                for _ in range(10)
            ]
            for future in as_completed(futures):
                response, _elapsed = future.result()
                outcomes.append(response.status_code)
        successful = outcomes.count(201)
        conflicts = outcomes.count(409)
        self.results["same_slot_concurrency"] = {
            "successes": successful,
            "conflicts": conflicts,
            "other_statuses": sorted(set(outcomes) - {201, 409}),
        }
        self.assertEqual(successful, 1, "Only one same-slot booking may succeed.")
        self.assertEqual(conflicts, 9, "Every later same-slot booking must be rejected.")

    def _assert_fake_pipeline_timing(self) -> None:
        with self.assertLogs("backend.server.services.ai_service", level="DEBUG") as captured:
            result = self._fake_ai.respond("Pipeline timing verification.")
        self.assertTrue(result.success)
        timing_lines = [line for line in captured.output if "Pipeline timings" in line]
        self.assertEqual(len(timing_lines), 1)
        numbers = [float(value) for value in re.findall(r"=([0-9]+\.[0-9]+)s", timing_lines[0])]
        self.assertEqual(len(numbers), 7)
        *stages, total = numbers
        self.assertGreaterEqual(total + 0.001, max(stages))
        self.assertNotIn("Pipeline timing verification.", timing_lines[0])
        self.assertNotIn("deterministic performance-test prompt", timing_lines[0])


if __name__ == "__main__":
    unittest.main()
