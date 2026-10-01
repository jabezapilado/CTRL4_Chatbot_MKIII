from __future__ import annotations

import json
import re
from hashlib import sha256
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from typing import Final

import mysql.connector
from werkzeug.security import generate_password_hash

from .config import Config


config = Config()

ALLOWED_ACCOUNT_ROLES: Final[frozenset[str]] = frozenset({
    "student",
    "staff",
    "admin",
})

ALLOWED_ACCOUNT_STATUSES: Final[frozenset[str]] = frozenset({
    "active",
    "disabled",
})

ALLOWED_GENDERS: Final[frozenset[str]] = frozenset({
    "Male",
    "Female",
    "Prefer not to say",
    "Other",
})

ALLOWED_ACCOUNT_UPDATE_FIELDS: Final[frozenset[str]] = frozenset({
    "full_name",
    "email",
    "gender",
    "program",
    "assigned_programs",
    "office",
    "support_statement",
    "consultation_rooms",
    "consultation_schedules",
    "appointment_slots",
    "consultation_modes",
    "status",
})
ACCOUNT_JSON_FIELDS: Final[frozenset[str]] = frozenset({
    "assigned_programs",
    "consultation_rooms",
    "consultation_schedules",
    "appointment_slots",
    "consultation_modes",
})
APPOINTMENT_STATUSES: Final[tuple[str, ...]] = (
    "pending",
    "confirmed",
    "cancelled",
    "rejected",
    "completed",
)
APPOINTMENT_CONFLICT_LOCK_TIMEOUT_SECONDS: Final[int] = 5
STUDENT_NUMBER_ALLOCATION_MAX_ATTEMPTS: Final[int] = 5
APPOINTMENT_CONFLICT_BLOCKING_STATUSES: Final[tuple[str, ...]] = (
    "pending",
    "confirmed",
)
_MIGRATION_LEGACY_APPOINTMENT_STATUSES: Final[tuple[str, ...]] = (
    "approved",
    "done",
    "did_not_attend",
)
_MIGRATION_KNOWN_APPOINTMENT_STATUSES: Final[frozenset[str]] = frozenset(
    APPOINTMENT_STATUSES + _MIGRATION_LEGACY_APPOINTMENT_STATUSES
)


class AppointmentConflictPersistenceError(Exception):
    """A transaction recheck found a blocking appointment for the slot."""


class AppointmentConflictLockError(Exception):
    """The database could not reserve the slot's advisory lock in time."""


def _connection_kwargs(database: str | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "host": config.DB_HOST,
        "port": config.DB_PORT,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
        "autocommit": False,
    }
    if database:
        kwargs["database"] = database

    ssl_options: dict[str, Any] = {}
    if config.DB_SSL_CA:
        ssl_options["ca"] = config.DB_SSL_CA
        ssl_options["verify_cert"] = config.DB_SSL_VERIFY_CERT
    if ssl_options:
        kwargs["ssl_ca"] = ssl_options.get("ca")
        kwargs["ssl_verify_cert"] = ssl_options.get("verify_cert", False)

    return kwargs


def _server_connection():
    return mysql.connector.connect(**_connection_kwargs())


def _database_connection():
    return mysql.connector.connect(**_connection_kwargs(config.DB_NAME))

def current_time() -> datetime:
    return datetime.now().replace(microsecond=0)


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return value


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(value) for key, value in row.items()}


def _json_column_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


APPROVED_CONSULTATION_ROOMS: Final[tuple[str, ...]] = (
    "SJH-206",
    "PGN-105",
)
APPROVED_CONSULTATION_SCHEDULES: Final[tuple[dict[str, str], ...]] = (
    {"room": "SJH-206", "days": "Monday-Friday", "time": "7:00 AM - 5:00 PM"},
    {"room": "PGN-105", "days": "Monday-Friday", "time": "7:00 AM - 9:00 PM"},
)


