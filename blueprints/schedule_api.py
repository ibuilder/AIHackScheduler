"""Schedule analysis API: CPM calculation and DCMA schedule quality.

These endpoints are deterministic — same schedule in, same numbers out, no
model call involved. They are the layer the AI features are supposed to reason
*about*, so they need to be right before anything downstream can be trusted.
"""

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required

from audit.audit_logger import audit_logger
from core.risk import Distribution
from extensions import db
from models import Project
from services.optional import IntegrationUnavailable
from services.schedule_analysis import (
    analyse_project,
    health_check,
    progress_report,
    set_baseline,
)
from services.schedule_io import (
    ImportError_,
    capabilities,
    export_project,
    import_into_project,
    read_schedule_file,
    serialise,
)
from services.schedule_risk import DEFAULT_ITERATIONS, simulate_project

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


@schedule_api_bp.route("/projects/<int:project_id>/risk")
@login_required
def project_risk(project_id):
    """Monte Carlo completion forecast: P10/P50/P80/P90 and criticality index."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    try:
        iterations = int(request.args.get("iterations", DEFAULT_ITERATIONS))
    except (TypeError, ValueError):
        return jsonify({"error": "iterations must be a whole number"}), 400

    distribution_name = (request.args.get("distribution") or "pert").lower()
    try:
        distribution = Distribution(distribution_name)
    except ValueError:
        valid = ", ".join(d.value for d in Distribution)
        return jsonify({"error": f"distribution must be one of: {valid}"}), 400

    result = simulate_project(project_id, iterations=iterations, distribution=distribution)
    return jsonify(result), (200 if result.get("success") else 422)


@schedule_api_bp.route("/projects/<int:project_id>/progress")
@login_required
def project_progress(project_id):
    """Baseline Execution Index, finish variance, and worst slippage."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    result = progress_report(project_id)
    return jsonify(result), (200 if result.get("success") else 422)


@schedule_api_bp.route("/projects/<int:project_id>/baseline", methods=["POST"])
@login_required
def project_set_baseline(project_id):
    """Freeze the current plan as the baseline to measure against."""
    _, error = _authorised_project(project_id)
    if error:
        return error

    # A JSON body is required, not merely accepted: it is half of what stands
    # in for CSRF protection on this blueprint.
    if not request.is_json:
        return jsonify({"error": "A JSON request body is required"}), 415

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "A JSON object body is required"}), 400

    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "A baseline name is required"}), 400

    try:
        baseline = set_baseline(
            project_id,
            name=name[:120],
            user_id=current_user.id,
            notes=(payload.get("notes") or "")[:2000],
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422

    return (
        jsonify(
            {
                "success": True,
                "baseline": {
                    "id": baseline.id,
                    "name": baseline.name,
                    "task_count": baseline.task_count,
                    "set_at": baseline.set_at.isoformat() if baseline.set_at else None,
                },
            }
        ),
        201,
    )


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


# ── file import and export ────────────────────────────────────────────────


@schedule_api_bp.route("/formats")
@login_required
def formats():
    """What this deployment can read and write, and honestly why not."""
    return jsonify(capabilities())


@schedule_api_bp.route("/import", methods=["POST"])
@login_required
def import_schedule():
    """Create a project from an uploaded .xer, .xml (MSPDI) or .mpp file."""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Attach a schedule file as 'file'"}), 400

    data = upload.read()
    if not data:
        return jsonify({"error": "The uploaded file is empty"}), 400

    try:
        schedule = read_schedule_file(data, upload.filename)
    except IntegrationUnavailable as exc:
        # Reading .mpp needs MPXJ and a JVM. Say so rather than failing vaguely.
        return jsonify(exc.as_response()), 501
    except ImportError_ as exc:
        return jsonify({"error": str(exc)}), 422

    try:
        project = import_into_project(
            schedule,
            company_id=current_user.company_id,
            user_id=current_user.id,
            project_name=(request.form.get("name") or "").strip() or None,
        )
    except ImportError_ as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 422

    audit_logger.log_action(
        action="schedule_imported",
        resource_type="project",
        resource_id=project.id,
        details=f"{schedule.source_format} import of {upload.filename}",
    )

    return (
        jsonify(
            {
                "success": True,
                "project_id": project.id,
                "project_name": project.name,
                "imported": schedule.summary(),
                # Anything the reader could not map, surfaced rather than dropped.
                "warnings": schedule.warnings,
            }
        ),
        201,
    )


@schedule_api_bp.route("/projects/<int:project_id>/export/<export_format>")
@login_required
def export_schedule(project_id, export_format):
    """Download a project as XER or Microsoft Project XML.

    There is no .mpp option: the binary format cannot be written by any
    available library. Export MSPDI and open it in Project.
    """
    _, error = _authorised_project(project_id)
    if error:
        return error

    try:
        schedule = export_project(project_id)
        content, filename, mimetype = serialise(schedule, export_format)
    except LookupError:
        return jsonify({"error": "Project not found"}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return Response(
        content,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
