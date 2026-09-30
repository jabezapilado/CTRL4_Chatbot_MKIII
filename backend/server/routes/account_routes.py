from flask import Blueprint, jsonify, request
import logging

from ..request_validation import require_any_role, require_role

from ..services.account_service import (
    create_account_service,
    create_student_accounts_from_csv_service,
    deactivate_admin_account_service,
    deactivate_staff_account_service,
    deactivate_student_account_service,
    list_accounts_service,
    update_admin_account_service,
    update_staff_account_service,
    update_student_account_service,
    search_students_for_staff_service,
    reset_student_password_service,
    get_own_staff_operational_profile_service,
    update_own_staff_password_service,
    update_own_staff_operational_profile_service,
    StudentAccountImportValidationError,
)
from ..services.program_service import program_service

logger = logging.getLogger(__name__)

account_bp = Blueprint(
    "accounts",
    __name__,
    url_prefix="/api/accounts",
)


@account_bp.get("/programs")
def list_programs_route():
    _, error = require_role("admin")
    if error:
        return error
    return jsonify(
        {
            "success": True,
            "message": "Programs retrieved successfully.",
            "data": {"items": program_service.list_programs(include_inactive=True)},
        }
    ), 200


@account_bp.get("/programs/active")
def list_active_programs_route():
    _, error = require_any_role("admin", "staff")
    if error:
        return error
    return jsonify(
        {
            "success": True,
            "message": "Active programs retrieved successfully.",
            "data": {"items": program_service.list_programs()},
        }
    ), 200


@account_bp.post("/programs")
def create_program_route():
    _, error = require_role("admin")
    if error:
        return error
    try:
        program = program_service.create_program(request.get_json(silent=True) or {})
    except ValueError as exc:
        return _error_response(str(exc), 400)
    return jsonify(
        {
            "success": True,
            "message": "Program created successfully.",
            "data": program,
        }
    ), 201


@account_bp.patch("/programs/<string:program_code>")
def update_program_route(program_code: str):
    _, error = require_role("admin")
    if error:
        return error
    try:
        program = program_service.update_program(
            program_code,
            request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    return jsonify(
        {
            "success": True,
            "message": "Program updated successfully.",
            "data": program,
        }
    ), 200


@account_bp.get("/staff/profile")
def staff_profile_route():
    user, error = require_role("staff")
    if error:
        return error
    try:
        profile = get_own_staff_operational_profile_service(user)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    return jsonify(
        {
            "success": True,
            "message": "Counselor profile retrieved successfully.",
            "data": profile,
        }
    ), 200


@account_bp.patch("/staff/profile")
def update_staff_profile_route():
    user, error = require_role("staff")
    if error:
        return error
    try:
        profile = update_own_staff_operational_profile_service(
            user,
            request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    return jsonify(
        {
            "success": True,
            "message": "Counselor profile updated successfully.",
            "data": profile,
        }
    ), 200


@account_bp.post("/staff/password")
def update_staff_password_route():
    user, error = require_role("staff")
    if error:
        return error
    try:
        update_own_staff_password_service(
            user,
            request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except PermissionError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    return jsonify(
        {
            "success": True,
            "message": "Password updated successfully.",
            "data": None,
        }
    ), 200


def _error_response(message: str, status: int):
    return jsonify(
        {
            "success": False,
            "message": message,
            "errors": None,
        }
    ), status


@account_bp.get("")
def accounts():
    _, error = require_role("admin")
    if error:
        return error
    try:
        items = list_accounts_service(request.args)
    except ValueError as exc:
        return _error_response(str(exc), 400)

    return jsonify(
        {
            "success": True,
            "message": "Accounts retrieved successfully.",
            "data": {"items": items},
        }
    ), 200


@account_bp.get("/search")
def search_accounts():
    user, error = require_role("staff")
    if error:
        return error

    query = str(request.args.get("q", "")).strip()

    if not query:
        return jsonify(
            {
                "success": True,
                "message": "No matching accounts.",
                "data": {"items": []},
            }
        ), 200

    try:
        items = search_students_for_staff_service(user, query)
    except LookupError as exc:
        return _error_response(str(exc), 404)

    return jsonify(
        {
            "success": True,
            "message": "Accounts retrieved successfully.",
            "data": {"items": items},
        }
    ), 200


@account_bp.post("")
def create_account_route():
    user, error = require_role("admin")
    if error:
        return error

    payload = request.get_json(silent=True) or {}

    try:
        account = create_account_service(payload)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except FileExistsError as exc:
        return _error_response(str(exc), 409)
    except Exception:
        logger.exception("Failed to create account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s created account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Account created successfully.",
            "data": {
                "id": account["id"],
                "status": "created",
                "student_number": account["student_number"],
                "staff_number": account["staff_number"],
            },
        }
    ), 201


@account_bp.post("/import/students")
def import_student_accounts_route():
    user, error = require_role("admin")
    if error:
        return error

    uploaded_file = request.files.get("file")
    if uploaded_file is None:
        return _error_response("Select a CSV file to import.", 400)

    try:
        imported = create_student_accounts_from_csv_service(uploaded_file.read())
    except StudentAccountImportValidationError as exc:
        return _error_response(str(exc), 400)
    except FileExistsError as exc:
        return _error_response(str(exc), 409)
    except Exception:
        logger.exception("Failed to import student accounts.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s imported %s student accounts",
        user["id"],
        len(imported),
    )

    return jsonify(
        {
            "success": True,
            "message": f"Imported {len(imported)} student account(s). Download the one-time credentials file now.",
            "data": {"items": imported},
        }
    ), 201


@account_bp.patch("/admin/<int:account_id>")
def update_admin_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    payload = request.get_json(silent=True) or {}

    try:
        account = update_admin_account_service(account_id, payload)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except FileExistsError as exc:
        return _error_response(str(exc), 409)
    except Exception:
        logger.exception("Failed to update administrator account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s updated administrator account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Administrator account updated successfully.",
            "data": {"account": account},
        }
    ), 200


@account_bp.delete("/admin/<int:account_id>")
def deactivate_admin_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    try:
        account = deactivate_admin_account_service(
            account_id,
            authenticated_admin_id=user["id"],
        )
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except Exception:
        logger.exception("Failed to deactivate administrator account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s deactivated administrator account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Administrator account deactivated successfully.",
            "data": {
                "id": account["id"],
                "status": account["status"],
            },
        }
    ), 200


