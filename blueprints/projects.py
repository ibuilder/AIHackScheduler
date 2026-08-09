from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import Project, Resource, ScheduleType, Task

projects_bp = Blueprint("projects", __name__)


def _json_body() -> dict:
    """The request body as a dict, or an empty one.

    ``request.json`` raises on a body that is not JSON, which surfaced as a 500
    rather than a 400. Returning an empty dict lets the field checks below
    report what is actually missing.
    """
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@projects_bp.route("/")
@login_required
def list_projects():
    if current_user.role.name == "ADMIN":
        projects = Project.query.filter_by(company_id=current_user.company_id).all()
    else:
        projects = Project.query.filter_by(
            company_id=current_user.company_id, created_by=current_user.id
        ).all()

    return render_template("projects/list.html", projects=projects)


@projects_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_project():
    if request.method == "POST":
        try:
            # Validate form data
            name = request.form.get("name")
            if not name:
                flash("Project name is required", "error")
                return render_template("projects/create.html")

            start_date_str = request.form.get("start_date")
            end_date_str = request.form.get("end_date")

            if not start_date_str or not end_date_str:
                flash("Start date and end date are required", "error")
                return render_template("projects/create.html")

            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            if end_date <= start_date:
                flash("End date must be after start date", "error")
                return render_template("projects/create.html")

            schedule_type_str = request.form.get("schedule_type", "GANTT").upper()

            # Create project with proper enum handling
            project = Project()
            project.name = name
            project.description = request.form.get("description")
            project.project_number = request.form.get("project_number")
            project.company_id = current_user.company_id
            project.created_by = current_user.id
            project.start_date = start_date
            project.end_date = end_date
            project.budget = (
                float(request.form.get("budget", 0)) if request.form.get("budget") else None
            )
            project.location = request.form.get("location")
            project.schedule_type = (
                ScheduleType[schedule_type_str]
                if schedule_type_str in ["GANTT", "LINEAR", "PULL_PLANNING"]
                else ScheduleType.GANTT
            )

            db.session.add(project)
            db.session.commit()

            flash("Project created successfully!", "success")
            return redirect(url_for("projects.project_detail", project_id=project.id))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating project: {str(e)}", "error")

    return render_template("projects/create.html")


@projects_bp.route("/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)

    # Check access permissions. Admin is a role *within* a company, not a
    # cross-tenant superuser, so the company check applies to every role.
    if current_user.company_id != project.company_id:
        flash("Access denied", "error")
        return redirect(url_for("projects.list_projects"))

    # Get project tasks
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.start_date).all()
    resources = Resource.query.filter_by(project_id=project_id).all()

    # Calculate project statistics
    total_tasks = len(tasks)
    completed_tasks = len([t for t in tasks if t.status.name == "COMPLETED"])
    completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    return render_template(
        "projects/detail.html",
        project=project,
        tasks=tasks,
        resources=resources,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        completion_percentage=completion_percentage,
    )


@projects_bp.route("/<int:project_id>/tasks/create", methods=["POST"])
@login_required
def create_task(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.company_id != project.company_id:
        return jsonify({"error": "Access denied"}), 403

    # Validate before constructing. strptime(None) raises TypeError, which
    # escaped as a 500 -- a POST with no body crashed the server rather than
    # being told what it was missing.
    body = _json_body()
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    dates = {}
    for field in ("start_date", "end_date"):
        raw = body.get(field)
        if not raw:
            return jsonify({"error": f"{field} is required (YYYY-MM-DD)"}), 400
        try:
            dates[field] = datetime.strptime(raw, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return jsonify({"error": f"{field} must be YYYY-MM-DD"}), 400

    if dates["end_date"] < dates["start_date"]:
        return jsonify({"error": "end_date cannot precede start_date"}), 400

    task = Task(
        name=name,
        description=body.get("description"),
        project_id=project_id,
        start_date=dates["start_date"],
        end_date=dates["end_date"],
        duration=body.get("duration", 1),
        priority=body.get("priority", "medium"),
        location=body.get("location"),
        station_start=body.get("station_start"),
        station_end=body.get("station_end"),
        pull_plan_week=body.get("pull_plan_week"),
    )

    db.session.add(task)
    db.session.commit()

    return jsonify(
        {
            "id": task.id,
            "name": task.name,
            "start_date": task.start_date.isoformat(),
            "end_date": task.end_date.isoformat(),
            "status": task.status.name,
        }
    )


@projects_bp.route("/<int:project_id>/resources/create", methods=["POST"])
@login_required
def create_resource(project_id):
    project = Project.query.get_or_404(project_id)

    if current_user.company_id != project.company_id:
        return jsonify({"error": "Access denied"}), 403

    # name and type are NOT NULL, so an empty body raised IntegrityError and
    # left the session needing a rollback for whatever ran next.
    body = _json_body()
    name = (body.get("name") or "").strip()
    kind = (body.get("type") or "").strip()
    if not name or not kind:
        return jsonify({"error": "name and type are required"}), 400

    resource = Resource(
        name=name,
        type=kind,
        project_id=project_id,
        unit=body.get("unit"),
        unit_cost=body.get("unit_cost"),
        total_quantity=body.get("total_quantity"),
        available_quantity=body.get("available_quantity"),
        location=body.get("location"),
    )

    db.session.add(resource)
    db.session.commit()

    return jsonify(
        {
            "id": resource.id,
            "name": resource.name,
            "type": resource.type,
            "unit_cost": resource.unit_cost,
        }
    )