def _is_empty_json_list(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return False
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return not value.strip()
    return isinstance(value, list) and not value


def seed_missing_staff_operational_profiles() -> list[int]:
    """Populate only completely unconfigured staff schedules from verified MK II metadata."""
    initialize_database()
    updated_ids: list[int] = []
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, consultation_rooms, consultation_schedules
                FROM accounts
                WHERE role = 'staff'
                  AND status = 'active'
                """
            )
            staff_rows = cursor.fetchall()
            for staff in staff_rows:
                if not (
                    _is_empty_json_list(staff.get("consultation_rooms"))
                    and _is_empty_json_list(staff.get("consultation_schedules"))
                ):
                    continue
                cursor.execute(
                    """
                    UPDATE accounts
                    SET consultation_rooms = %s,
                        consultation_schedules = %s
                    WHERE id = %s
                      AND role = 'staff'
                    """,
                    (
                        _json_column_value(list(APPROVED_CONSULTATION_ROOMS)),
                        _json_column_value(list(APPROVED_CONSULTATION_SCHEDULES)),
                        staff["id"],
                    ),
                )
                if cursor.rowcount == 1:
                    updated_ids.append(int(staff["id"]))
        connection.commit()
    return updated_ids


def _seed_accounts() -> list[tuple[Any, ...]]:
    accounts = [
        {
            "email": config.SEED_STUDENT_EMAIL,
            "full_name": config.SEED_STUDENT_NAME,
            "student_number": config.SEED_STUDENT_NUMBER,
            "staff_number": None,
            "password": config.SEED_STUDENT_PASSWORD,
            "role": "student",
            "program": config.SEED_STUDENT_PROGRAM,
            "gender": config.SEED_STUDENT_GENDER,
        },
        {
            "email": config.SEED_STUDENT2_EMAIL,
            "full_name": config.SEED_STUDENT2_NAME,
            "student_number": config.SEED_STUDENT2_NUMBER,
            "staff_number": None,
            "password": config.SEED_STUDENT2_PASSWORD,
            "role": "student",
            "program": config.SEED_STUDENT2_PROGRAM,
            "gender": config.SEED_STUDENT2_GENDER,
        },
        {
            "email": config.SEED_STAFF_EMAIL,
            "full_name": config.SEED_STAFF_NAME,
            "student_number": None,
            "staff_number": config.SEED_STAFF_NUMBER,
            "password": config.SEED_STAFF_PASSWORD,
            "role": "staff",
            "program": None,  
            "assigned_programs": [config.SEED_STUDENT_PROGRAM],
            "gender": config.SEED_STAFF_GENDER,
        },
        {
            "email": config.SEED_STAFF2_EMAIL,
            "full_name": config.SEED_STAFF2_NAME,
            "student_number": None,
            "staff_number": config.SEED_STAFF2_NUMBER,
            "password": config.SEED_STAFF2_PASSWORD,
            "role": "staff",
            "program": None,
            "assigned_programs": [config.SEED_STUDENT2_PROGRAM],
            "gender": config.SEED_STAFF2_GENDER,
        },
        {
            "email": config.SEED_ADMIN_EMAIL,
            "full_name": config.SEED_ADMIN_NAME,
            "student_number": None,
            "staff_number": None,
            "password": config.SEED_ADMIN_PASSWORD,
            "role": "admin",
            "program": None,
            "gender": config.SEED_ADMIN_GENDER,
        },
    ]

    # Seed row order matches the accounts table schema.
    rows: list[tuple[Any, ...]] = []
    for account in accounts:
        email = str(account["email"]).strip().lower()
        password = str(account["password"])
        full_name = str(account["full_name"]).strip()
        student_number = account.get("student_number")
        staff_number = account.get("staff_number")
        gender = account.get("gender")
        program = account.get("program", None)
        assigned_programs = account.get("assigned_programs")
        office = None
        support_statement = None
        consultation_rooms = None
        consultation_schedules = None
        role = str(account["role"]).strip().lower()

        if not email or not password or not full_name:
            continue

        rows.append(
            (
                email,
                generate_password_hash(password),
                full_name,
                student_number,
                staff_number,
                gender,
                program,
                _json_column_value(assigned_programs),
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                role,
                "active",
                current_time(),
            )
        )

    return rows

def seed_database() -> None:
    initialize_database()

    seed_rows = _seed_accounts()

    if not seed_rows:
        return

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT IGNORE INTO accounts (
                    email,
                    password_hash,
                    full_name,
                    student_number,
                    staff_number,
                    gender,
                    program,
                    assigned_programs,
                    office,
                    support_statement,
                    consultation_rooms,
                    consultation_schedules,
                    role,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                seed_rows,
            )
            for email, programs in (
                (config.SEED_STAFF_EMAIL, [config.SEED_STUDENT_PROGRAM]),
                (config.SEED_STAFF2_EMAIL, [config.SEED_STUDENT2_PROGRAM]),
            ):
                cursor.execute(
                    """
                    UPDATE accounts
                    SET assigned_programs = %s
                    WHERE email = %s
                      AND role = 'staff'
                      AND (
                          assigned_programs IS NULL
                          OR JSON_LENGTH(assigned_programs) = 0
                      )
                    """,
                    (_json_column_value(programs), email),
                )
            cursor.execute(
                """
                INSERT INTO settings (setting_key, setting_value, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    setting_value = VALUES(setting_value),
                    updated_at = VALUES(updated_at)
                """,
                (
                    "currentAdmissionYear",
                    "2024",
                    current_time(),
                ),
            )
        connection.commit()


# --- Automatic account number generation ---
def generate_next_student_number() -> str:
    initialize_database()

    admission_year = str(load_settings().get("currentAdmissionYear", "2024"))

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT student_number
                FROM accounts
                WHERE student_number LIKE %s
                ORDER BY student_number DESC
                LIMIT 1
                """,
                (f"{admission_year}-%",),
            )
            row = cursor.fetchone()

    if not row or not row[0]:
        return f"{admission_year}-00001"

    last = int(str(row[0]).split("-")[1]) + 1
    return f"{admission_year}-{last:05d}"


def generate_next_staff_number() -> str:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT staff_number
                FROM accounts
                WHERE staff_number IS NOT NULL
                ORDER BY staff_number DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()

    if not row or not row[0]:
        return "STF-0001"

    last = int(str(row[0]).replace("STF-", "")) + 1
    return f"STF-{last:04d}"


def _appointment_status_enum_definition(statuses: tuple[str, ...]) -> str:
    return ", ".join(f"'{status}'" for status in statuses)


def _migrate_appointment_status_enum(cursor: Any) -> None:
    cursor.execute(
        """
        SELECT COLUMN_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'appointments'
          AND COLUMN_NAME = 'status'
        """,
        (config.DB_NAME,),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("Unable to inspect the appointments status column.")

    column_type = str(row[0])
    if not column_type.casefold().startswith("enum("):
        raise RuntimeError("Appointments status column must be an ENUM.")

    configured_statuses = tuple(re.findall(r"'([^']*)'", column_type))
    if set(configured_statuses) == set(APPOINTMENT_STATUSES):
        return

    unexpected_schema_statuses = (
        set(configured_statuses) - _MIGRATION_KNOWN_APPOINTMENT_STATUSES
    )
    if unexpected_schema_statuses:
        raise RuntimeError("Appointments status column contains unsupported values.")

    cursor.execute("SELECT DISTINCT status FROM appointments")
    stored_statuses = {str(status_row[0]) for status_row in cursor.fetchall()}
    unexpected_stored_statuses = (
        stored_statuses - _MIGRATION_KNOWN_APPOINTMENT_STATUSES
    )
    if unexpected_stored_statuses:
        raise RuntimeError("Appointments contain unsupported status values.")

    transitional_statuses = (
        _MIGRATION_LEGACY_APPOINTMENT_STATUSES + APPOINTMENT_STATUSES
    )
    cursor.execute(
        f"""
        ALTER TABLE appointments
        MODIFY COLUMN status ENUM({_appointment_status_enum_definition(transitional_statuses)})
        NOT NULL DEFAULT 'pending'
        """
    )
    for legacy_status, target_status in (
        ("approved", "confirmed"),
        ("done", "completed"),
        ("did_not_attend", "cancelled"),
    ):
        cursor.execute(
            "UPDATE appointments SET status = %s WHERE status = %s",
            (target_status, legacy_status),
        )
    cursor.execute(
        f"""
        ALTER TABLE appointments
        MODIFY COLUMN status ENUM({_appointment_status_enum_definition(APPOINTMENT_STATUSES)})
        NOT NULL DEFAULT 'pending'
        """
    )


def _column_exists(cursor: Any, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (config.DB_NAME, table_name, column_name),
    )
    return cursor.fetchone() is not None


def _migrate_conversation_management_schema(cursor: Any) -> None:
    if _column_exists(cursor, "conversation_summaries", "transcript_json"):
        # Preserve only legacy flagged-case transcripts before removing the
        # retired general-summary column. Raw conversations now have their own
        # staff-only table and are never retained for routine conversations.
        cursor.execute(
            """
            INSERT INTO flagged_conversation_transcripts (
                conversation_summary_id,
                transcript_json,
                created_at,
                updated_at
            )
            SELECT id, transcript_json, created_at, created_at
            FROM conversation_summaries
            WHERE flagged_status = 1
              AND transcript_json IS NOT NULL
            ON DUPLICATE KEY UPDATE
                transcript_json = VALUES(transcript_json),
                updated_at = VALUES(updated_at)
            """
        )
        cursor.execute(
            """
            ALTER TABLE conversation_summaries
            DROP COLUMN transcript_json
            """
        )

    if not _column_exists(cursor, "escalations", "escalation_reason"):
        cursor.execute(
            """
            ALTER TABLE escalations
            ADD COLUMN escalation_reason VARCHAR(255) NULL
            """
        )

    if not _column_exists(cursor, "escalations", "reviewed_at"):
        cursor.execute(
            """
            ALTER TABLE escalations
            ADD COLUMN reviewed_at DATETIME NULL
            """
        )


def _migrate_chatbot_feedback_schema(cursor: Any) -> None:
    """Add privacy-safe quality metadata without adding transcript storage."""
    if not _column_exists(cursor, "chatbot_feedback", "response_context"):
        cursor.execute(
            """
            ALTER TABLE chatbot_feedback
            ADD COLUMN response_context VARCHAR(50) NULL
            """
        )


def _migrate_staff_appointment_preferences_schema(cursor: Any) -> None:
    """Add per-counselor booking preferences without replacing existing profiles."""
    slots_added = not _column_exists(cursor, "accounts", "appointment_slots")
    modes_added = not _column_exists(cursor, "accounts", "consultation_modes")
    if slots_added:
        cursor.execute(
            """
            ALTER TABLE accounts
            ADD COLUMN appointment_slots JSON NULL
            """
        )
    if modes_added:
        cursor.execute(
            """
            ALTER TABLE accounts
            ADD COLUMN consultation_modes JSON NULL
            """
        )

    # Preserve current booking behavior for existing counselors while giving
    # each account an independent value they can now change themselves.
    if slots_added:
        cursor.execute(
            """
            UPDATE accounts
            SET appointment_slots = JSON_ARRAY(
                    '08:00 AM', '09:00 AM', '10:00 AM',
                    '01:00 PM', '02:00 PM', '03:00 PM'
                )
            WHERE role = 'staff'
              AND appointment_slots IS NULL
            """
        )
    if modes_added:
        cursor.execute(
            """
            UPDATE accounts
            SET consultation_modes = JSON_ARRAY('Online', 'Onsite')
            WHERE role = 'staff'
              AND consultation_modes IS NULL
            """
        )


def initialize_database() -> None:
    # Creating a database requires server-wide CREATE privileges. Production
    # deployments provision the database explicitly, then run with a
    # database-scoped application account. Development retains the convenient
    # create-if-missing behavior.
    if config.DATABASE_INITIALIZE_ON_START:
        with _server_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET {config.DB_CHARSET} COLLATE {config.DB_CHARSET}_unicode_ci"
                )
            connection.commit()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255) NOT NULL,
                    student_number VARCHAR(20) NULL UNIQUE,
                    staff_number VARCHAR(20) NULL UNIQUE,
                    gender ENUM(
                        'Male',
                        'Female',
                        'Prefer not to say',
                        'Other'
                    ) NULL,
                    program VARCHAR(100) NULL,
                    assigned_programs JSON NULL,
                    office VARCHAR(255) NULL,
                    support_statement TEXT NULL,
                    consultation_rooms JSON NULL,
                    consultation_schedules JSON NULL,
                    appointment_slots JSON NULL,
                    consultation_modes JSON NULL,
                    role ENUM(
                        'student',
                        'staff',
                        'admin'
                    ) NOT NULL DEFAULT 'student',
                    status ENUM(
                        'active',
                        'disabled'
                    ) NOT NULL DEFAULT 'active',
                    created_at DATETIME NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS inquiries (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NULL,
                    inquiry_type VARCHAR(100) NOT NULL,
                    emotion_result VARCHAR(100) NOT NULL,
                    escalated TINYINT(1) NOT NULL DEFAULT 0,
                    appointment_recommended TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (account_id)
                    REFERENCES accounts(id)
                    ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NULL,
                    primary_concern VARCHAR(255) NOT NULL,
                    conversation_type VARCHAR(100) NOT NULL,
                    emotion_results VARCHAR(255) NOT NULL,
                    flagged_status TINYINT(1) NOT NULL DEFAULT 0,
                    appointment_recommendation VARCHAR(255) NOT NULL,
                    recommendations TEXT NULL,
                    suggested_intervention TEXT NULL,
                    language_used VARCHAR(50) NOT NULL,
                    total_messages INT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (account_id)
                    REFERENCES accounts(id)
                    ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS flagged_conversation_transcripts (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_summary_id INT NOT NULL UNIQUE,
                    transcript_json MEDIUMTEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE CASCADE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS escalations (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NULL,
                    summary_id INT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    escalation_reason VARCHAR(255) NULL,
                    intervention_notes TEXT NULL,
                    created_at DATETIME NOT NULL,
                    resolved_at DATETIME NULL,
                    reviewed_at DATETIME NULL,
                    FOREIGN KEY (account_id)
                    REFERENCES accounts(id)
                    ON DELETE SET NULL,
                    FOREIGN KEY (summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS case_notes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_summary_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_case_notes_summary_created (
                        conversation_summary_id,
                        created_at
                    ),
                    INDEX idx_case_notes_staff (staff_account_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_summary_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    destination VARCHAR(100) NOT NULL,
                    referral_reason TEXT NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_referrals_summary_created (
                        conversation_summary_id,
                        created_at
                    ),
                    INDEX idx_referrals_status (status)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS referral_status_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    referral_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (referral_id)
                    REFERENCES referrals(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_referral_status_history_referral_created (
                        referral_id,
                        created_at
                    )
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS referral_notes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    referral_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    note_text TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (referral_id)
                    REFERENCES referrals(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_referral_notes_referral_created (
                        referral_id,
                        created_at
                    )
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS interventions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_summary_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    intervention_type VARCHAR(100) NOT NULL,
                    objective TEXT NOT NULL,
                    progress_status VARCHAR(50) NOT NULL DEFAULT 'planned',
                    outcome TEXT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_interventions_summary_created (
                        conversation_summary_id,
                        created_at
                    ),
                    INDEX idx_interventions_progress_status (progress_status)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS intervention_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    intervention_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    progress_status VARCHAR(50) NOT NULL,
                    outcome TEXT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (intervention_id)
                    REFERENCES interventions(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_intervention_history_intervention_created (
                        intervention_id,
                        created_at
                    )
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS case_confidentiality (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    conversation_summary_id INT NOT NULL UNIQUE,
                    staff_account_id INT NOT NULL,
                    confidentiality_status VARCHAR(50) NOT NULL,
                    confidentiality_reason TEXT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_case_confidentiality_status (confidentiality_status)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS case_confidentiality_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    case_confidentiality_id INT NOT NULL,
                    staff_account_id INT NOT NULL,
                    confidentiality_status VARCHAR(50) NOT NULL,
                    confidentiality_reason TEXT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (case_confidentiality_id)
                    REFERENCES case_confidentiality(id)
                    ON DELETE RESTRICT,
                    FOREIGN KEY (staff_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_case_confidentiality_history_record_created (
                        case_confidentiality_id,
                        created_at
                    )
                )
                """
            )
            _migrate_conversation_management_schema(cursor)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS appointments (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NOT NULL,
                    contact_number VARCHAR(20) NOT NULL,
                    appointment_category VARCHAR(100) NOT NULL,
                    appointment_mode VARCHAR(50) NOT NULL,
                    preferred_date DATE NOT NULL,
                    preferred_time_slot VARCHAR(20) NOT NULL,
                    reason TEXT NOT NULL,
                    status ENUM(
                        'pending',
                        'confirmed',
                        'cancelled',
                        'rejected',
                        'completed'
                    ) NOT NULL DEFAULT 'pending',
                    counselor_notes TEXT NULL,
                    appointment_source ENUM(
                        'chatbot',
                        'walk_in',
                        'hotline',
                        'messenger',
                        'email',
                        'staff_manual'
                    ) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    recipient_account_id INT NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    message TEXT NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    is_read TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (recipient_account_id)
                    REFERENCES accounts(id)
                    ON DELETE RESTRICT,
                    INDEX idx_notifications_recipient_created (
                        recipient_account_id,
                        created_at
                    )
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chatbot_feedback (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    account_id INT NULL,
                    conversation_summary_id INT NULL,
                    response_token_hash CHAR(64) NOT NULL UNIQUE,
                    category VARCHAR(50) NOT NULL,
                    comment VARCHAR(500) NULL,
                    response_context VARCHAR(50) NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (account_id)
                    REFERENCES accounts(id)
                    ON DELETE SET NULL,
                    FOREIGN KEY (conversation_summary_id)
                    REFERENCES conversation_summaries(id)
                    ON DELETE SET NULL,
                    INDEX idx_chatbot_feedback_account_created (
                        account_id,
                        created_at
                    ),
                    INDEX idx_chatbot_feedback_summary (
                        conversation_summary_id
                    )
                )
                """
            )
            _migrate_chatbot_feedback_schema(cursor)
            _migrate_staff_appointment_preferences_schema(cursor)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    setting_key VARCHAR(100) NOT NULL UNIQUE,
                    setting_value TEXT NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
            _migrate_appointment_status_enum(cursor)
        connection.commit()


def save_inquiry(payload: dict[str, Any]) -> int:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO inquiries (
                    account_id,
                    inquiry_type,
                    emotion_result,
                    escalated,
                    appointment_recommended,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.get("account_id"),
                    payload["inquiry_type"],
                    payload["emotion_result"],
                    1 if payload.get("escalated") else 0,
                    1 if payload.get("appointment_recommended") else 0,
                    payload.get("created_at", current_time()),
                ),
            )
            inquiry_id = cursor.lastrowid
        connection.commit()
        return int(inquiry_id)

def save_escalation(payload: dict[str, Any]) -> int:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO escalations (
                    account_id,
                    summary_id,
                    status,
                    escalation_reason,
                    intervention_notes,
                    created_at,
                    resolved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.get("account_id"),
                    payload.get("summary_id"),
                    payload.get("status", "pending"),
                    payload.get("escalation_reason"),
                    payload.get("intervention_notes"),
                    payload.get("created_at", current_time()),
                    payload.get("resolved_at"),
                ),
            )
            escalation_id = cursor.lastrowid
        connection.commit()
        return int(escalation_id)


def _insert_appointment_row(cursor: Any, payload: dict[str, Any]) -> int:
    """Insert one already-validated appointment using the active connection."""
    cursor.execute(
        """
        INSERT INTO appointments (
            account_id,
            contact_number,
            appointment_category,
            appointment_mode,
            preferred_date,
            preferred_time_slot,
            reason,
            status,
            counselor_notes,
            appointment_source,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            payload["account_id"],
            payload["contact_number"],
            payload["appointment_category"],
            payload["appointment_mode"],
            payload["preferred_date"],
            payload["preferred_time_slot"],
            payload["reason"],
            payload.get("status", "pending"),
            payload.get("counselor_notes"),
            payload["appointment_source"],
            payload.get("created_at", current_time()),
            payload.get("updated_at", current_time()),
        ),
    )
    return int(cursor.lastrowid)


def _appointment_conflict_lock_name(
    preferred_date: object,
    normalized_time_slot: object,
) -> str:
    """Return a bounded, non-sensitive advisory-lock identifier for one slot."""
    key_material = (
        f"{config.DB_NAME}|{preferred_date}|{normalized_time_slot}"
    ).encode("utf-8")
    return f"ctrl4:{sha256(key_material).hexdigest()[:58]}"


def save_appointment_if_available(
    payload: dict[str, Any],
    *,
    normalized_time_slot: str,
    equivalent_time_slots: tuple[str, ...],
) -> int:
    """Atomically reserve a start-time slot and persist an appointment.

    The service supplies the already-normalized slot and equivalent stored
    representations.  This helper intentionally does not parse appointment
    times or decide booking policy; it serializes one persistence key, applies
    the final blocking-status recheck, and writes only when the slot is free.
    """
    if not equivalent_time_slots:
        raise ValueError("Equivalent appointment time slots are required.")

    lock_name = _appointment_conflict_lock_name(
        payload["preferred_date"],
        normalized_time_slot,
    )
    lock_acquired = False

    with _database_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT GET_LOCK(%s, %s)",
                    (lock_name, APPOINTMENT_CONFLICT_LOCK_TIMEOUT_SECONDS),
                )
                lock_result = cursor.fetchone()
                lock_acquired = bool(lock_result and lock_result[0] == 1)
                if not lock_acquired:
                    raise AppointmentConflictLockError()

            # Advisory locks are connection-scoped, not transaction-scoped.
            # End the lock-acquisition read before the write transaction starts.
            connection.commit()
            connection.start_transaction()
            with connection.cursor() as cursor:
                slot_placeholders = ", ".join(["%s"] * len(equivalent_time_slots))
                status_placeholders = ", ".join(
                    ["%s"] * len(APPOINTMENT_CONFLICT_BLOCKING_STATUSES)
                )
                cursor.execute(
                    f"""
                    SELECT 1
                    FROM appointments
                    WHERE preferred_date = %s
                      AND status IN ({status_placeholders})
                      AND TRIM(preferred_time_slot) IN ({slot_placeholders})
                    LIMIT 1
                    """,
                    (
                        payload["preferred_date"],
                        *APPOINTMENT_CONFLICT_BLOCKING_STATUSES,
                        *equivalent_time_slots,
                    ),
                )
                if cursor.fetchone() is not None:
                    raise AppointmentConflictPersistenceError()

                appointment_id = _insert_appointment_row(cursor, payload)
            connection.commit()
            return appointment_id
        except Exception:
            connection.rollback()
            raise
        finally:
            if lock_acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                    cursor.fetchone()

def list_appointments_by_date(
    preferred_date: str,
) -> list[dict[str, Any]]:
    return fetch_rows(
        """
        SELECT preferred_time_slot, status
        FROM appointments
        WHERE preferred_date = %s
        """,
        (preferred_date,),
    )


def save_notification(payload: dict[str, Any]) -> int:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notifications (
                    recipient_account_id,
                    title,
                    message,
                    type,
                    is_read,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    payload["recipient_account_id"],
                    payload["title"],
                    payload["message"],
                    payload["type"],
                    1 if payload.get("is_read") else 0,
                    payload.get("created_at", current_time()),
                ),
            )
            notification_id = cursor.lastrowid
        connection.commit()

    return int(notification_id)


def save_chatbot_feedback(payload: dict[str, Any]) -> int:
    """Persist one student rating without storing either chat message."""
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chatbot_feedback (
                    account_id,
                    conversation_summary_id,
                    response_token_hash,
                    category,
                    comment,
                    response_context,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload["account_id"],
                    payload.get("conversation_summary_id"),
                    payload["response_token_hash"],
                    payload["category"],
                    payload.get("comment"),
                    payload.get("response_context"),
                    payload.get("created_at", current_time()),
                ),
            )
            feedback_id = cursor.lastrowid
        connection.commit()
    return int(feedback_id)


def list_chatbot_feedback_for_programs(programs: object) -> list[dict[str, Any]]:
    """Return feedback only for active students in authorized programs."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT
            chatbot_feedback.id AS feedback_id,
            chatbot_feedback.conversation_summary_id,
            chatbot_feedback.category,
            chatbot_feedback.comment,
            chatbot_feedback.response_context,
            chatbot_feedback.created_at,
            accounts.full_name AS student_name,
            accounts.student_number,
            accounts.program
        FROM chatbot_feedback
        INNER JOIN accounts
            ON accounts.id = chatbot_feedback.account_id
        WHERE accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY chatbot_feedback.created_at DESC, chatbot_feedback.id DESC
        LIMIT 100
        """,
        authorized_programs,
    )


def list_notifications_for_recipient(
    recipient_account_id: int,
) -> list[dict[str, Any]]:
    return fetch_rows(
        """
        SELECT
            id,
            title,
            message,
            type,
            is_read,
            created_at
        FROM notifications
        WHERE recipient_account_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        (recipient_account_id,),
    )


def mark_notification_read(
    notification_id: int,
    recipient_account_id: int,
) -> bool:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM notifications
                WHERE id = %s
                  AND recipient_account_id = %s
                LIMIT 1
                """,
                (notification_id, recipient_account_id),
            )
            if not cursor.fetchone():
                return False

            cursor.execute(
                """
                UPDATE notifications
                SET is_read = 1
                WHERE id = %s
                  AND recipient_account_id = %s
                """,
                (notification_id, recipient_account_id),
            )
        connection.commit()

    return True

def save_conversation_summary(payload: dict[str, Any]) -> int:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_summaries (
                    account_id,
                    primary_concern,
                    conversation_type,
                    emotion_results,
                    flagged_status,
                    appointment_recommendation,
                    recommendations,
                    suggested_intervention,
                    language_used,
                    total_messages,
                    summary,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload.get("account_id"),
                    payload["primary_concern"],
                    payload["conversation_type"],
                    payload["emotion_results"],
                    1 if payload.get("flagged_status") else 0,
                    payload["appointment_recommendation"],
                    payload.get("recommendations"),
                    payload.get("suggested_intervention"),
                    payload["language_used"],
                    payload["total_messages"],
                    payload["summary"],
                    payload.get("created_at", current_time()),
                ),
            )

            summary_id = cursor.lastrowid

        connection.commit()

    return int(summary_id)


def ensure_active_conversation_summary(account_id: int) -> int:
    """Return one privacy-safe Inbox placeholder for an active student chat."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM conversation_summaries
                WHERE account_id = %s
                  AND conversation_type = 'active'
                ORDER BY id DESC
                LIMIT 1
                """,
                (account_id,),
            )
            existing = cursor.fetchone()
            if existing:
                return int(existing[0])

            cursor.execute(
                """
                INSERT INTO conversation_summaries (
                    account_id,
                    primary_concern,
                    conversation_type,
                    emotion_results,
                    flagged_status,
                    appointment_recommendation,
                    recommendations,
                    suggested_intervention,
                    language_used,
                    total_messages,
                    summary,
                    created_at
                )
                VALUES (%s, %s, 'active', %s, 0, %s, NULL, NULL, %s, 0, %s, %s)
                """,
                (
                    account_id,
                    "Conversation in progress",
                    "Pending",
                    "Pending",
                    "Pending",
                    "Conversation in progress",
                    current_time(),
                ),
            )
            summary_id = cursor.lastrowid
        connection.commit()

    return int(summary_id)


def finalize_active_conversation_summary(
    summary_id: int,
    account_id: int,
    payload: dict[str, Any],
) -> bool:
    """Replace an active placeholder with the final privacy-safe AI summary."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversation_summaries
                SET primary_concern = %s,
                    conversation_type = %s,
                    emotion_results = %s,
                    flagged_status = %s,
                    appointment_recommendation = %s,
                    recommendations = %s,
                    suggested_intervention = %s,
                    language_used = %s,
                    total_messages = %s,
                    summary = %s
                WHERE id = %s
                  AND account_id = %s
                  AND conversation_type = 'active'
                """,
                (
                    payload["primary_concern"],
                    payload["conversation_type"],
                    payload["emotion_results"],
                    1 if payload.get("flagged_status") else 0,
                    payload["appointment_recommendation"],
                    payload.get("recommendations"),
                    payload.get("suggested_intervention"),
                    payload["language_used"],
                    payload["total_messages"],
                    payload["summary"],
                    summary_id,
                    account_id,
                ),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def mark_active_conversation_escalated(summary_id: int, account_id: int) -> bool:
    """Mark an active Inbox placeholder as a pending high-risk conversation."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversation_summaries
                SET primary_concern = 'Crisis Concern',
                    emotion_results = 'Crisis',
                    flagged_status = 1,
                    appointment_recommendation = 'Immediate Guidance Office review',
                    recommendations = 'Immediate Guidance Office review is recommended.',
                    suggested_intervention = 'Immediate Guidance Office review is recommended.'
                WHERE id = %s
                  AND account_id = %s
                  AND conversation_type = 'active'
                """,
                (summary_id, account_id),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def mark_active_conversation_for_staff_review(summary_id: int, account_id: int) -> bool:
    """Mark an active Inbox placeholder for counselor review without crisis labeling."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversation_summaries
                SET primary_concern = 'Wellbeing Concern',
                    flagged_status = 1,
                    appointment_recommendation = 'Guidance Office review recommended',
                    recommendations = 'Guidance Office review is recommended.',
                    suggested_intervention = 'Guidance Office review is recommended.'
                WHERE id = %s
                  AND account_id = %s
                  AND conversation_type = 'active'
                """,
                (summary_id, account_id),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def ensure_pending_escalation(
    account_id: int,
    summary_id: int,
    escalation_reason: str,
) -> bool:
    """Create one pending escalation for a summary, returning whether it was new."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO escalations (
                    account_id,
                    summary_id,
                    status,
                    escalation_reason,
                    created_at
                )
                SELECT %s, %s, 'pending', %s, %s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM escalations
                    WHERE summary_id = %s
                      AND status = 'pending'
                )
                """,
                (
                    account_id,
                    summary_id,
                    escalation_reason,
                    current_time(),
                    summary_id,
                ),
            )
            created = cursor.rowcount == 1
        connection.commit()

    return created


def discard_active_conversation_summary(summary_id: int, account_id: int) -> bool:
    """Discard an unused active placeholder when a pending crisis case is refreshed."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM conversation_summaries
                WHERE id = %s
                  AND account_id = %s
                  AND conversation_type = 'active'
                """,
                (summary_id, account_id),
            )
            deleted = cursor.rowcount == 1
        connection.commit()

    return deleted


def fetch_open_conversation_case(account_id: int) -> dict[str, Any] | None:
    """Return the student's current pending flagged case without transcript data."""
    rows = fetch_rows(
        """
        SELECT
            conversation_summaries.id AS summary_id,
            conversation_summaries.summary,
            conversation_summaries.total_messages,
            conversation_summaries.created_at
        FROM conversation_summaries
        INNER JOIN escalations
            ON escalations.summary_id = conversation_summaries.id
        WHERE conversation_summaries.account_id = %s
          AND conversation_summaries.flagged_status = 1
          AND escalations.status = 'pending'
        ORDER BY escalations.created_at DESC, escalations.id DESC
        LIMIT 1
        """,
        (account_id,),
    )
    return rows[0] if rows else None


def refresh_open_conversation_summary(
    summary_id: int,
    summary: str,
    total_messages: int,
) -> bool:
    """Refresh an open case summary while retaining its original timestamp."""
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE conversation_summaries
                SET summary = %s,
                    total_messages = %s
                WHERE id = %s
                  AND flagged_status = 1
                """,
                (summary, total_messages, summary_id),
            )
            updated = cursor.rowcount == 1
        connection.commit()
    return updated

def list_conversation_summaries() -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT *
        FROM conversation_summaries
        ORDER BY created_at DESC
        """
    )


def _normalized_programs(programs: object) -> tuple[str, ...]:
    if not isinstance(programs, (list, tuple, set)):
        return ()
    return tuple(
        dict.fromkeys(
            str(program).strip()
            for program in programs
            if str(program).strip()
        )
    )


def _student_program_scope_clause(
    account_column: str,
    programs: object | None,
) -> tuple[str, tuple[str, ...]]:
    """Build a fail-closed student-program filter for internal scoped queries."""
    if programs is None:
        return "", ()

    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return " AND 1 = 0", ()

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return (
        f"""
        AND {account_column} IN (
            SELECT id
            FROM accounts
            WHERE role = 'student'
              AND status = 'active'
              AND program IN ({placeholders})
        )
        """,
        authorized_programs,
    )


def list_inquiries_for_programs(programs: object) -> list[dict[str, Any]]:
    """Return inquiry metadata only for students in the supplied programs."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT inquiries.*
        FROM inquiries
        INNER JOIN accounts
            ON accounts.id = inquiries.account_id
        WHERE accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY inquiries.id DESC
        LIMIT 100
        """,
        authorized_programs,
    )


def list_conversation_summaries_for_programs(programs: object) -> list[dict[str, Any]]:
    """Return finalized summaries only for students in the supplied programs."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT conversation_summaries.*
        FROM conversation_summaries
        INNER JOIN accounts
            ON accounts.id = conversation_summaries.account_id
        WHERE accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
          AND conversation_summaries.conversation_type <> 'active'
        ORDER BY conversation_summaries.created_at DESC
        """,
        authorized_programs,
    )


def list_escalations_for_programs(programs: object) -> list[dict[str, Any]]:
    """Return escalation metadata only for students in the supplied programs."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT escalations.*
        FROM escalations
        INNER JOIN conversation_summaries
            ON conversation_summaries.id = escalations.summary_id
        INNER JOIN accounts
            ON accounts.id = conversation_summaries.account_id
        WHERE accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY escalations.id DESC
        LIMIT 100
        """,
        authorized_programs,
    )


