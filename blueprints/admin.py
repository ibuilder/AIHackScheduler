"""Administration: users, company settings, integrations, audit and status.

This was two blueprints. ``blueprints/admin.py`` served ``/admin`` and
``admin/user_management.py`` served ``/management``, and both implemented
``manage_users``, ``create_user`` and ``company_settings`` against the same
templates. Views in one redirected to endpoints in the other, so a user editing
their company details could be bounced between two different user lists.

The duplication was not merely untidy. The two ``create_user`` implementations
disagreed about how to read the role field: one did ``UserRole(role)``, keyed
on the enum *value*, the other ``UserRole[role]``, keyed on its *name*. The form
sends ``ADMIN``, which is a name, so ``POST /admin/users/create`` raised
``ValueError: 'ADMIN' is not a valid UserRole`` on every submission while the
``/management`` copy worked. Nothing caught it because no test had ever posted
to either.

One blueprint now, at ``/admin``. ``/management/*`` still resolves — it
redirects, so existing links and bookmarks survive.
"""

import logging
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from audit.audit_logger import audit_logger
from extensions import db
from models import AuditLog, AzureIntegration, Company, Project, User, UserRole

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Refuse anyone who is not an administrator of their own company.

    ``functools.wraps`` rather than assigning ``__name__`` by hand: Flask keys
    endpoints on the function name, so the hand-rolled version worked, but it
    dropped the docstring and module and would silently collide if two wrapped
    views ever shared a name.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            flash("Access denied. Administrator privileges required.", "error")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)

    return decorated_function


# ── overview ─────────────────────────────────────────────────────────────


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(company_id=current_user.company_id).count()
    active_users = User.query.filter_by(company_id=current_user.company_id, is_active=True).count()

    total_projects = Project.query.filter_by(company_id=current_user.company_id).count()
    active_projects = Project.query.filter_by(
        company_id=current_user.company_id, status="active"
    ).count()

    recent_projects = (
        Project.query.filter_by(company_id=current_user.company_id)
        .order_by(Project.created_at.desc())
        .limit(5)
        .all()
    )
    recent_users = (
        User.query.filter_by(company_id=current_user.company_id)
        .order_by(User.created_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        active_users=active_users,
        total_projects=total_projects,
        active_projects=active_projects,
        recent_projects=recent_projects,
        recent_users=recent_users,
    )


# ── users ────────────────────────────────────────────────────────────────


@admin_bp.route("/users")
@login_required
@admin_required
def manage_users():
    users = User.query.filter_by(company_id=current_user.company_id).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/create", methods=["GET", "POST"])
@login_required
@admin_required
def create_user():
    if request.method == "POST":
        try:
            username = request.form.get("username")
            email = request.form.get("email")
            first_name = request.form.get("first_name")
            last_name = request.form.get("last_name")
            role = request.form.get("role")
            password = request.form.get("password")

            if not all([username, email, first_name, last_name, role, password]):
                flash("All fields are required", "error")
                return render_template("admin/create_user.html")

            if User.query.filter_by(username=username).first():
                flash("Username already exists", "error")
                return render_template("admin/create_user.html")

            if User.query.filter_by(email=email).first():
                flash("Email already exists", "error")
                return render_template("admin/create_user.html")

            if role not in UserRole.__members__:
                flash("Unknown role", "error")
                return render_template("admin/create_user.html")

            user = User()
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            # Keyed on the enum NAME, because templates/admin/create_user.html
            # sends "ADMIN". UserRole(role) keys on the value ("admin") and
            # raises ValueError for every option the form offers.
            user.role = UserRole[role]
            user.company_id = current_user.company_id
            user.password_hash = generate_password_hash(password)
            user.is_active = True

            db.session.add(user)
            db.session.commit()

            audit_logger.log_user_management(
                "user_created", user.id, {"created_username": username, "role": role}
            )

            flash(f"User {username} created successfully!", "success")
            return redirect(url_for("admin.manage_users"))

        except Exception as e:
            db.session.rollback()
            logging.error("User creation error: %s", e, exc_info=True)
            flash("Error creating user. Please try again.", "error")

    return render_template("admin/create_user.html")


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found", "error")
        return redirect(url_for("admin.manage_users"))

    # Tenant isolation: an administrator administers their own company.
    if user.company_id != current_user.company_id:
        flash("Access denied", "error")
        return redirect(url_for("admin.manage_users"))

    if request.method == "POST":
        try:
            original = {"role": user.role.value, "is_active": user.is_active}

            role = request.form.get("role")
            if role not in UserRole.__members__:
                flash("Unknown role", "error")
                return render_template("admin/edit_user.html", user=user)

            user.first_name = request.form.get("first_name")
            user.last_name = request.form.get("last_name")
            user.email = request.form.get("email")
            user.role = UserRole[role]
            user.is_active = request.form.get("is_active") == "on"

            new_password = request.form.get("password")
            if new_password:
                user.password_hash = generate_password_hash(new_password)

            db.session.commit()

            changes = {}
            if original["role"] != user.role.value:
                changes["role_changed"] = f"{original['role']} -> {user.role.value}"
            if original["is_active"] != user.is_active:
                changes["status_changed"] = (
                    f"{'active' if original['is_active'] else 'inactive'} -> "
                    f"{'active' if user.is_active else 'inactive'}"
                )
            audit_logger.log_user_management("user_modified", user.id, changes)

            flash("User updated successfully!", "success")
            return redirect(url_for("admin.manage_users"))

        except Exception as e:
            db.session.rollback()
            logging.error("User edit error: %s", e, exc_info=True)
            flash("Error updating user. Please try again.", "error")

    return render_template("admin/edit_user.html", user=user)


def _set_active(user_id: int, active: bool, action: str, message: str):
    """Shared body for activate and deactivate."""
    user = db.session.get(User, user_id)
    if user is None or user.company_id != current_user.company_id:
        flash("Access denied", "error")
        return redirect(url_for("admin.manage_users"))

    if not active and user.id == current_user.id:
        # Locking yourself out of the only admin account is unrecoverable
        # through the interface.
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("admin.edit_user", user_id=user_id))

    try:
        user.is_active = active
        db.session.commit()
        audit_logger.log_user_management(action, user.id, {"username": user.username})
        flash(message, "success")
    except Exception as e:
        db.session.rollback()
        logging.error("User %s error: %s", action, e, exc_info=True)
        flash("Error updating the account. Please try again.", "error")

    return redirect(url_for("admin.manage_users"))


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@login_required
@admin_required
def deactivate_user(user_id):
    return _set_active(user_id, False, "user_deactivated", "User deactivated.")


