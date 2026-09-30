import csv
import hmac
import json
import re
import secrets
from io import StringIO
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from ..db import (
    ALLOWED_ACCOUNT_ROLES,
    ALLOWED_ACCOUNT_STATUSES,
    ALLOWED_GENDERS,
    create_account,
    fetch_account_by_id,
    fetch_account_password_credentials,
    fetch_account_by_email,
    list_accounts,
    search_student_accounts_by_programs,
    update_account_password_hash,
    update_account_fields,
)
from .program_service import program_service

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_ROLES = ALLOWED_ACCOUNT_ROLES
ADMIN_ACCOUNT_CREATE_FIELDS = frozenset({
    "full_name",
    "email",
    "password",
    "role",
    "gender",
})
ADMIN_ACCOUNT_UPDATE_FIELDS = frozenset({
    "full_name",
    "email",
    "gender",
})
STUDENT_ACCOUNT_UPDATE_FIELDS = frozenset({
    "full_name",
    "email",
    "gender",
    "program",
})
STAFF_ACCOUNT_UPDATE_FIELDS = frozenset({
    "full_name",
    "email",
    "gender",
    "assigned_programs",
})
STAFF_ADMIN_ACCOUNT_CREATE_FIELDS = frozenset({
    "full_name",
    "email",
    "password",
    "role",
    "gender",
    "assigned_programs",
})
STAFF_OPERATIONAL_PROFILE_FIELDS = frozenset({
    "office",
    "support_statement",
    "consultation_rooms",
    "consultation_schedules",
    "appointment_slots",
    "consultation_modes",
})
STAFF_OWN_PASSWORD_FIELDS = frozenset({
    "current_password",
    "new_password",
    "confirm_password",
})
ADMIN_STUDENT_PASSWORD_RESET_FIELDS = frozenset({
    "new_password",
    "confirm_password",
})
STUDENT_SELF_REGISTRATION_FIELDS = frozenset(
    {
        "full_name",
        "email",
        "password",
        "gender",
        "program",
        "registration_code",
    }
)
STUDENT_SELF_REGISTRATION_EMAIL_DOMAIN = "student.hau.edu.ph"
CONSULTATION_SCHEDULE_FIELDS = frozenset({"room", "days", "time"})
MAX_APPOINTMENT_SLOTS = 24
MAX_CONSULTATION_MODES = 12
MAX_CONSULTATION_MODE_LENGTH = 80
STUDENT_ACCOUNT_IMPORT_COLUMNS = (
    "full_name",
    "email",
    "gender",
    "program",
)
MAX_STUDENT_ACCOUNT_IMPORT_ROWS = 500
MAX_STUDENT_ACCOUNT_IMPORT_BYTES = 1_000_000
WEEKDAY_ORDER = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class StudentAccountImportValidationError(ValueError):
    """Raised when a student-account import is unsafe to begin."""


def _generated_temporary_password() -> str:
    """Return a one-time password; callers must never persist or log it."""
    return f"C4!{secrets.token_urlsafe(12)}"


def _import_error_message(errors: list[str]) -> str:
    displayed_errors = errors[:8]
    suffix = "" if len(errors) <= len(displayed_errors) else " Review the CSV and try again."
    return "Import was not completed. " + " ".join(displayed_errors) + suffix