def list_staff_inbox_summaries(programs: object) -> list[dict[str, Any]]:
    """Return the newest active or finalized item per authorized student program."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT
            conversation_summaries.id AS summary_id,
            accounts.id AS student_account_id,
            accounts.full_name AS student_name,
            accounts.student_number,
            accounts.program,
            conversation_summaries.primary_concern,
            conversation_summaries.conversation_type,
            conversation_summaries.emotion_results,
            conversation_summaries.flagged_status,
            conversation_summaries.appointment_recommendation,
            conversation_summaries.recommendations,
            conversation_summaries.suggested_intervention,
            conversation_summaries.language_used,
            conversation_summaries.total_messages,
            conversation_summaries.summary,
            conversation_summaries.created_at,
            escalations.status AS escalation_status,
            escalations.escalation_reason,
            escalations.created_at AS escalation_created_at,
            escalations.reviewed_at,
            EXISTS(
                SELECT 1
                FROM referrals
                WHERE referrals.conversation_summary_id = conversation_summaries.id
            ) AS has_referral,
            EXISTS(
                SELECT 1
                FROM interventions
                WHERE interventions.conversation_summary_id = conversation_summaries.id
            ) AS has_intervention
        FROM conversation_summaries
        INNER JOIN (
            SELECT
                summaries.account_id,
                COALESCE(
                    MAX(
                        CASE
                            WHEN pending_escalations.status = 'pending'
                             AND summaries.flagged_status = 1
                            THEN summaries.id
                        END
                    ),
                    MAX(
                        CASE
                            WHEN reviewed_escalations.status = 'reviewed'
                             AND reviewed_escalations.reviewed_at IS NOT NULL
                             AND NOT EXISTS (
                                 SELECT 1
                                 FROM conversation_summaries AS later_summaries
                                 WHERE later_summaries.account_id = summaries.account_id
                                   AND later_summaries.created_at > reviewed_escalations.reviewed_at
                             )
                            THEN summaries.id
                        END
                    ),
                    MAX(summaries.id)
                ) AS selected_summary_id
            FROM conversation_summaries AS summaries
            LEFT JOIN escalations AS pending_escalations
                ON pending_escalations.summary_id = summaries.id
               AND pending_escalations.status = 'pending'
            LEFT JOIN escalations AS reviewed_escalations
                ON reviewed_escalations.summary_id = summaries.id
               AND reviewed_escalations.status = 'reviewed'
            WHERE summaries.account_id IS NOT NULL
            GROUP BY summaries.account_id
            HAVING
                MAX(
                    CASE
                        WHEN summaries.conversation_type = 'active' THEN 1
                        ELSE 0
                    END
                ) = 0
                OR MAX(
                    CASE
                        WHEN pending_escalations.status = 'pending'
                         AND summaries.flagged_status = 1
                        THEN 1
                        ELSE 0
                    END
                ) = 1

            UNION

            SELECT account_id, id AS selected_summary_id
            FROM conversation_summaries
            WHERE conversation_type = 'active'
        ) AS selected_summary
            ON selected_summary.selected_summary_id = conversation_summaries.id
        INNER JOIN accounts
            ON accounts.id = conversation_summaries.account_id
        LEFT JOIN escalations
            ON escalations.id = (
                SELECT MAX(escalation.id)
                FROM escalations AS escalation
                WHERE escalation.summary_id = conversation_summaries.id
            )
        WHERE accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY
            CASE
                WHEN escalations.status = 'pending' THEN 0
                WHEN conversation_summaries.flagged_status = 1 THEN 1
                ELSE 2
            END ASC,
            conversation_summaries.created_at DESC,
            conversation_summaries.id DESC
        """,
        authorized_programs,
    )


