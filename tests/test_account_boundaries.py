from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch
from flask import Flask

import mysql.connector

from backend.server.services import account_service


class AccountBoundaryTests(unittest.TestCase):
    def test_student_account_csv_import_creates_only_validated_students(self) -> None:
        csv_content = (
            b"full_name,email,gender,program\n"
            b"Student One,one@student.hau.edu.ph,Female,BS Computer Science\n"
        )
        created_account = {
            "id": 12,
            "student_number": "2026-00001",
            "staff_number": None,
        }

        with patch.object(
            account_service,
            "fetch_account_by_email",
            return_value=None,
        ), patch.object(
            account_service.program_service,
            "active_program_names",
            return_value={"BS Computer Science"},
        ), patch.object(
            account_service,
            "_create_account_with_duplicate_email_translation",
            return_value=created_account,
        ) as create_account:
            imported = account_service.create_student_accounts_from_csv_service(
                csv_content,
            )

        self.assertEqual(imported[0]["student_number"], "2026-00001")
        self.assertEqual(imported[0]["email"], "one@student.hau.edu.ph")
        self.assertTrue(imported[0]["temporary_password"])
        self.assertEqual(create_account.call_args.kwargs["role"], "student")
        self.assertIsNone(create_account.call_args.kwargs["student_number"])
        self.assertTrue(
            account_service.check_password_hash(
                create_account.call_args.kwargs["password_hash"],
                imported[0]["temporary_password"],
            )
        )

    def test_student_account_csv_import_rejects_duplicate_rows_before_creation(self) -> None:
        csv_content = (
            b"full_name,email,gender,program\n"
            b"Student One,student@student.hau.edu.ph,Female,BS Computer Science\n"
            b"Student Two,student@student.hau.edu.ph,Male,BS Computer Science\n"
        )
        with patch.object(
            account_service,
            "fetch_account_by_email",
            return_value=None,
        ), patch.object(
            account_service.program_service,
            "active_program_names",
            return_value={"BS Computer Science"},
        ), patch.object(
            account_service,
            "_create_account_with_duplicate_email_translation",
        ) as create_account, self.assertRaisesRegex(
            account_service.StudentAccountImportValidationError,
            "Email is duplicated in this CSV",
        ):
            account_service.create_student_accounts_from_csv_service(csv_content)

        create_account.assert_not_called()

    def test_student_account_csv_import_rejects_extra_row_columns(self) -> None:
        csv_content = (
            b"full_name,email,gender,program\n"
            b"Student One,student@student.hau.edu.ph,Female,BS Computer Science,staff\n"
        )
        with self.assertRaisesRegex(
            account_service.StudentAccountImportValidationError,
            "Too many columns",
        ):
            account_service.create_student_accounts_from_csv_service(csv_content)

    def test_student_account_csv_import_route_requires_admin_role(self) -> None:
        from backend.server.routes import account_routes
        from backend.server.routes.account_routes import account_bp

        app = Flask(__name__)
        app.secret_key = "student-account-import-routes"
        app.register_blueprint(account_bp)

        def client_for(role: str):
            client = app.test_client()
            with client.session_transaction() as session:
                session["hau_user"] = {
                    "id": 7,
                    "email": f"{role}@example.test",
                    "role": role,
                }
            return client

        imported = [
            {
                "row_number": 2,
                "full_name": "Student One",
                "email": "student@example.test",
                "student_number": "2026-00001",
                "temporary_password": "temporary-password",
            }
        ]
        with patch.object(
            account_routes,
            "create_student_accounts_from_csv_service",
            return_value=imported,
        ) as import_students:
            response = client_for("admin").post(
                "/api/accounts/import/students",
                data={"file": (BytesIO(b"csv"), "students.csv")},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["data"]["items"], imported)
        import_students.assert_called_once_with(b"csv")
        self.assertEqual(
            client_for("student").post(
                "/api/accounts/import/students",
                data={"file": (BytesIO(b"csv"), "students.csv")},
            ).status_code,
            403,
        )

    def test_student_account_retries_after_concurrent_number_collision(self) -> None:
        from backend.server import db

        class Cursor:
            def __init__(self, exception=None, account_id=0):
                self.exception = exception
                self.lastrowid = account_id

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def execute(self, *_args):
                if self.exception:
                    raise self.exception

        class Connection:
            def __init__(self, cursor):
                self.cursor_value = cursor
                self.committed = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def cursor(self):
                return self.cursor_value

            def commit(self):
                self.committed = True

        duplicate_number = mysql.connector.IntegrityError(
            msg="Duplicate entry '2024-00042' for key 'accounts.student_number'",
            errno=1062,
        )
        first_connection = Connection(Cursor(exception=duplicate_number))
        second_connection = Connection(Cursor(account_id=91))

        with patch.object(db, "initialize_database"), patch.object(
            db,
            "fetch_account_by_email",
            return_value=None,
        ), patch.object(
            db,
            "generate_next_student_number",
            side_effect=("2024-00042", "2024-00043"),
        ) as next_number, patch.object(
            db,
            "_database_connection",
            side_effect=(first_connection, second_connection),
        ):
            account = db.create_account(
                full_name="Concurrent Survey Student",
                email="concurrent@student.hau.edu.ph",
                password_hash="hash",
                role="student",
                gender="Prefer not to say",
                program="BS Computer Science",
            )

        self.assertEqual(account["id"], 91)
        self.assertEqual(account["student_number"], "2024-00043")
        self.assertEqual(next_number.call_count, 2)
        self.assertTrue(second_connection.committed)

    def test_verified_profile_seed_uses_only_documented_rooms_and_schedule_windows(self) -> None:
        from backend.server import db

        self.assertEqual(db.APPROVED_CONSULTATION_ROOMS, ("SJH-206", "PGN-105"))
        self.assertEqual(
            db.APPROVED_CONSULTATION_SCHEDULES,
            (
                {"room": "SJH-206", "days": "Monday-Friday", "time": "7:00 AM - 5:00 PM"},
                {"room": "PGN-105", "days": "Monday-Friday", "time": "7:00 AM - 9:00 PM"},
            ),
        )
    def test_admin_staff_update_rejects_operational_profile_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported account update field"):
            account_service.update_staff_account_service(
                5,
                {"consultation_rooms": ["SJH-206"]},
            )

    def test_staff_search_returns_only_authorized_public_fields(self) -> None:
        profile = {"id": 4, "assigned_programs": '["BS Computer Science"]'}
        results = [
            {
                "full_name": "Student One",
                "student_number": "2026-00001",
                "program": "BS Computer Science",
                "email": "student@example.test",
            }
        ]
        with patch.object(account_service, "fetch_account_by_id", return_value=profile), patch.object(
            account_service,
            "search_student_accounts_by_programs",
            return_value=results,
        ) as search:
            returned = account_service.search_students_for_staff_service({"id": 4}, "student")

        self.assertEqual(returned, results)
        search.assert_called_once_with("student", ("BS Computer Science",))
        self.assertNotIn("id", returned[0])

    def test_staff_self_profile_uses_session_identity_only(self) -> None:
        existing = {
            "id": 9,
            "office": "",
            "support_statement": "",
            "consultation_rooms": "[]",
            "consultation_schedules": "[]",
            "appointment_slots": "[]",
            "consultation_modes": "[]",
        }
        updated = {
            **existing,
            "office": "SJH-206",
            "consultation_rooms": '["SJH-206"]',
            "consultation_schedules": '[{"room":"SJH-206","days":"Monday","time":"09:00 AM - 05:00 PM"}]',
            "appointment_slots": '["09:00 AM","10:00 AM"]',
            "consultation_modes": '["Online","Onsite"]',
        }
        with patch.object(account_service, "fetch_account_by_id", side_effect=[existing, updated]), patch.object(
            account_service,
            "_update_account_fields_with_duplicate_email_translation",
            return_value=updated,
        ) as update:
            profile = account_service.update_own_staff_operational_profile_service(
                {"id": 9},
                {
                    "office": "SJH-206",
                    "consultation_rooms": ["SJH-206"],
                    "consultation_schedules": [
                        {"room": "SJH-206", "days": "Monday", "time": "09:00 AM - 05:00 PM"}
                    ],
                    "appointment_slots": ["10:00 AM", "9:00 AM"],
                    "consultation_modes": ["Online", "Onsite"],
                },
            )

        self.assertEqual(profile["office"], "SJH-206")
        self.assertEqual(profile["appointment_slots"], ["09:00 AM", "10:00 AM"])
        self.assertEqual(profile["consultation_modes"], ["Online", "Onsite"])
        self.assertEqual(update.call_args.args[0], 9)

    def test_staff_can_update_only_their_own_password_after_verification(self) -> None:
        credentials = {
            "id": 9,
            "status": "active",
            "password_hash": account_service.generate_password_hash("current-password"),
        }
        with patch.object(
            account_service,
            "fetch_account_password_credentials",
            return_value=credentials,
        ), patch.object(
            account_service,
            "update_account_password_hash",
            return_value=True,
        ) as update:
            account_service.update_own_staff_password_service(
                {"id": 9},
                {
                    "current_password": "current-password",
                    "new_password": "new-password",
                    "confirm_password": "new-password",
                },
            )

        self.assertEqual(update.call_args.args[0], 9)
        self.assertEqual(update.call_args.kwargs["role"], "staff")
        self.assertTrue(
            account_service.check_password_hash(
                update.call_args.args[1],
                "new-password",
            )
        )

    def test_staff_password_update_rejects_invalid_current_or_confirmation(self) -> None:
        credentials = {
            "id": 9,
            "status": "active",
            "password_hash": account_service.generate_password_hash("current-password"),
        }
        with patch.object(
            account_service,
            "fetch_account_password_credentials",
            return_value=credentials,
        ), self.assertRaisesRegex(PermissionError, "Current password is incorrect"):
            account_service.update_own_staff_password_service(
                {"id": 9},
                {
                    "current_password": "incorrect-password",
                    "new_password": "new-password",
                    "confirm_password": "new-password",
                },
            )

        with self.assertRaisesRegex(ValueError, "New passwords do not match"):
            account_service.update_own_staff_password_service(
                {"id": 9},
                {
                    "current_password": "current-password",
                    "new_password": "new-password",
                    "confirm_password": "different-password",
                },
            )

    def test_admin_can_reset_student_password_without_exposing_the_hash(self) -> None:
        with patch.object(
            account_service,
            "fetch_account_by_id",
            return_value={"id": 12, "role": "student", "status": "active"},
        ), patch.object(
            account_service,
            "update_account_password_hash",
            return_value=True,
        ) as update:
            account_service.reset_student_password_service(
                12,
                {
                    "new_password": "SurveyReset123!",
                    "confirm_password": "SurveyReset123!",
                },
            )

        self.assertEqual(update.call_args.args[0], 12)
        self.assertEqual(update.call_args.kwargs["role"], "student")
        self.assertTrue(
            account_service.check_password_hash(
                update.call_args.args[1],
                "SurveyReset123!",
            )
        )

    def test_admin_student_password_reset_rejects_nonstudent_or_invalid_payload(self) -> None:
        with patch.object(account_service, "fetch_account_by_id", return_value=None):
            with self.assertRaisesRegex(LookupError, "Student account not found"):
                account_service.reset_student_password_service(
                    12,
                    {"new_password": "SurveyReset123!", "confirm_password": "SurveyReset123!"},
                )

        with self.assertRaisesRegex(ValueError, "New passwords do not match"):
            account_service.reset_student_password_service(
                12,
                {"new_password": "SurveyReset123!", "confirm_password": "different-password"},
            )

    def test_student_password_reset_route_requires_admin_role(self) -> None:
        from backend.server.routes import account_routes
        from backend.server.routes.account_routes import account_bp

        app = Flask(__name__)
        app.secret_key = "student-password-reset-routes"
        app.register_blueprint(account_bp)

        def client_for(role: str):
            client = app.test_client()
            with client.session_transaction() as session:
                session["hau_user"] = {
                    "id": 7,
                    "email": f"{role}@example.test",
                    "role": role,
                }
            return client

        payload = {
            "new_password": "SurveyReset123!",
            "confirm_password": "SurveyReset123!",
        }
        with patch.object(account_routes, "reset_student_password_service") as reset:
            response = client_for("admin").post("/api/accounts/12/password", json=payload)

        self.assertEqual(response.status_code, 200)
        reset.assert_called_once_with(12, payload)
        self.assertEqual(
            client_for("student").post("/api/accounts/12/password", json=payload).status_code,
            403,
        )

    def test_program_and_profile_routes_enforce_role_boundaries(self) -> None:
        from backend.server.routes.account_routes import account_bp
        from backend.server.routes import account_routes

        app = Flask(__name__)
        app.secret_key = "account-boundary-routes"
        app.register_blueprint(account_bp)

        def client_for(role):  # type: ignore[no-untyped-def]
            client = app.test_client()
            with client.session_transaction() as session:
                session["hau_user"] = {
                    "id": 7,
                    "email": f"{role}@example.test",
                    "role": role,
                }
            return client

        profile = {
            "office": "SJH-206",
            "support_statement": "",
            "consultation_rooms": ["SJH-206"],
            "consultation_schedules": [],
        }
        with patch.object(
            account_routes.program_service,
            "list_programs",
            return_value=[],
        ), patch.object(
            account_routes,
            "get_own_staff_operational_profile_service",
            return_value=profile,
        ):
            self.assertEqual(client_for("admin").get("/api/accounts/programs").status_code, 200)
            self.assertEqual(client_for("staff").get("/api/accounts/staff/profile").status_code, 200)

        self.assertEqual(client_for("staff").get("/api/accounts/programs").status_code, 403)
        self.assertEqual(client_for("admin").get("/api/accounts/staff/profile").status_code, 403)
        self.assertEqual(client_for("student").get("/api/accounts/programs").status_code, 403)