def create_student_accounts_from_csv_service(file_bytes: object) -> list[dict]:
    """Validate then import student accounts from the approved CSV template.

    The CSV intentionally does not accept roles or passwords. It can only create
    students, numbers are allocated by the existing persistence function, and
    temporary passwords are generated server-side for the one-time result file.
    """
    if not isinstance(file_bytes, bytes) or not file_bytes:
        raise StudentAccountImportValidationError("Upload a non-empty CSV file.")
    if len(file_bytes) > MAX_STUDENT_ACCOUNT_IMPORT_BYTES:
        raise StudentAccountImportValidationError("The CSV file is too large.")

    try:
        content = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StudentAccountImportValidationError(
            "The CSV must use UTF-8 encoding."
        ) from exc

    try:
        reader = csv.DictReader(StringIO(content))
    except csv.Error as exc:
        raise StudentAccountImportValidationError("The CSV could not be read.") from exc

    headers = tuple((header or "").strip() for header in (reader.fieldnames or ()))
    if headers != STUDENT_ACCOUNT_IMPORT_COLUMNS:
        required = ", ".join(STUDENT_ACCOUNT_IMPORT_COLUMNS)
        raise StudentAccountImportValidationError(
            f"Use the required CSV columns in this order: {required}."
        )

    rows: list[dict] = []
    errors: list[str] = []
    seen_emails: set[str] = set()
    try:
        for row_number, row in enumerate(reader, start=2):
            if len(rows) >= MAX_STUDENT_ACCOUNT_IMPORT_ROWS:
                errors.append(
                    f"Only {MAX_STUDENT_ACCOUNT_IMPORT_ROWS} accounts can be imported at one time."
                )
                break
            if (row or {}).get(None):
                errors.append(f"Row {row_number}: Too many columns.")
                continue
            raw_values = {
                column: str((row or {}).get(column) or "").strip()
                for column in STUDENT_ACCOUNT_IMPORT_COLUMNS
            }
            if not any(raw_values.values()):
                continue

            try:
                full_name = _validate_full_name(raw_values["full_name"])
                email = _validate_email(raw_values["email"])
                gender = _validate_gender(raw_values["gender"])
                program = _validate_student_program(raw_values["program"])
            except (ValueError, FileExistsError) as exc:
                errors.append(f"Row {row_number}: {exc}")
                continue

            if email in seen_emails:
                errors.append(f"Row {row_number}: Email is duplicated in this CSV.")
                continue
            seen_emails.add(email)
            rows.append(
                {
                    "row_number": row_number,
                    "full_name": full_name,
                    "email": email,
                    "gender": gender,
                    "program": program,
                }
            )
    except csv.Error as exc:
        raise StudentAccountImportValidationError("The CSV could not be read.") from exc

    if not rows:
        errors.append("The CSV does not contain any account rows.")
    if errors:
        raise StudentAccountImportValidationError(_import_error_message(errors))

    imported: list[dict] = []
    for row in rows:
        temporary_password = _generated_temporary_password()
        account = _create_account_with_duplicate_email_translation(
            full_name=row["full_name"],
            email=row["email"],
            password_hash=generate_password_hash(temporary_password),
            role="student",
            student_number=None,
            staff_number=None,
            gender=row["gender"],
            program=row["program"],
        )
        imported.append(
            {
                "row_number": row["row_number"],
                "full_name": row["full_name"],
                "email": row["email"],
                "student_number": account["student_number"],
                "temporary_password": temporary_password,
            }
        )
    return imported


def _validate_full_name(value: object) -> str:
    full_name = str(value or "").strip()
    if not full_name:
        raise ValueError("Full name is required.")
    return full_name


def _validate_email(value: object, *, existing_account_id: int | None = None) -> str:
    email = str(value or "").strip().lower()
    if not email:
        raise ValueError("Email is required.")
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Invalid email address.")

    account_with_email = fetch_account_by_email(email)
    if (
        account_with_email
        and account_with_email["id"] != existing_account_id
    ):
        raise FileExistsError("Email already exists.")

    return email


def _validate_gender(value: object) -> str:
    gender = str(value or "").strip()
    if not gender:
        raise ValueError("Gender is required.")
    if gender not in ALLOWED_GENDERS:
        raise ValueError("Invalid gender.")
    return gender


def _validate_role(value: object) -> str:
    role = str(value).strip().lower()
    if role not in VALID_ROLES:
        raise ValueError("Invalid account role.")
    return role


def _validate_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status not in ALLOWED_ACCOUNT_STATUSES:
        raise ValueError("Invalid account status.")
    return status


def _validate_student_program(value: object) -> str:
    program = str(value or "").strip()
    if not program:
        raise ValueError("Program is required.")
    if program not in program_service.active_program_names():
        raise ValueError("Invalid program.")
    return program