def list_staff_flagged_case_summaries(programs: object) -> list[dict[str, Any]]:
    """Return all pending and reviewed flagged cases within staff program scope."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT
            conversation_summaries.id AS summary_id,
            accounts.id AS student_account_id,
            accounts.full_name AS student_name,
            accounts.student_number,
            accounts.program,
            conversation_summaries.primary_concern,
            conversation_summaries.conversation_type,
            conversation_summaries.emotion_results,
            conversation_summaries.flagged_status,
            conversation_summaries.appointment_recommendation,
            conversation_summaries.recommendations,
            conversation_summaries.suggested_intervention,
            conversation_summaries.language_used,
            conversation_summaries.total_messages,
            conversation_summaries.summary,
            conversation_summaries.created_at,
            escalations.status AS escalation_status,
            escalations.escalation_reason,
            escalations.created_at AS escalation_created_at,
            escalations.reviewed_at,
            EXISTS(
                SELECT 1
                FROM referrals
                WHERE referrals.conversation_summary_id = conversation_summaries.id
            ) AS has_referral,
            EXISTS(
                SELECT 1
                FROM interventions
                WHERE interventions.conversation_summary_id = conversation_summaries.id
            ) AS has_intervention
        FROM conversation_summaries
        INNER JOIN accounts
            ON accounts.id = conversation_summaries.account_id
        INNER JOIN escalations
            ON escalations.id = (
                SELECT MAX(escalation.id)
                FROM escalations AS escalation
                WHERE escalation.summary_id = conversation_summaries.id
            )
        WHERE conversation_summaries.flagged_status = 1
          AND escalations.status IN ('pending', 'reviewed')
          AND accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY
            CASE WHEN escalations.status = 'pending' THEN 0 ELSE 1 END ASC,
            COALESCE(escalations.reviewed_at, conversation_summaries.created_at) DESC,
            conversation_summaries.id DESC
        """,
        authorized_programs,
    )