@account_bp.patch("/staff/<int:account_id>")
def update_staff_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    payload = request.get_json(silent=True) or {}

    try:
        account = update_staff_account_service(account_id, payload)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except FileExistsError as exc:
        return _error_response(str(exc), 409)
    except Exception:
        logger.exception("Failed to update staff account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s updated staff account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Staff account updated successfully.",
            "data": {"account": account},
        }
    ), 200


@account_bp.delete("/staff/<int:account_id>")
def deactivate_staff_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    try:
        account = deactivate_staff_account_service(account_id)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except Exception:
        logger.exception("Failed to deactivate staff account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s deactivated staff account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Staff account deactivated successfully.",
            "data": {
                "id": account["id"],
                "status": account["status"],
            },
        }
    ), 200


@account_bp.patch("/<int:account_id>")
def update_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    payload = request.get_json(silent=True) or {}

    try:
        account = update_student_account_service(account_id, payload)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except FileExistsError as exc:
        return _error_response(str(exc), 409)
    except Exception:
        logger.exception("Failed to update student account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s updated student account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Student account updated successfully.",
            "data": {"account": account},
        }
    ), 200


@account_bp.post("/<int:account_id>/password")
def reset_student_password_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    try:
        reset_student_password_service(
            account_id,
            request.get_json(silent=True) or {},
        )
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except Exception:
        logger.exception("Failed to reset student password.")
        return _error_response("Internal server error.", 500)

    logger.info("Admin %s reset password for student account %s", user["id"], account_id)
    return jsonify(
        {
            "success": True,
            "message": "Student password reset successfully.",
            "data": None,
        }
    ), 200


@account_bp.delete("/<int:account_id>")
def deactivate_account_route(account_id: int):
    user, error = require_role("admin")
    if error:
        return error

    try:
        account = deactivate_student_account_service(account_id)
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except LookupError as exc:
        return _error_response(str(exc), 404)
    except Exception:
        logger.exception("Failed to deactivate student account.")
        return _error_response("Internal server error.", 500)

    logger.info(
        "Admin %s deactivated student account %s",
        user["id"],
        account["id"],
    )

    return jsonify(
        {
            "success": True,
            "message": "Student account deactivated successfully.",
            "data": {
                "id": account["id"],
                "status": account["status"],
            },
        }
    ), 200
