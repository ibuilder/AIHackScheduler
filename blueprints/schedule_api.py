"""Schedule analysis API: CPM calculation and DCMA schedule quality.

These endpoints are deterministic — same schedule in, same numbers out, no
model call involved. They are the layer the AI features are supposed to reason
*about*, so they need to be right before anything downstream can be trusted.
"""

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from models import Project
from services.schedule_analysis import analyse_project, health_check

schedule_api_bp = Blueprint("schedule_api", __name__)


def _authorised_project(project_id):
    """Fetch a project scoped to the caller's company, or return an error."""
    project = Project.query.get(project_id)
    if project is None:
        return None, (jsonify({"error": "Project not found"}), 404)
    if project.company_id != current_user.company_id:
        # Same response as a missing project, so the endpoint does not confirm
        # the existence of another tenant's project ids.
        return None, (jsonify({"error": "Project not found"}), 404)
    return project, None


@schedule_api_bp.route("/projects/<int:project_id>/cpm")
@login_required
def project_cpm(project_id):
    """Forward/backward pass: dates, total float, free float, driving path."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    result = analyse_project(project_id)
    return jsonify(result), (200 if result.get("success") else 422)


@schedule_api_bp.route("/projects/<int:project_id>/health")
@login_required
def project_health(project_id):
    """DCMA 14-point schedule quality assessment."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    result = health_check(project_id)
    return jsonify(result), (200 if result.get("success") else 422)


@schedule_api_bp.route("/projects/<int:project_id>/critical-path")
@login_required
def project_critical_path(project_id):
    """Just the driving path, for chart overlays."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    result = analyse_project(project_id)
    if not result.get("success"):
        return jsonify(result), 422

    return jsonify(
        {
            "success": True,
            "project_id": project_id,
            "project_duration_days": result["project_duration_days"],
            "calculated_finish": result["calculated_finish"],
            "critical_path": result["critical_path"],
            "activities": [a for a in result["activities"] if a["is_critical"]],
        }
    )