def list_staff_reviewed_case_history(
    anchor_summary_id: int,
    programs: object,
) -> list[dict[str, Any]]:
    """Return reviewed flagged cases for the student attached to one safe anchor."""
    authorized_programs = _normalized_programs(programs)
    if not authorized_programs:
        return []

    placeholders = ", ".join(["%s"] * len(authorized_programs))
    return fetch_rows(
        f"""
        SELECT
            reviewed_summaries.id AS summary_id,
            accounts.full_name AS student_name,
            accounts.student_number,
            accounts.program,
            reviewed_summaries.primary_concern,
            reviewed_summaries.emotion_results,
            reviewed_summaries.flagged_status,
            reviewed_summaries.summary,
            reviewed_summaries.created_at,
            reviewed_escalations.status AS escalation_status,
            reviewed_escalations.reviewed_at
        FROM conversation_summaries AS anchor_summary
        INNER JOIN conversation_summaries AS reviewed_summaries
            ON reviewed_summaries.account_id = anchor_summary.account_id
        INNER JOIN accounts
            ON accounts.id = reviewed_summaries.account_id
        INNER JOIN escalations AS reviewed_escalations
            ON reviewed_escalations.id = (
                SELECT MAX(escalation.id)
                FROM escalations AS escalation
                WHERE escalation.summary_id = reviewed_summaries.id
            )
        WHERE anchor_summary.id = %s
          AND reviewed_summaries.flagged_status = 1
          AND reviewed_escalations.status = 'reviewed'
          AND accounts.role = 'student'
          AND accounts.status = 'active'
          AND accounts.program IN ({placeholders})
        ORDER BY reviewed_escalations.reviewed_at DESC,
                 reviewed_summaries.id DESC
        """,
        (anchor_summary_id, *authorized_programs),
    )


def fetch_staff_inbox_summary(summary_id: int) -> dict[str, Any] | None:
    """Return one active or finalized item with safe student case indicators."""
    rows = fetch_rows(
        """
        SELECT
            conversation_summaries.id AS summary_id,
            accounts.id AS student_account_id,
            accounts.full_name AS student_name,
            accounts.student_number,
            accounts.program,
            conversation_summaries.primary_concern,
            conversation_summaries.conversation_type,
            conversation_summaries.emotion_results,
            conversation_summaries.flagged_status,
            conversation_summaries.appointment_recommendation,
            conversation_summaries.recommendations,
            conversation_summaries.suggested_intervention,
            conversation_summaries.language_used,
            conversation_summaries.total_messages,
            conversation_summaries.summary,
            conversation_summaries.created_at,
            escalations.status AS escalation_status,
            escalations.escalation_reason,
            escalations.created_at AS escalation_created_at,
            escalations.reviewed_at,
            EXISTS(
                SELECT 1
                FROM referrals
                WHERE referrals.conversation_summary_id = conversation_summaries.id
            ) AS has_referral,
            EXISTS(
                SELECT 1
                FROM interventions
                WHERE interventions.conversation_summary_id = conversation_summaries.id
            ) AS has_intervention
        FROM conversation_summaries
        INNER JOIN accounts
            ON accounts.id = conversation_summaries.account_id
        LEFT JOIN escalations
            ON escalations.id = (
                SELECT MAX(escalation.id)
                FROM escalations AS escalation
                WHERE escalation.summary_id = conversation_summaries.id
            )
        WHERE conversation_summaries.id = %s
          AND accounts.role = 'student'
          AND accounts.status = 'active'
        LIMIT 1
        """,
        (summary_id,),
    )
    return rows[0] if rows else None


def list_inquiries() -> list[dict[str, Any]]:
    """Return inquiry records for service-owned privacy filtering."""
    initialize_database()

    return fetch_rows(
        """
        SELECT *
        FROM inquiries
        ORDER BY id DESC
        LIMIT 100
        """
    )


def list_escalations() -> list[dict[str, Any]]:
    """Return escalation records for service-owned privacy filtering."""
    initialize_database()

    return fetch_rows(
        """
        SELECT *
        FROM escalations
        ORDER BY id DESC
        LIMIT 100
        """
    )