def _decode_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def _validate_program_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Assigned programs must be a list.")

    programs: list[str] = []
    seen_programs: set[str] = set()
    for item in value:
        program = str(item or "").strip()
        if not program:
            raise ValueError("Assigned programs cannot contain blank values.")
        if program not in program_service.active_program_names():
            raise ValueError("Invalid assigned program.")
        if program in seen_programs:
            raise ValueError("Assigned programs cannot contain duplicates.")
        programs.append(program)
        seen_programs.add(program)

    return programs


def _validate_text_field(
    value: object,
    *,
    max_length: int | None = None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Account profile field must be text.")

    text = value.strip()
    if not text:
        return None
    if max_length and len(text) > max_length:
        raise ValueError("Account profile field is too long.")

    return text


def _validate_room_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Consultation rooms must be a list.")

    rooms: list[str] = []
    seen_rooms: set[str] = set()
    for item in value:
        room = str(item or "").strip()
        if not room:
            raise ValueError("Consultation rooms cannot contain blank values.")
        if room in seen_rooms:
            raise ValueError("Consultation rooms cannot contain duplicates.")
        rooms.append(room)
        seen_rooms.add(room)

    return rooms


def _validate_schedule_list(
    value: object,
    *,
    allowed_rooms: list[str],
) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("Consultation schedules must be a list.")

    allowed_room_names = set(allowed_rooms)
    schedules: list[dict] = []

    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Consultation schedules must contain objects.")
        if set(item) != CONSULTATION_SCHEDULE_FIELDS:
            raise ValueError("Invalid consultation schedule fields.")

        room = str(item.get("room") or "").strip()
        days = _normalize_schedule_days(item.get("days"))
        time = _normalize_schedule_time(item.get("time"))

        if not room or not days or not time:
            raise ValueError("Consultation schedules require room, days, and time.")
        if room not in allowed_room_names:
            raise ValueError("Consultation schedules must reference consultation rooms.")

        schedules.append(
            {
                "room": room,
                "days": days,
                "time": time,
            }
        )

    return schedules


def _validate_appointment_slot_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("Appointment start times must contain at least one time.")
    if len(value) > MAX_APPOINTMENT_SLOTS:
        raise ValueError("Too many appointment start times were provided.")

    slots: list[str] = []
    for raw_slot in value:
        if not isinstance(raw_slot, str):
            raise ValueError("Appointment start times must contain valid times.")
        try:
            slot = datetime.strptime(" ".join(raw_slot.split()), "%I:%M %p").strftime(
                "%I:%M %p"
            )
        except ValueError as exc:
            raise ValueError("Appointment start times must contain valid times.") from exc
        slots.append(slot)
    if len(set(slots)) != len(slots):
        raise ValueError("Appointment start times must not contain duplicates.")
    return sorted(slots, key=lambda slot: datetime.strptime(slot, "%I:%M %p"))


def _validate_consultation_mode_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("Consultation modes must contain at least one mode.")
    if len(value) > MAX_CONSULTATION_MODES:
        raise ValueError("Too many consultation modes were provided.")

    modes: list[str] = []
    seen: set[str] = set()
    for raw_mode in value:
        if not isinstance(raw_mode, str):
            raise ValueError("Consultation modes must contain text values.")
        mode = " ".join(raw_mode.split())
        if not mode or len(mode) > MAX_CONSULTATION_MODE_LENGTH:
            raise ValueError("Consultation modes must contain valid text values.")
        normalized = mode.casefold()
        if normalized in seen:
            raise ValueError("Consultation modes must not contain duplicates.")
        seen.add(normalized)
        modes.append(mode)
    return modes


def _normalize_schedule_days(value: object) -> str:
    days = " ".join(str(value or "").split())
    if not days:
        raise ValueError("Consultation schedules require room, days, and time.")
    if " to " in days:
        start, end = (part.strip() for part in days.split(" to ", 1))
    elif "-" in days:
        start, end = (part.strip() for part in days.split("-", 1))
    else:
        start = end = days
    if start not in WEEKDAY_ORDER or end not in WEEKDAY_ORDER:
        raise ValueError("Consultation schedule days are invalid.")
    if WEEKDAY_ORDER.index(start) > WEEKDAY_ORDER.index(end):
        raise ValueError("Consultation schedule days are invalid.")
    return start if start == end else f"{start} to {end}"


def _normalize_schedule_time(value: object) -> str:
    raw_time = " ".join(str(value or "").split())
    if raw_time.count("-") != 1:
        raise ValueError("Consultation schedule time is invalid.")
    start_raw, end_raw = (part.strip() for part in raw_time.split("-"))
    try:
        start = datetime.strptime(start_raw, "%I:%M %p")
        end = datetime.strptime(end_raw, "%I:%M %p")
    except ValueError as exc:
        raise ValueError("Consultation schedule time is invalid.") from exc
    if start >= end:
        raise ValueError("Consultation schedule end time must be after start time.")
    return f"{start.strftime('%I:%M %p')} - {end.strftime('%I:%M %p')}"


def _validate_staff_profile_fields(
    payload: dict,
    *,
    existing_account: dict | None = None,
) -> dict:
    updates = {}

    if "assigned_programs" in payload:
        updates["assigned_programs"] = _validate_program_list(
            payload.get("assigned_programs")
        )

    if "office" in payload:
        updates["office"] = _validate_text_field(
            payload.get("office"),
            max_length=255,
        )

    if "support_statement" in payload:
        updates["support_statement"] = _validate_text_field(
            payload.get("support_statement")
        )

    existing_rooms = _decode_list(
        existing_account.get("consultation_rooms") if existing_account else None
    )

    if "consultation_rooms" in payload:
        updates["consultation_rooms"] = _validate_room_list(
            payload.get("consultation_rooms")
        )

    effective_rooms = updates.get("consultation_rooms", existing_rooms)

    if "consultation_schedules" in payload:
        updates["consultation_schedules"] = _validate_schedule_list(
            payload.get("consultation_schedules"),
            allowed_rooms=effective_rooms,
        )
    elif "consultation_rooms" in payload and existing_account:
        _validate_schedule_list(
            _decode_list(existing_account.get("consultation_schedules")),
            allowed_rooms=effective_rooms,
        )

    if "appointment_slots" in payload:
        updates["appointment_slots"] = _validate_appointment_slot_list(
            payload.get("appointment_slots")
        )

    if "consultation_modes" in payload:
        updates["consultation_modes"] = _validate_consultation_mode_list(
            payload.get("consultation_modes")
        )

    return updates


def _validate_common_account_updates(
    payload: dict,
    existing_account: dict,
) -> dict:
    updates = {}

    if "full_name" in payload:
        updates["full_name"] = _validate_full_name(payload.get("full_name"))

    if "email" in payload:
        updates["email"] = _validate_email(
            payload.get("email"),
            existing_account_id=existing_account["id"],
        )

    if "gender" in payload:
        updates["gender"] = _validate_gender(payload.get("gender"))

    return updates


def _is_duplicate_email_persistence_error(exc: Exception) -> bool:
    message = str(exc).lower()

    if (
        isinstance(exc, ValueError)
        and "email" in message
        and "already exists" in message
    ):
        return True

    errno = getattr(exc, "errno", None)
    if errno == 1062 and "email" in message:
        return True

    return False


def _create_account_with_duplicate_email_translation(**account_fields) -> dict:
    try:
        return create_account(**account_fields)
    except Exception as exc:
        if _is_duplicate_email_persistence_error(exc):
            raise FileExistsError("Email already exists.") from exc
        raise


def _update_account_fields_with_duplicate_email_translation(
    account_id: int,
    updates: dict,
    *,
    role: str,
) -> dict | None:
    try:
        return update_account_fields(account_id, updates, role=role)
    except Exception as exc:
        if _is_duplicate_email_persistence_error(exc):
            raise FileExistsError("Email already exists.") from exc
        raise


def create_account_service(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")

    full_name = str(payload.get("full_name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    role = str(payload["role"] if "role" in payload else "student").strip().lower()

    gender = str(payload.get("gender", "")).strip() or None
    program = str(payload.get("program", "")).strip() or None

    if not full_name or not email or not password:
        raise ValueError("Missing required fields.")

    if not password.strip():
        raise ValueError("Password cannot be blank.")

    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    full_name = _validate_full_name(full_name)
    email = _validate_email(email)
    role = _validate_role(role)

    if role == "student":
        program = _validate_student_program(program)

    gender = _validate_gender(gender)

    if role == "admin":
        unsupported_fields = set(payload) - ADMIN_ACCOUNT_CREATE_FIELDS
        if unsupported_fields:
            raise ValueError("Unsupported administrator account field.")

    staff_profile = {}
    if role == "staff":
        unsupported_fields = set(payload) - STAFF_ADMIN_ACCOUNT_CREATE_FIELDS
        if unsupported_fields:
            raise ValueError("Operational counselor fields are managed by Guidance staff.")
        if "assigned_programs" in payload:
            staff_profile["assigned_programs"] = _validate_program_list(
                payload.get("assigned_programs")
            )

    return _create_account_with_duplicate_email_translation(
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        student_number=None,
        staff_number=None,
        gender=gender,
        program=program,
        **staff_profile,
    )


def create_student_self_registration_service(
    payload: object,
    *,
    registration_code: object,
) -> dict:
    """Create a student account through the temporary public survey flow."""
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")
    if set(payload) - STUDENT_SELF_REGISTRATION_FIELDS:
        raise ValueError("Unsupported registration field.")

    supplied_code = str(payload.get("registration_code") or "")
    expected_code = str(registration_code or "")
    if not expected_code or not hmac.compare_digest(supplied_code, expected_code):
        raise PermissionError("The survey registration code is invalid.")

    email = str(payload.get("email") or "").strip().lower()
    if not email.endswith(f"@{STUDENT_SELF_REGISTRATION_EMAIL_DOMAIN}"):
        raise ValueError("Use your school student email address to register.")

    return create_account_service(
        {
            "full_name": payload.get("full_name"),
            "email": email,
            "password": payload.get("password"),
            "gender": payload.get("gender"),
            "program": payload.get("program"),
            "role": "student",
        }
    )


def list_accounts_service(filters: dict) -> list[dict]:
    role = str(filters.get("role", "")).strip().lower() or None
    status = str(filters.get("status", "")).strip().lower() or None
    query = str(filters.get("q", "")).strip() or None

    if role:
        role = _validate_role(role)

    if status:
        status = _validate_status(status)

    return list_accounts(role=role, status=status, query=query)


def search_students_for_staff_service(staff_account: dict, query: object) -> list[dict]:
    """Search public student identity fields within the staff member's programs."""
    text = str(query or "").strip()
    if not text:
        return []

    profile = fetch_account_by_id(int(staff_account["id"]), role="staff")
    if not profile:
        raise LookupError("Staff account not found.")
    programs = _decode_list(profile.get("assigned_programs"))
    normalized_programs = tuple(
        dict.fromkeys(
            str(program).strip()
            for program in programs
            if str(program).strip()
        )
    )
    if not normalized_programs:
        return []
    return search_student_accounts_by_programs(text, normalized_programs)


def update_student_account_service(account_id: int, payload: dict) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")

    unsupported_fields = set(payload) - STUDENT_ACCOUNT_UPDATE_FIELDS
    if unsupported_fields:
        raise ValueError("Unsupported account update field.")

    existing_account = fetch_account_by_id(account_id, role="student")
    if not existing_account:
        raise LookupError("Student account not found.")

    updates = _validate_common_account_updates(payload, existing_account)

    if "program" in payload:
        updates["program"] = _validate_student_program(payload.get("program"))

    if not updates:
        raise ValueError("No supported account fields were provided.")

    updated_account = _update_account_fields_with_duplicate_email_translation(
        account_id,
        updates,
        role="student",
    )
    if not updated_account:
        raise LookupError("Student account not found.")

    return updated_account


def update_staff_account_service(account_id: int, payload: dict) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")

    unsupported_fields = set(payload) - STAFF_ACCOUNT_UPDATE_FIELDS
    if unsupported_fields:
        raise ValueError("Unsupported account update field.")

    existing_account = fetch_account_by_id(account_id, role="staff")
    if not existing_account:
        raise LookupError("Staff account not found.")

    updates = _validate_common_account_updates(payload, existing_account)
    if "assigned_programs" in payload:
        updates["assigned_programs"] = _validate_program_list(
            payload.get("assigned_programs")
        )

    if not updates:
        raise ValueError("No supported account fields were provided.")

    updated_account = _update_account_fields_with_duplicate_email_translation(
        account_id,
        updates,
        role="staff",
    )
    if not updated_account:
        raise LookupError("Staff account not found.")

    return updated_account


def get_own_staff_operational_profile_service(staff_account: dict) -> dict:
    profile = fetch_account_by_id(int(staff_account["id"]), role="staff")
    if not profile:
        raise LookupError("Staff account not found.")
    return {
        "office": profile.get("office") or "",
        "support_statement": profile.get("support_statement") or "",
        "consultation_rooms": _decode_list(profile.get("consultation_rooms")),
        "consultation_schedules": _decode_list(profile.get("consultation_schedules")),
        "appointment_slots": _decode_list(profile.get("appointment_slots")),
        "consultation_modes": _decode_list(profile.get("consultation_modes")),
    }


def update_own_staff_operational_profile_service(
    staff_account: dict,
    payload: dict,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")
    unsupported_fields = set(payload) - STAFF_OPERATIONAL_PROFILE_FIELDS
    if unsupported_fields:
        raise ValueError("Unsupported counselor operational profile field.")

    existing = fetch_account_by_id(int(staff_account["id"]), role="staff")
    if not existing:
        raise LookupError("Staff account not found.")
    updates = _validate_staff_profile_fields(payload, existing_account=existing)
    if not updates:
        raise ValueError("No supported operational profile fields were provided.")
    updated = _update_account_fields_with_duplicate_email_translation(
        int(staff_account["id"]),
        updates,
        role="staff",
    )
    if not updated:
        raise LookupError("Staff account not found.")
    return {
        "office": updated.get("office") or "",
        "support_statement": updated.get("support_statement") or "",
        "consultation_rooms": _decode_list(updated.get("consultation_rooms")),
        "consultation_schedules": _decode_list(updated.get("consultation_schedules")),
        "appointment_slots": _decode_list(updated.get("appointment_slots")),
        "consultation_modes": _decode_list(updated.get("consultation_modes")),
    }


def update_own_staff_password_service(staff_account: dict, payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")
    unsupported_fields = set(payload) - STAFF_OWN_PASSWORD_FIELDS
    if unsupported_fields:
        raise ValueError("Unsupported password update field.")

    current_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    confirm_password = str(payload.get("confirm_password", ""))
    if not current_password or not new_password or not confirm_password:
        raise ValueError("Current password, new password, and confirmation are required.")
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters long.")
    if new_password != confirm_password:
        raise ValueError("New passwords do not match.")

    account_id = int(staff_account["id"])
    credentials = fetch_account_password_credentials(account_id, role="staff")
    if not credentials or credentials.get("status") != "active":
        raise LookupError("Staff account not found.")
    if not check_password_hash(str(credentials.get("password_hash", "")), current_password):
        raise PermissionError("Current password is incorrect.")

    updated = update_account_password_hash(
        account_id,
        generate_password_hash(new_password),
        role="staff",
    )
    if not updated:
        raise LookupError("Staff account not found.")


def reset_student_password_service(account_id: int, payload: dict) -> None:
    """Set a new student password through the administrator-only recovery flow."""
    if account_id <= 0:
        raise ValueError("Invalid account id.")
    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")
    if set(payload) - ADMIN_STUDENT_PASSWORD_RESET_FIELDS:
        raise ValueError("Unsupported password reset field.")

    new_password = str(payload.get("new_password", ""))
    confirm_password = str(payload.get("confirm_password", ""))
    if not new_password or not confirm_password:
        raise ValueError("New password and confirmation are required.")
    if len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters long.")
    if new_password != confirm_password:
        raise ValueError("New passwords do not match.")

    existing_account = fetch_account_by_id(account_id, role="student")
    if not existing_account:
        raise LookupError("Student account not found.")

    updated = update_account_password_hash(
        account_id,
        generate_password_hash(new_password),
        role="student",
    )
    if not updated:
        raise LookupError("Student account not found.")


def update_admin_account_service(account_id: int, payload: dict) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    if not isinstance(payload, dict):
        raise ValueError("Invalid request payload.")

    unsupported_fields = set(payload) - ADMIN_ACCOUNT_UPDATE_FIELDS
    if unsupported_fields:
        raise ValueError("Unsupported account update field.")

    existing_account = fetch_account_by_id(account_id, role="admin")
    if not existing_account:
        raise LookupError("Administrator account not found.")

    updates = _validate_common_account_updates(payload, existing_account)

    if not updates:
        raise ValueError("No supported account fields were provided.")

    updated_account = _update_account_fields_with_duplicate_email_translation(
        account_id,
        updates,
        role="admin",
    )
    if not updated_account:
        raise LookupError("Administrator account not found.")

    return updated_account


def deactivate_admin_account_service(
    account_id: int,
    *,
    authenticated_admin_id: int,
) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    if authenticated_admin_id <= 0:
        raise ValueError("Invalid authenticated administrator id.")

    if account_id == authenticated_admin_id:
        raise ValueError("Administrators cannot deactivate their own account.")

    existing_account = fetch_account_by_id(account_id, role="admin")
    if not existing_account:
        raise LookupError("Administrator account not found.")

    if existing_account.get("status") == "disabled":
        return existing_account

    updated_account = update_account_fields(
        account_id,
        {"status": "disabled"},
        role="admin",
    )
    if not updated_account:
        raise LookupError("Administrator account not found.")

    return updated_account


def deactivate_staff_account_service(account_id: int) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    existing_account = fetch_account_by_id(account_id, role="staff")
    if not existing_account:
        raise LookupError("Staff account not found.")

    if existing_account.get("status") == "disabled":
        return existing_account

    updated_account = update_account_fields(
        account_id,
        {"status": "disabled"},
        role="staff",
    )
    if not updated_account:
        raise LookupError("Staff account not found.")

    return updated_account


def deactivate_student_account_service(account_id: int) -> dict:
    if account_id <= 0:
        raise ValueError("Invalid account id.")

    existing_account = fetch_account_by_id(account_id, role="student")
    if not existing_account:
        raise LookupError("Student account not found.")

    if existing_account.get("status") == "disabled":
        return existing_account

    updated_account = update_account_fields(
        account_id,
        {"status": "disabled"},
        role="student",
    )
    if not updated_account:
        raise LookupError("Student account not found.")

    return updated_account


def login_service(payload: dict) -> dict:
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or not password:
        raise ValueError("Email and password are required.")
    if not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Invalid email address.")

    account = fetch_account_by_email(email)
    if not account:
        raise PermissionError("Invalid credentials.")

    if account.get("status") != "active":
        raise PermissionError("Invalid credentials.")

    role = str(account.get("role", "")).strip().lower()
    if role not in VALID_ROLES:
        raise PermissionError("Invalid account configuration.")

    stored_password = str(account.get("password_hash", ""))
    # All accounts are stored using Werkzeug password hashes.
    # Legacy plaintext password support has been removed.
    password_ok = check_password_hash(stored_password, password)

    if not password_ok:
        raise PermissionError("Invalid credentials.")

    user = {
        "id": account["id"],
        "student_number": account.get("student_number"),
        "email": account["email"],
        "full_name": account["full_name"],
        "role": role,
    }

    return user
