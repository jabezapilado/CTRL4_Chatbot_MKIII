import logging
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    redirect,
    session,
    make_response,
    g,
    current_app,
)

from ..auth import (
    STUDENT_TERMS_ACCEPTED_SESSION_KEY,
    get_logged_in_user,
    role_landing_path,
)
from ..request_validation import (
    ROLE_ADMIN,
    ROLE_STAFF,
    ROLE_STUDENT,
)
from ..services import transient_chat_service

logger = logging.getLogger(__name__)

frontend_bp = Blueprint("frontend", __name__)


def _login_redirect_for_current_session_state():
    reason = (
        "session-replaced"
        if getattr(g, "student_session_replaced", False)
        else "session-required"
    )
    return redirect(f"/login?reason={reason}")


@frontend_bp.get("/")
def home():
    return render_template(
        "login.html",
        student_self_registration_available=_student_self_registration_available(),
    )


@frontend_bp.get("/login")
def login():
    return render_template(
        "login.html",
        student_self_registration_available=_student_self_registration_available(),
    )


def _student_self_registration_available() -> bool:
    return bool(
        current_app.config.get("STUDENT_SELF_REGISTRATION_ENABLED")
        and str(current_app.config.get("STUDENT_SELF_REGISTRATION_CODE") or "")
    )


@frontend_bp.get("/register")
def student_registration():
    if not _student_self_registration_available():
        return jsonify({"error": "Not found"}), 404
    return render_template("student_registration.html")


@frontend_bp.get("/chatbot")
def chatbot():
    user = get_logged_in_user() or {}
    active_chat = []
    terms_required = (
        str(user.get("role", "")).lower() == ROLE_STUDENT
        and session.get(STUDENT_TERMS_ACCEPTED_SESSION_KEY) is not True
    )
    if str(user.get("role", "")).lower() == ROLE_STUDENT and not terms_required:
        active_chat = transient_chat_service.get_visible_history(
            getattr(session, "sid", ""),
            user.get("id"),
        )
    response = make_response(
        render_template(
            "chatbot.html",
            active_chat=active_chat,
            terms_required=terms_required,
        )
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@frontend_bp.get("/appointment")
def appointment():
    return render_template("appointment.html")


@frontend_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@frontend_bp.get("/admin")
def admin_accounts():
    return render_template(
        "admin.html",
    )


@frontend_bp.before_request
def require_login_for_private_routes():
    public_paths = {
        "/",
        "/login",
        "/register",
        "/health",
        "/auth/login",
        "/auth/logout",
        "/auth/student-registration",
        "/auth/student-registration/programs",
    }
    path = request.path

    if path.startswith("/static/") or path in public_paths:
        user = get_logged_in_user()
        if path in {"/", "/login", "/register"} and user:
            return redirect(role_landing_path(user))
        return None

    user = get_logged_in_user()
    logger.debug("Frontend request: path=%s authenticated=%s", path, bool(user))
    if not user:
        if path.startswith("/api/") or path == "/chat":
            logger.warning("Unauthorized API access to %s", path)
            return jsonify(
                {
                    "success": False,
                    "message": "Login required.",
                    "errors": None,
                }
            ), 401
        logger.info("Redirecting unauthenticated user to login from %s", path)
        return _login_redirect_for_current_session_state()

    role = str(user.get("role", ROLE_STUDENT)).lower()
    if path in {"/chatbot", "/appointment"} and role in {
        ROLE_STAFF,
        ROLE_ADMIN,
    }:
        return redirect("/dashboard")
    if path == "/dashboard" and role == ROLE_ADMIN:
        return redirect("/admin")
    if path == "/dashboard" and role == ROLE_STUDENT:
        return redirect("/chatbot")
    if path == "/admin" and role != ROLE_ADMIN:
        return redirect(role_landing_path(user))

    return None