def list_chatbot_inquiries_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return only the persisted fields needed for chatbot-message analytics."""
    scope_clause, scope_params = _student_program_scope_clause(
        "inquiries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT created_at, emotion_result
        FROM inquiries
        WHERE inquiry_type = 'ai_chat'
          {scope_clause}
          AND (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at < %s)
        ORDER BY created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_conversation_finalizations_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return only finalized-conversation aggregate input fields."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT created_at, total_messages
        FROM conversation_summaries
        WHERE conversation_type <> 'active'
          {scope_clause}
          AND (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at < %s)
        ORDER BY created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_escalations_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return only escalation timestamps needed for aggregate analytics."""
    scope_clause, scope_params = _student_program_scope_clause(
        "escalations.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT created_at
        FROM escalations
        WHERE 1 = 1
          {scope_clause}
          AND (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at < %s)
        ORDER BY created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_flagged_case_statuses_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return persisted status values for flagged cases created in a range."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT escalations.status, conversation_summaries.created_at
        FROM conversation_summaries
        INNER JOIN escalations
            ON escalations.summary_id = conversation_summaries.id
        WHERE conversation_summaries.flagged_status = 1
          {scope_clause}
          AND (%s IS NULL OR conversation_summaries.created_at >= %s)
          AND (%s IS NULL OR conversation_summaries.created_at < %s)
        ORDER BY conversation_summaries.created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_flagged_case_referrals_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return timestamps for referrals attached to flagged cases."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT referrals.created_at
        FROM referrals
        INNER JOIN conversation_summaries
            ON conversation_summaries.id = referrals.conversation_summary_id
        WHERE conversation_summaries.flagged_status = 1
          {scope_clause}
          AND (%s IS NULL OR referrals.created_at >= %s)
          AND (%s IS NULL OR referrals.created_at < %s)
        ORDER BY referrals.created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_flagged_case_interventions_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return timestamps for interventions attached to flagged cases."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT interventions.created_at
        FROM interventions
        INNER JOIN conversation_summaries
            ON conversation_summaries.id = interventions.conversation_summary_id
        WHERE conversation_summaries.flagged_status = 1
          {scope_clause}
          AND (%s IS NULL OR interventions.created_at >= %s)
          AND (%s IS NULL OR interventions.created_at < %s)
        ORDER BY interventions.created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_flagged_case_confidentiality_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return current confidentiality states for flagged-case records."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT case_confidentiality.confidentiality_status,
               case_confidentiality.created_at
        FROM case_confidentiality
        INNER JOIN conversation_summaries
            ON conversation_summaries.id =
               case_confidentiality.conversation_summary_id
        WHERE conversation_summaries.flagged_status = 1
          {scope_clause}
          AND (%s IS NULL OR case_confidentiality.created_at >= %s)
          AND (%s IS NULL OR case_confidentiality.created_at < %s)
        ORDER BY case_confidentiality.created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_flagged_case_escalations_for_analytics(
    start_at: datetime | None,
    end_at: datetime | None,
    programs: object | None = None,
) -> list[dict[str, Any]]:
    """Return escalation timestamps for flagged cases."""
    scope_clause, scope_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    return fetch_rows(
        f"""
        SELECT escalations.created_at
        FROM escalations
        INNER JOIN conversation_summaries
            ON conversation_summaries.id = escalations.summary_id
        WHERE conversation_summaries.flagged_status = 1
          {scope_clause}
          AND (%s IS NULL OR escalations.created_at >= %s)
          AND (%s IS NULL OR escalations.created_at < %s)
        ORDER BY escalations.created_at ASC
        """,
        (*scope_params, start_at, start_at, end_at, end_at),
    )


def list_staff_referrals_for_workload_analytics(
    staff_account_id: int,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[dict[str, Any]]:
    """Return aggregate input for referrals owned by one staff account."""
    return fetch_rows(
        """
        SELECT status, created_at
        FROM referrals
        WHERE staff_account_id = %s
          AND (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at < %s)
        ORDER BY created_at ASC
        """,
        (staff_account_id, start_at, start_at, end_at, end_at),
    )


def list_staff_interventions_for_workload_analytics(
    staff_account_id: int,
    start_at: datetime | None,
    end_at: datetime | None,
) -> list[dict[str, Any]]:
    """Return aggregate input for interventions owned by one staff account."""
    return fetch_rows(
        """
        SELECT progress_status, created_at
        FROM interventions
        WHERE staff_account_id = %s
          AND (%s IS NULL OR created_at >= %s)
          AND (%s IS NULL OR created_at < %s)
        ORDER BY created_at ASC
        """,
        (staff_account_id, start_at, start_at, end_at, end_at),
    )


def list_flagged_conversations() -> list[dict[str, Any]]:
    """Return flagged conversation records without account linkage fields."""
    initialize_database()

    return fetch_rows(
        """
        SELECT
            conversation_summaries.id,
            conversation_summaries.primary_concern,
            conversation_summaries.conversation_type,
            conversation_summaries.emotion_results,
            conversation_summaries.appointment_recommendation,
            conversation_summaries.recommendations,
            conversation_summaries.suggested_intervention,
            conversation_summaries.language_used,
            conversation_summaries.total_messages,
            conversation_summaries.summary,
            conversation_summaries.created_at,
            escalations.status AS escalation_status,
            escalations.escalation_reason,
            escalations.reviewed_at
        FROM conversation_summaries
        INNER JOIN escalations
            ON escalations.summary_id = conversation_summaries.id
        WHERE conversation_summaries.flagged_status = 1
        ORDER BY conversation_summaries.created_at DESC
        """
    )


def fetch_flagged_conversation(summary_id: int) -> dict[str, Any] | None:
    """Return one flagged conversation summary and escalation record."""
    initialize_database()

    rows = fetch_rows(
        """
        SELECT
            conversation_summaries.id,
            conversation_summaries.primary_concern,
            conversation_summaries.conversation_type,
            conversation_summaries.emotion_results,
            conversation_summaries.appointment_recommendation,
            conversation_summaries.recommendations,
            conversation_summaries.suggested_intervention,
            conversation_summaries.language_used,
            conversation_summaries.total_messages,
            conversation_summaries.summary,
            conversation_summaries.created_at,
            escalations.status AS escalation_status,
            escalations.escalation_reason,
            escalations.reviewed_at
        FROM conversation_summaries
        INNER JOIN escalations
            ON escalations.summary_id = conversation_summaries.id
        WHERE conversation_summaries.id = %s
          AND conversation_summaries.flagged_status = 1
        LIMIT 1
        """,
        (summary_id,),
    )
    return rows[0] if rows else None


def save_flagged_conversation_transcript(
    summary_id: int,
    transcript: list[dict[str, str]],
) -> None:
    """Persist the server-owned transcript for one flagged case only."""
    initialize_database()
    serialized = json.dumps(transcript, ensure_ascii=False, separators=(",", ":"))
    timestamp = current_time()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO flagged_conversation_transcripts (
                    conversation_summary_id,
                    transcript_json,
                    created_at,
                    updated_at
                )
                SELECT %s, %s, %s, %s
                FROM conversation_summaries
                WHERE id = %s
                  AND flagged_status = 1
                ON DUPLICATE KEY UPDATE
                    transcript_json = VALUES(transcript_json),
                    updated_at = VALUES(updated_at)
                """,
                (summary_id, serialized, timestamp, timestamp, summary_id),
            )
        connection.commit()


def fetch_flagged_conversation_transcript(summary_id: int) -> dict[str, Any] | None:
    """Return one raw transcript record for service-owned staff projection."""
    initialize_database()
    rows = fetch_rows(
        """
        SELECT transcript_json, created_at, updated_at
        FROM flagged_conversation_transcripts
        WHERE conversation_summary_id = %s
        LIMIT 1
        """,
        (summary_id,),
    )
    return rows[0] if rows else None


def mark_escalation_reviewed(summary_id: int) -> bool:
    """Mark a pending escalation as reviewed without replacing its record."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE escalations
                SET status = 'reviewed',
                    reviewed_at = %s
                WHERE summary_id = %s
                  AND status = 'pending'
                """,
                (current_time(), summary_id),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def create_case_note(payload: dict[str, Any]) -> int:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO case_notes (
                    conversation_summary_id,
                    staff_account_id,
                    note_text,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    payload["conversation_summary_id"],
                    payload["staff_account_id"],
                    payload["note_text"],
                    payload.get("created_at", current_time()),
                    payload.get("updated_at", current_time()),
                ),
            )
            note_id = cursor.lastrowid
        connection.commit()

    return int(note_id)


def list_case_notes(conversation_summary_id: int) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT id, note_text, created_at, updated_at
        FROM case_notes
        WHERE conversation_summary_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_summary_id,),
    )


def fetch_case_note(
    note_id: int,
    conversation_summary_id: int,
) -> dict[str, Any] | None:
    initialize_database()

    rows = fetch_rows(
        """
        SELECT id, note_text, created_at, updated_at
        FROM case_notes
        WHERE id = %s
          AND conversation_summary_id = %s
        LIMIT 1
        """,
        (note_id, conversation_summary_id),
    )
    return rows[0] if rows else None


def update_case_note(
    note_id: int,
    conversation_summary_id: int,
    note_text: str,
) -> bool:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE case_notes
                SET note_text = %s,
                    updated_at = %s
                WHERE id = %s
                  AND conversation_summary_id = %s
                """,
                (
                    note_text,
                    current_time(),
                    note_id,
                    conversation_summary_id,
                ),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def create_referral(payload: dict[str, Any]) -> int:
    """Create a referral and its initial history records atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = payload.get("created_at", current_time())
            cursor.execute(
                """
                INSERT INTO referrals (
                    conversation_summary_id,
                    staff_account_id,
                    destination,
                    referral_reason,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload["conversation_summary_id"],
                    payload["staff_account_id"],
                    payload["destination"],
                    payload["referral_reason"],
                    payload["status"],
                    timestamp,
                    payload.get("updated_at", timestamp),
                ),
            )
            referral_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO referral_status_history (
                    referral_id,
                    staff_account_id,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    referral_id,
                    payload["staff_account_id"],
                    payload["status"],
                    timestamp,
                ),
            )
            initial_note = payload.get("initial_note")
            if initial_note:
                cursor.execute(
                    """
                    INSERT INTO referral_notes (
                        referral_id,
                        staff_account_id,
                        note_text,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        referral_id,
                        payload["staff_account_id"],
                        initial_note,
                        timestamp,
                    ),
                )
        connection.commit()

    return referral_id


def list_referrals(conversation_summary_id: int) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT
            id,
            destination,
            referral_reason,
            status,
            created_at,
            updated_at
        FROM referrals
        WHERE conversation_summary_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_summary_id,),
    )


def fetch_referral(
    referral_id: int,
    conversation_summary_id: int,
) -> dict[str, Any] | None:
    initialize_database()

    rows = fetch_rows(
        """
        SELECT
            id,
            destination,
            referral_reason,
            status,
            created_at,
            updated_at
        FROM referrals
        WHERE id = %s
          AND conversation_summary_id = %s
        LIMIT 1
        """,
        (referral_id, conversation_summary_id),
    )
    return rows[0] if rows else None


def update_referral_status(
    referral_id: int,
    conversation_summary_id: int,
    staff_account_id: int,
    status: str,
) -> bool:
    """Update the current status and append the status history atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = current_time()
            cursor.execute(
                """
                UPDATE referrals
                SET status = %s,
                    updated_at = %s
                WHERE id = %s
                  AND conversation_summary_id = %s
                """,
                (status, timestamp, referral_id, conversation_summary_id),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            cursor.execute(
                """
                INSERT INTO referral_status_history (
                    referral_id,
                    staff_account_id,
                    status,
                    created_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (referral_id, staff_account_id, status, timestamp),
            )
        connection.commit()

    return True


def create_referral_note(payload: dict[str, Any]) -> int:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO referral_notes (
                    referral_id,
                    staff_account_id,
                    note_text,
                    created_at
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    payload["referral_id"],
                    payload["staff_account_id"],
                    payload["note_text"],
                    payload.get("created_at", current_time()),
                ),
            )
            note_id = int(cursor.lastrowid)
        connection.commit()

    return note_id


def list_referral_status_history(
    referral_id: int,
    conversation_summary_id: int,
) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT referral_status_history.status, referral_status_history.created_at
        FROM referral_status_history
        INNER JOIN referrals ON referrals.id = referral_status_history.referral_id
        WHERE referral_status_history.referral_id = %s
          AND referrals.conversation_summary_id = %s
        ORDER BY referral_status_history.created_at ASC,
                 referral_status_history.id ASC
        """,
        (referral_id, conversation_summary_id),
    )


def list_referral_notes(
    referral_id: int,
    conversation_summary_id: int,
) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT referral_notes.id, referral_notes.note_text, referral_notes.created_at
        FROM referral_notes
        INNER JOIN referrals ON referrals.id = referral_notes.referral_id
        WHERE referral_notes.referral_id = %s
          AND referrals.conversation_summary_id = %s
        ORDER BY referral_notes.created_at ASC, referral_notes.id ASC
        """,
        (referral_id, conversation_summary_id),
    )


def create_intervention(payload: dict[str, Any]) -> int:
    """Create an intervention and initial planned-history record atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = payload.get("created_at", current_time())
            cursor.execute(
                """
                INSERT INTO interventions (
                    conversation_summary_id,
                    staff_account_id,
                    intervention_type,
                    objective,
                    progress_status,
                    outcome,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    payload["conversation_summary_id"],
                    payload["staff_account_id"],
                    payload["intervention_type"],
                    payload["objective"],
                    payload["progress_status"],
                    None,
                    timestamp,
                    payload.get("updated_at", timestamp),
                ),
            )
            intervention_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO intervention_history (
                    intervention_id,
                    staff_account_id,
                    progress_status,
                    outcome,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    intervention_id,
                    payload["staff_account_id"],
                    payload["progress_status"],
                    None,
                    timestamp,
                ),
            )
        connection.commit()

    return intervention_id


def list_interventions(conversation_summary_id: int) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT
            id,
            intervention_type,
            objective,
            progress_status,
            outcome,
            created_at,
            updated_at
        FROM interventions
        WHERE conversation_summary_id = %s
        ORDER BY created_at ASC, id ASC
        """,
        (conversation_summary_id,),
    )


def fetch_intervention(
    intervention_id: int,
    conversation_summary_id: int,
) -> dict[str, Any] | None:
    initialize_database()

    rows = fetch_rows(
        """
        SELECT
            id,
            intervention_type,
            objective,
            progress_status,
            outcome,
            created_at,
            updated_at
        FROM interventions
        WHERE id = %s
          AND conversation_summary_id = %s
        LIMIT 1
        """,
        (intervention_id, conversation_summary_id),
    )
    return rows[0] if rows else None


def update_intervention_progress(
    intervention_id: int,
    conversation_summary_id: int,
    staff_account_id: int,
    progress_status: str,
) -> bool:
    """Update current progress and append a progress-history record atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = current_time()
            cursor.execute(
                """
                UPDATE interventions
                SET progress_status = %s,
                    updated_at = %s
                WHERE id = %s
                  AND conversation_summary_id = %s
                  AND outcome IS NULL
                """,
                (
                    progress_status,
                    timestamp,
                    intervention_id,
                    conversation_summary_id,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            cursor.execute(
                """
                INSERT INTO intervention_history (
                    intervention_id,
                    staff_account_id,
                    progress_status,
                    outcome,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    intervention_id,
                    staff_account_id,
                    progress_status,
                    None,
                    timestamp,
                ),
            )
        connection.commit()

    return True


def record_intervention_outcome(
    intervention_id: int,
    conversation_summary_id: int,
    staff_account_id: int,
    progress_status: str,
    outcome: str,
) -> bool:
    """Store one terminal outcome and append it to intervention history atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = current_time()
            cursor.execute(
                """
                UPDATE interventions
                SET outcome = %s,
                    updated_at = %s
                WHERE id = %s
                  AND conversation_summary_id = %s
                  AND outcome IS NULL
                """,
                (
                    outcome,
                    timestamp,
                    intervention_id,
                    conversation_summary_id,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            cursor.execute(
                """
                INSERT INTO intervention_history (
                    intervention_id,
                    staff_account_id,
                    progress_status,
                    outcome,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    intervention_id,
                    staff_account_id,
                    progress_status,
                    outcome,
                    timestamp,
                ),
            )
        connection.commit()

    return True


def list_intervention_history(
    intervention_id: int,
    conversation_summary_id: int,
) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT
            intervention_history.progress_status,
            intervention_history.outcome,
            intervention_history.created_at
        FROM intervention_history
        INNER JOIN interventions
            ON interventions.id = intervention_history.intervention_id
        WHERE intervention_history.intervention_id = %s
          AND interventions.conversation_summary_id = %s
        ORDER BY intervention_history.created_at ASC,
                 intervention_history.id ASC
        """,
        (intervention_id, conversation_summary_id),
    )


def create_case_confidentiality(payload: dict[str, Any]) -> int:
    """Create current confidentiality state and its first history entry atomically."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = payload.get("created_at", current_time())
            cursor.execute(
                """
                INSERT INTO case_confidentiality (
                    conversation_summary_id,
                    staff_account_id,
                    confidentiality_status,
                    confidentiality_reason,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    payload["conversation_summary_id"],
                    payload["staff_account_id"],
                    payload["confidentiality_status"],
                    payload.get("confidentiality_reason"),
                    timestamp,
                    payload.get("updated_at", timestamp),
                ),
            )
            confidentiality_id = int(cursor.lastrowid)
            cursor.execute(
                """
                INSERT INTO case_confidentiality_history (
                    case_confidentiality_id,
                    staff_account_id,
                    confidentiality_status,
                    confidentiality_reason,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    confidentiality_id,
                    payload["staff_account_id"],
                    payload["confidentiality_status"],
                    payload.get("confidentiality_reason"),
                    timestamp,
                ),
            )
        connection.commit()

    return confidentiality_id


