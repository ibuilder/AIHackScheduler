import logging
from datetime import datetime, timezone

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
from models import AuditLog, Company, Project, User, UserRole

admin_bp = Blueprint("user_management", __name__)


@admin_bp.route("/users")
@login_required
def manage_users():
    """User management dashboard"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    users = User.query.filter_by(company_id=current_user.company_id).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/create", methods=["GET", "POST"])
@login_required
def create_user():
    """Create new user"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        try:
            # Validate input
            username = request.form.get("username")
            email = request.form.get("email")
            first_name = request.form.get("first_name")
            last_name = request.form.get("last_name")
            role = request.form.get("role")
            password = request.form.get("password")

            if not all([username, email, first_name, last_name, role, password]):
                flash("All fields are required", "error")
                return render_template("admin/create_user.html")

            # Check if user already exists
            if User.query.filter_by(username=username).first():
                flash("Username already exists", "error")
                return render_template("admin/create_user.html")

            if User.query.filter_by(email=email).first():
                flash("Email already exists", "error")
                return render_template("admin/create_user.html")

            # Create user
            user = User()
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.role = UserRole[role]
            user.company_id = current_user.company_id
            user.password_hash = generate_password_hash(password)
            user.is_active = True

            db.session.add(user)
            db.session.commit()

            # Log user creation
            audit_logger.log_user_management(
                "user_created", user.id, {"created_username": username, "role": role}
            )

            flash(f"User {username} created successfully!", "success")
            return redirect(url_for("admin.manage_users"))

        except Exception as e:
            db.session.rollback()
            logging.error(f"User creation error: {str(e)}")
            flash("Error creating user. Please try again.", "error")

    return render_template("admin/create_user.html")


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    """Edit user details"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    user = User.query.get_or_404(user_id)

    # Can only edit users in same company
    if user.company_id != current_user.company_id:
        flash("Access denied", "error")
        return redirect(url_for("admin.manage_users"))

    if request.method == "POST":
        try:
            original_data = {"role": user.role.value, "is_active": user.is_active}

            # Update user fields
            user.first_name = request.form.get("first_name")
            user.last_name = request.form.get("last_name")
            user.email = request.form.get("email")
            user.role = UserRole[request.form.get("role")]
            user.is_active = request.form.get("is_active") == "on"

            # Update password if provided
            new_password = request.form.get("password")
            if new_password:
                user.password_hash = generate_password_hash(new_password)

            db.session.commit()

            # Log user modification
            changes = {}
            if original_data["role"] != user.role.value:
                changes["role_changed"] = f"{original_data['role']} -> {user.role.value}"
            if original_data["is_active"] != user.is_active:
                changes["status_changed"] = (
                    f"{'active' if original_data['is_active'] else 'inactive'} -> {'active' if user.is_active else 'inactive'}"
                )

            audit_logger.log_user_management("user_modified", user.id, changes)

            flash("User updated successfully!", "success")
            return redirect(url_for("admin.manage_users"))

        except Exception as e:
            db.session.rollback()
            logging.error(f"User edit error: {str(e)}")
            flash("Error updating user. Please try again.", "error")

    return render_template("admin/edit_user.html", user=user)


@admin_bp.route("/users/<int:user_id>/deactivate", methods=["POST"])
@login_required
def deactivate_user(user_id):
    """Deactivate a user"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)

    if user.company_id != current_user.company_id:
        return jsonify({"error": "Access denied"}), 403

    if user.id == current_user.id:
        return jsonify({"error": "Cannot deactivate yourself"}), 400

    try:
        user.is_active = False
        db.session.commit()

        audit_logger.log_user_management("user_deactivated", user.id)

        return jsonify({"success": True, "message": f"User {user.username} deactivated"})

    except Exception as e:
        db.session.rollback()
        logging.error(f"User deactivation error: {str(e)}")
        return jsonify({"error": "Failed to deactivate user"}), 500


@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
@login_required
def activate_user(user_id):
    """Activate a user"""
    if current_user.role.name not in ["ADMIN"]:
        return jsonify({"error": "Access denied"}), 403

    user = User.query.get_or_404(user_id)

    if user.company_id != current_user.company_id:
        return jsonify({"error": "Access denied"}), 403

    try:
        user.is_active = True
        db.session.commit()

        audit_logger.log_user_management("user_activated", user.id)

        return jsonify({"success": True, "message": f"User {user.username} activated"})

    except Exception as e:
        db.session.rollback()
        logging.error(f"User activation error: {str(e)}")
        return jsonify({"error": "Failed to activate user"}), 500


@admin_bp.route("/company/settings", methods=["GET", "POST"])
@login_required
def company_settings():
    """Manage company settings"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    company = Company.query.get(current_user.company_id)

    if request.method == "POST":
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

        except Exception as e:
            db.session.rollback()
            logging.error(f"Company settings update error: {str(e)}")
            flash("Error updating company settings. Please try again.", "error")

    return render_template("admin/company_settings.html", company=company)


@admin_bp.route("/audit-logs")
@login_required
def audit_logs():
    """View audit logs"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

    page = request.args.get("page", 1, type=int)
    per_page = 50

    logs = (
        AuditLog.query.filter_by(company_id=current_user.company_id)
        .order_by(AuditLog.timestamp.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template("admin/audit_logs.html", logs=logs)


@admin_bp.route("/system-status")
@login_required
def system_status():
    """System status and health monitoring"""
    if current_user.role.name not in ["ADMIN"]:
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for("main.dashboard"))

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
        status["database"] = {
            "status": "healthy",
            "response_time_ms": _database_is_reachable(),
        }
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