@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
@login_required
@admin_required
def activate_user(user_id):
    return _set_active(user_id, True, "user_activated", "User reactivated.")


@admin_bp.route("/api/users/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_user_status(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "Not found"}), 404
    if user.company_id != current_user.company_id:
        return jsonify({"error": "Access denied"}), 403
    if user.id == current_user.id and user.is_active:
        return jsonify({"error": "You cannot deactivate your own account"}), 400

    user.is_active = not user.is_active
    db.session.commit()
    audit_logger.log_user_management(
        "user_activated" if user.is_active else "user_deactivated",
        user.id,
        {"username": user.username},
    )
    return jsonify({"success": True, "user_id": user_id, "is_active": user.is_active})


# ── company ──────────────────────────────────────────────────────────────


@admin_bp.route("/company/settings", methods=["GET", "POST"])
@login_required
@admin_required
def company_settings():
    company = db.session.get(Company, current_user.company_id)

    if request.method == "POST" and company is not None:
        try:
            company.name = request.form.get("name")
            company.address = request.form.get("address")
            company.phone = request.form.get("phone")
            company.email = request.form.get("email")
            company.azure_tenant_id = request.form.get("azure_tenant_id")
            company.fabric_workspace_id = request.form.get("fabric_workspace_id")

            db.session.commit()
            audit_logger.log_action(
                "company_settings_updated", resource_type="company", resource_id=company.id
            )
            flash("Company settings updated successfully!", "success")
            return redirect(url_for("admin.company_settings"))

        except Exception as e:
            db.session.rollback()
            logging.error("Company settings update error: %s", e, exc_info=True)
            flash("Error updating company settings. Please try again.", "error")

    return render_template("admin/company_settings.html", company=company)


@admin_bp.route("/integrations")
@login_required
@admin_required
def manage_integrations():
    integrations = (
        AzureIntegration.query.join(Project)
        .filter(Project.company_id == current_user.company_id)
        .all()
    )
    return render_template("admin/integrations.html", integrations=integrations)


# ── audit and status ─────────────────────────────────────────────────────


@admin_bp.route("/audit-logs")
@login_required
@admin_required
def audit_logs():
    page = request.args.get("page", 1, type=int)
    logs = (
        AuditLog.query.filter_by(company_id=current_user.company_id)
        .order_by(AuditLog.timestamp.desc())
        .paginate(page=page, per_page=50, error_out=False)
    )
    return render_template("admin/audit_logs.html", logs=logs)


@admin_bp.route("/system-status")
@login_required
@admin_required
def system_status():
    return render_template("admin/system_status.html", status=collect_system_status())


def collect_system_status() -> dict:
    """Measure what the platform can actually observe about itself.

    This used to return a literal dict: database "healthy", cache "healthy",
    average response time "245ms", 127 requests per minute, error rate "0.2%".
    None of it was measured. An administrator opening the page to decide
    whether the system was in trouble was reading numbers that never changed,
    which is worse than showing nothing.

    Everything below is either measured now or reported as unknown. Request
    rate and error rate are deliberately absent rather than invented: nothing
    in the application records them, and the place to read them is the
    ``/health/metrics`` endpoint that Prometheus scrapes.
    """
    import os
    import time

    import psutil

    from monitoring.health_checks import _database_is_reachable

    status = {"checked_at": datetime.now(timezone.utc).isoformat()}

    try:
        status["database"] = {"status": "healthy", "response_time_ms": _database_is_reachable()}
    except Exception as exc:
        logging.error("System status: database unreachable: %s", exc, exc_info=True)
        status["database"] = {"status": "unhealthy"}

    # The cache is configured at startup; report the backend actually in use
    # rather than asserting health of something that may be a no-op.
    try:
        cache_type = current_app.config.get("CACHE_TYPE", "unknown")
        status["cache"] = {
            "status": "healthy" if cache_type else "not_configured",
            "backend": str(cache_type),
        }
    except Exception as exc:
        logging.error("System status: cache check failed: %s", exc, exc_info=True)
        status["cache"] = {"status": "unknown"}

    # Background jobs need a broker. Without one, Celery is not running, and
    # saying so is more useful than a green tick.
    broker = os.environ.get("CELERY_BROKER_URL") or os.environ.get("REDIS_URL")
    status["background_jobs"] = {
        "status": "configured" if broker else "not_configured",
        "broker": "redis" if broker else None,
    }

    # An integration is configured when its credentials are present. This is
    # the same test services/optional.py applies before enabling a feature.
    status["integrations"] = {
        "azure_ai": "configured"
        if os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_KEY")
        else "not_configured",
        "fabric": "configured" if os.environ.get("AZURE_FABRIC_ENDPOINT") else "not_configured",
        "power_bi": "configured"
        if all(
            os.environ.get(name)
            for name in ("POWERBI_CLIENT_ID", "POWERBI_CLIENT_SECRET", "POWERBI_TENANT_ID")
        )
        else "not_configured",
        "stripe": "configured" if os.environ.get("STRIPE_SECRET_KEY") else "not_configured",
    }

    try:
        process = psutil.Process()
        status["process"] = {
            "pid": process.pid,
            "uptime_seconds": round(time.time() - process.create_time()),
            "memory_mb": round(process.memory_info().rss / (1024 * 1024), 1),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "system_memory_percent": psutil.virtual_memory().percent,
        }
    except Exception as exc:
        logging.error("System status: process metrics failed: %s", exc, exc_info=True)
        status["process"] = {}

    status["records"] = {
        "users": User.query.filter_by(company_id=current_user.company_id).count(),
        "projects": Project.query.filter_by(company_id=current_user.company_id).count(),
    }

    return status