def fetch_case_confidentiality(
    conversation_summary_id: int,
) -> dict[str, Any] | None:
    initialize_database()

    rows = fetch_rows(
        """
        SELECT
            id,
            confidentiality_status,
            confidentiality_reason,
            created_at,
            updated_at
        FROM case_confidentiality
        WHERE conversation_summary_id = %s
        LIMIT 1
        """,
        (conversation_summary_id,),
    )
    return rows[0] if rows else None


def update_case_confidentiality(
    conversation_summary_id: int,
    staff_account_id: int,
    confidentiality_status: str,
    confidentiality_reason: str | None,
) -> bool:
    """Update the current state and append a confidentiality history entry."""
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            timestamp = current_time()
            cursor.execute(
                """
                UPDATE case_confidentiality
                SET staff_account_id = %s,
                    confidentiality_status = %s,
                    confidentiality_reason = %s,
                    updated_at = %s
                WHERE conversation_summary_id = %s
                """,
                (
                    staff_account_id,
                    confidentiality_status,
                    confidentiality_reason,
                    timestamp,
                    conversation_summary_id,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            cursor.execute(
                """
                INSERT INTO case_confidentiality_history (
                    case_confidentiality_id,
                    staff_account_id,
                    confidentiality_status,
                    confidentiality_reason,
                    created_at
                )
                SELECT id, %s, %s, %s, %s
                FROM case_confidentiality
                WHERE conversation_summary_id = %s
                """,
                (
                    staff_account_id,
                    confidentiality_status,
                    confidentiality_reason,
                    timestamp,
                    conversation_summary_id,
                ),
            )
        connection.commit()

    return True


def list_case_confidentiality_history(
    conversation_summary_id: int,
) -> list[dict[str, Any]]:
    initialize_database()

    return fetch_rows(
        """
        SELECT
            case_confidentiality_history.confidentiality_status,
            case_confidentiality_history.confidentiality_reason,
            case_confidentiality_history.created_at
        FROM case_confidentiality_history
        INNER JOIN case_confidentiality
            ON case_confidentiality.id =
               case_confidentiality_history.case_confidentiality_id
        WHERE case_confidentiality.conversation_summary_id = %s
        ORDER BY case_confidentiality_history.created_at ASC,
                 case_confidentiality_history.id ASC
        """,
        (conversation_summary_id,),
    )

def fetch_account_by_email(email: str) -> dict[str, Any] | None:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id,
                student_number,
                staff_number,
                gender,
                program,
                assigned_programs,
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                appointment_slots,
                consultation_modes,
                email,
                password_hash,
                full_name,
                role,
                status,
                created_at
                FROM accounts WHERE email = %s LIMIT 1
                """,
                (email,),
            )
            row = cursor.fetchone()
    return row

def fetch_account_by_student_number(student_number: str) -> dict[str, Any] | None:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id,
                student_number,
                staff_number,
                gender,
                program,
                assigned_programs,
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                appointment_slots,
                consultation_modes,
                email,
                full_name,
                role,
                status,
                created_at
                FROM accounts
                WHERE student_number = %s
                LIMIT 1
                """,
                (student_number,),
            )
            row = cursor.fetchone()

    return row

def fetch_account_by_staff_number(staff_number: str) -> dict[str, Any] | None:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id,
                student_number,
                staff_number,
                gender,
                program,
                assigned_programs,
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                appointment_slots,
                consultation_modes,
                email,
                full_name,
                role,
                status,
                created_at
                FROM accounts
                WHERE staff_number = %s
                LIMIT 1
                """,
                (staff_number,),
            )
            row = cursor.fetchone()

    return row

def fetch_account_by_id(
    account_id: int,
    *,
    role: str | None = None,
) -> dict[str, Any] | None:
    initialize_database()

    role_filter = ""
    params: list[Any] = [account_id]

    if role:
        role = role.strip().lower()
        if role not in ALLOWED_ACCOUNT_ROLES:
            raise ValueError("Invalid account role.")
        role_filter = " AND role = %s"
        params.append(role)

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT id,
                student_number,
                staff_number,
                gender,
                program,
                assigned_programs,
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                appointment_slots,
                consultation_modes,
                email,
                full_name,
                role,
                status,
                created_at
                FROM accounts
                WHERE id = %s{role_filter}
                LIMIT 1
                """,
                tuple(params),
            )
            row = cursor.fetchone()

    return row


def fetch_account_password_credentials(
    account_id: int,
    *,
    role: str,
) -> dict[str, Any] | None:
    initialize_database()

    normalized_role = role.strip().lower()
    if normalized_role not in ALLOWED_ACCOUNT_ROLES:
        raise ValueError("Invalid account role.")

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id, password_hash, status
                FROM accounts
                WHERE id = %s AND role = %s
                LIMIT 1
                """,
                (account_id, normalized_role),
            )
            row = cursor.fetchone()

    return row


def update_account_password_hash(
    account_id: int,
    password_hash: str,
    *,
    role: str,
) -> bool:
    initialize_database()

    normalized_role = role.strip().lower()
    if normalized_role not in ALLOWED_ACCOUNT_ROLES:
        raise ValueError("Invalid account role.")
    if not password_hash.strip():
        raise ValueError("Password hash is required.")

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE accounts
                SET password_hash = %s
                WHERE id = %s AND role = %s
                """,
                (password_hash, account_id, normalized_role),
            )
            updated = cursor.rowcount == 1
        connection.commit()

    return updated


def list_accounts(
    *,
    role: str | None = None,
    status: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    initialize_database()

    filters: list[str] = []
    params: list[Any] = []

    if role:
        role = role.strip().lower()
        if role not in ALLOWED_ACCOUNT_ROLES:
            raise ValueError("Invalid account role.")
        filters.append("role = %s")
        params.append(role)

    if status:
        status = status.strip().lower()
        if status not in ALLOWED_ACCOUNT_STATUSES:
            raise ValueError("Invalid account status.")
        filters.append("status = %s")
        params.append(status)

    if query:
        search_value = f"%{query.strip()}%"
        filters.append(
            """
            (
                (
                    role = 'student'
                    AND (
                        full_name LIKE %s
                        OR email LIKE %s
                        OR student_number LIKE %s
                    )
                )
                OR (
                    role = 'staff'
                    AND (
                        full_name LIKE %s
                        OR email LIKE %s
                        OR staff_number LIKE %s
                    )
                )
                OR (
                    role = 'admin'
                    AND (
                        full_name LIKE %s
                        OR email LIKE %s
                    )
                )
            )
            """
        )
        params.extend([
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
            search_value,
        ])

    where_clause = ""
    if filters:
        where_clause = "WHERE " + " AND ".join(filters)

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT id,
                student_number,
                staff_number,
                gender,
                program,
                assigned_programs,
                office,
                support_statement,
                consultation_rooms,
                consultation_schedules,
                email,
                full_name,
                role,
                status,
                created_at
                FROM accounts
                {where_clause}
                ORDER BY id ASC
                """,
                tuple(params),
            )
            rows = cursor.fetchall()
    return rows


def update_account_fields(
    account_id: int,
    updates: dict[str, Any],
    *,
    role: str | None = None,
) -> dict[str, Any] | None:
    initialize_database()

    if not updates:
        raise ValueError("No account fields to update.")

    invalid_fields = set(updates) - ALLOWED_ACCOUNT_UPDATE_FIELDS
    if invalid_fields:
        raise ValueError("Invalid account update field.")

    role_filter = ""
    params = [
        _json_column_value(value) if field in ACCOUNT_JSON_FIELDS else value
        for field, value in updates.items()
    ]
    params.append(account_id)

    if role:
        role = role.strip().lower()
        if role not in ALLOWED_ACCOUNT_ROLES:
            raise ValueError("Invalid account role.")
        role_filter = " AND role = %s"
        params.append(role)

    assignments = ", ".join(f"{field} = %s" for field in updates)

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE accounts
                SET {assignments}
                WHERE id = %s{role_filter}
                """,
                tuple(params),
            )

        connection.commit()

    return fetch_account_by_id(account_id, role=role)


def search_student_accounts(query: str) -> list[dict[str, Any]]:
    initialize_database()

    search = f"%{query.strip()}%"

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    full_name,
                    student_number,
                    program,
                    email
                FROM accounts
                WHERE role = 'student'
                  AND status = 'active'
                  AND (
                        full_name LIKE %s
                     OR student_number LIKE %s
                  )
                ORDER BY full_name ASC
                LIMIT 10
                """,
                (search, search),
            )

            rows = cursor.fetchall()

    return [_json_safe_row(row) for row in rows]


def search_student_accounts_by_programs(
    query: str,
    programs: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Return only authorized public student-search fields for staff workflows."""
    if not programs:
        return []

    initialize_database()
    search = f"%{query.strip()}%"
    placeholders = ", ".join(["%s"] * len(programs))
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT
                    full_name,
                    student_number,
                    program,
                    email
                FROM accounts
                WHERE role = 'student'
                  AND status = 'active'
                  AND program IN ({placeholders})
                  AND (
                        full_name LIKE %s
                     OR student_number LIKE %s
                     OR email LIKE %s
                  )
                ORDER BY full_name ASC, student_number ASC
                LIMIT 10
                """,
                (*programs, search, search, search),
            )
            rows = cursor.fetchall()

    return [_json_safe_row(row) for row in rows]


# --- Helper: Get staff assigned to a program ---

def get_staff_by_program(program: str) -> dict[str, Any] | None:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT id,
                       staff_number,
                       full_name,
                       email,
                       assigned_programs,
                       office,
                       support_statement,
                       consultation_rooms,
                       consultation_schedules,
                       appointment_slots,
                       consultation_modes,
                       status
                FROM accounts
                WHERE role = 'staff'
                  AND status = 'active'
                ORDER BY id ASC
                """
            )
            staff_rows = cursor.fetchall()

    for staff in staff_rows:
        assigned = staff.get("assigned_programs")

        if not assigned:
            continue

        if isinstance(assigned, bytes):
            assigned = assigned.decode("utf-8")

        if isinstance(assigned, str):
            try:
                assigned = json.loads(assigned)
            except json.JSONDecodeError:
                continue

        if (
            isinstance(assigned, list)
            and program.strip().lower()
            in {str(p).strip().lower() for p in assigned}
        ):
            return staff

    return None

def get_student_by_id(
    student_id: int,
) -> dict[str, Any] | None:
    rows = fetch_rows(
        """
        SELECT
            id,
            full_name,
            program
        FROM accounts
        WHERE id = %s
          AND role = 'student'
          AND status = 'active'
        LIMIT 1
        """,
        (student_id,),
    )

    return rows[0] if rows else None


def get_student_by_student_number(student_number: str) -> dict[str, Any] | None:
    rows = fetch_rows(
        """
        SELECT
            id,
            full_name,
            student_number,
            program
        FROM accounts
        WHERE student_number = %s
          AND role = 'student'
          AND status = 'active'
        LIMIT 1
        """,
        (student_number,),
    )
    return rows[0] if rows else None

# --- Helper: List staff appointments by assigned programs ---
def list_staff_appointments(staff_id: int) -> list[dict[str, Any]]:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT assigned_programs
                FROM accounts
                WHERE id = %s
                  AND role = 'staff'
                  AND status = 'active'
                LIMIT 1
                """,
                (staff_id,),
            )
            staff = cursor.fetchone()

    if not staff:
        return []

    assigned_programs = staff.get("assigned_programs")

    if not assigned_programs:
        return []

    if isinstance(assigned_programs, str):
        try:
            assigned_programs = json.loads(assigned_programs)
        except json.JSONDecodeError:
            return []

    if not isinstance(assigned_programs, list):
        return []

    placeholders = ", ".join(["%s"] * len(assigned_programs))

    return fetch_rows(
        f"""
        SELECT
            appointments.*,
            accounts.full_name,
            accounts.email,
            accounts.student_number,
            accounts.program
        FROM appointments
        INNER JOIN accounts
            ON appointments.account_id = accounts.id
        WHERE accounts.program IN ({placeholders})
        ORDER BY appointments.preferred_date DESC,
                 appointments.preferred_time_slot DESC,
                 appointments.created_at DESC
        """,
        tuple(assigned_programs),
    )

def list_student_appointments(
    student_id: int,
) -> list[dict[str, Any]]:
    return fetch_rows(
        """
        SELECT
            *
        FROM appointments
        WHERE account_id = %s
        ORDER BY id DESC
        """,
        (student_id,),
    )

def get_dashboard_stats(programs: object | None = None) -> dict[str, Any]:
    initialize_database()

    appointment_scope, appointment_params = _student_program_scope_clause(
        "appointments.account_id",
        programs,
    )
    escalation_scope, escalation_params = _student_program_scope_clause(
        "escalations.account_id",
        programs,
    )
    summary_scope, summary_params = _student_program_scope_clause(
        "conversation_summaries.account_id",
        programs,
    )
    student_scope, student_params = _student_program_scope_clause(
        "accounts.id",
        programs,
    )

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM appointments
                WHERE preferred_date = CURDATE()
                  {appointment_scope}
                """,
                appointment_params,
            )
            appointments_today = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM appointments
                WHERE status = 'pending'
                  {appointment_scope}
                """,
                appointment_params,
            )
            pending_appointments = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM appointments
                WHERE status = 'completed'
                  AND preferred_date = CURDATE()
                  {appointment_scope}
                """,
                appointment_params,
            )
            completed_today = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM escalations
                WHERE status = 'pending'
                  {escalation_scope}
                """,
                escalation_params,
            )
            active_escalations = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM conversation_summaries
                WHERE conversation_type <> 'active'
                  {summary_scope}
                """,
                summary_params,
            )
            conversation_summaries = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM accounts
                WHERE role = 'student'
                  {student_scope}
                """,
                student_params,
            )
            total_students = cursor.fetchone()[0]

    return {
        "appointments_today": appointments_today,
        "pending_appointments": pending_appointments,
        "completed_today": completed_today,
        "active_escalations": active_escalations,
        "conversation_summaries": conversation_summaries,
        "total_students": total_students,
    }

def create_account(
    *,
    full_name: str,
    email: str,
    
    # password_hash must already be generated using
    # werkzeug.security.generate_password_hash().
    # Plaintext passwords must never be passed here.
    password_hash: str, 
    
    role: str,
    student_number: str | None = None,
    staff_number: str | None = None,
    gender: str | None = None,
    program: str | None = None,
    assigned_programs: Any | None = None,
    office: str | None = None,
    support_statement: str | None = None,
    consultation_rooms: Any | None = None,
    consultation_schedules: Any | None = None,
) -> dict[str, Any]:
    initialize_database()
    
    email = email.strip().lower()
    full_name = full_name.strip()
    role = role.strip().lower()
    gender = gender.strip() if gender else None
    program = program.strip() if program else None
    office = office.strip() if office else None
    support_statement = support_statement.strip() if support_statement else None

    # Automatic account number generation
    if role == "student":
        # Allocate this inside the persistence retry below.  Multiple survey
        # registrations can otherwise read the same next number before either
        # INSERT commits.
        student_number = None
        staff_number = None
    elif role == "staff":
        staff_number = generate_next_staff_number()
        student_number = None
    else:
        student_number = None
        staff_number = None

    if role != "staff":
        assigned_programs = None
        office = None
        support_statement = None
        consultation_rooms = None
        consultation_schedules = None

    if role == "admin":
        program = None

    if role not in ALLOWED_ACCOUNT_ROLES:
        raise ValueError("Invalid account role.")
    
    # No longer require manual entry of student_number or staff_number.
    if role == "student" and not program:
        raise ValueError("Program is required for students.")

    # No longer require manual staff_number.
    if fetch_account_by_email(email):
        raise ValueError("An account with this email already exists.")
    
    if student_number and fetch_account_by_student_number(student_number):
        raise ValueError("Student number already exists.")
    
    if (
        staff_number
        and fetch_account_by_staff_number(staff_number)
    ):
        raise ValueError("Staff number already exists.")

    if gender and gender not in ALLOWED_GENDERS:
        raise ValueError("Invalid gender.")

    attempts = STUDENT_NUMBER_ALLOCATION_MAX_ATTEMPTS if role == "student" else 1
    for attempt in range(attempts):
        if role == "student":
            student_number = generate_next_student_number()

        try:
            with _database_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO accounts (
                            full_name,
                            student_number,
                            staff_number,
                            gender,
                            program,
                            assigned_programs,
                            office,
                            support_statement,
                            consultation_rooms,
                            consultation_schedules,
                            email,
                            password_hash,
                            role,
                            status,
                            created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
                        """,
                        (
                            full_name,
                            student_number,
                            staff_number,
                            gender,
                            program,
                            _json_column_value(assigned_programs),
                            office,
                            support_statement,
                            _json_column_value(consultation_rooms),
                            _json_column_value(consultation_schedules),
                            email,
                            password_hash,
                            role,
                            current_time(),
                        ),
                    )

                    account_id = cursor.lastrowid

                connection.commit()
        except mysql.connector.IntegrityError as exc:
            is_student_number_collision = (
                role == "student"
                and getattr(exc, "errno", None) == 1062
                and "student_number" in str(exc).lower()
            )
            if is_student_number_collision and attempt + 1 < attempts:
                continue
            raise
        else:
            break
    else:
        raise RuntimeError("Unable to allocate a unique student number.")

    return {
        "id": account_id,
        "student_number": student_number,
        "staff_number": staff_number,
    }

def load_settings() -> dict[str, Any]:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT setting_key, setting_value FROM settings")
            rows = cursor.fetchall()

    settings = {
        "officeHours": "Monday to Friday, 8:00 AM - 5:00 PM",
        "officeEmail": "guidance@hau.edu.ph",
        "contactNumber": "(045) 123-4567",
        "officeLocation": "SOC Guidance Office, Holy Angel University",
        "autoFlag": True,
        "showSupport": False,
        "escalationMessage": "Your concern may need further attention from Guidance Office personnel. Please wait for proper assistance or contact the office directly if urgent.",
        "categories": [
            "Guidance Appointment",
            "Counseling Services",
            "Office Schedule",
            "Requirements and Procedures",
            "Emotional Support Concerns",
            "General Inquiry",
            "Unknown Inquiry",
        ],
        "faqs": [
            {
                "title": "Office Hours",
                "question": "What are your office hours?",
                "answer": "The SOC Guidance Office is open from Monday to Friday, 8:00 AM to 5:00 PM.",
            },
            {
                "title": "Book Appointment",
                "question": "How can I book an appointment?",
                "answer": "You may book an appointment by selecting the Book Appointment option and submitting your preferred date and reason for appointment.",
            },
            {
                "title": "Counseling Services",
                "question": "Can I speak with a counselor?",
                "answer": "Yes, you may request counseling assistance through the chatbot or visit the SOC Guidance Office during office hours.",
            },
        ],
    }

    for row in rows:
        key = row["setting_key"]
        value = row["setting_value"]
        if key in {"autoFlag", "showSupport"}:
            settings[key] = str(value).lower() in {"1", "true", "yes", "on"}
        elif key in {"categories", "faqs"}:
            try:
                settings[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
        else:
            settings[key] = value

    return settings


def load_persisted_settings(setting_keys: Iterable[str]) -> dict[str, Any]:
    """Return only explicitly persisted setting values for internal services."""

    keys = tuple(
        dict.fromkeys(
            str(key).strip()
            for key in setting_keys
            if str(key).strip()
        )
    )
    if not keys:
        return {}

    initialize_database()
    placeholders = ", ".join(["%s"] * len(keys))
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                f"""
                SELECT setting_key, setting_value
                FROM settings
                WHERE setting_key IN ({placeholders})
                """,
                keys,
            )
            rows = cursor.fetchall()

    return {
        str(row["setting_key"]): row["setting_value"]
        for row in rows
        if row.get("setting_key") is not None
    }


def save_settings(settings: dict[str, Any]) -> None:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            for key, value in settings.items():
                cursor.execute(
                    """
                    INSERT INTO settings (setting_key, setting_value, updated_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE setting_value = VALUES(setting_value), updated_at = VALUES(updated_at)
                    """,
                    (key, json.dumps(value) if isinstance(value, (dict, list)) else str(value), current_time()),
                )
        connection.commit()


def fetch_rows(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    initialize_database()
    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [_json_safe_row(row) for row in rows]

def get_appointment_by_id(
    appointment_id: int,
) -> dict[str, Any] | None:
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                """
                SELECT *
                FROM appointments
                WHERE id = %s
                LIMIT 1
                """,
                (appointment_id,),
            )

            row = cursor.fetchone()

    return _json_safe_row(row) if row else None

def update_appointment_status(appointment_id: int, status: str,) -> None:
    initialize_database()
    
    if status not in APPOINTMENT_STATUSES:
        raise ValueError("Invalid appointment status.")
    
    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE appointments
                SET
                    status = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    status,
                    current_time(),
                    appointment_id,
                )
            )
        connection.commit()
                
def update_counselor_notes(
    appointment_id: int,
    notes: str,
):
    initialize_database()

    with _database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE appointments
                SET
                    counselor_notes = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (
                    notes,
                    current_time(),
                    appointment_id,
                ),
            )
        connection.commit()
