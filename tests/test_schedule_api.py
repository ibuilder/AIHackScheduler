"""End-to-end tests for the schedule analysis API and tenant isolation."""

from werkzeug.security import generate_password_hash


def test_app_boots_with_no_optional_integrations(flask_app):
    """Azure, Stripe and Power BI are optional; their absence must not stop
    the application from starting."""
    assert flask_app is not None
    assert len(list(flask_app.url_map.iter_rules())) > 50


def test_cpm_endpoint_returns_dated_activities(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/cpm")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["project_duration_days"] > 0
    assert len(body["activities"]) == 25

    first = body["activities"][0]
    assert set(first) >= {
        "id",
        "name",
        "early_start",
        "early_finish",
        "late_start",
        "late_finish",
        "total_float",
        "free_float",
        "is_critical",
    }


def test_critical_path_is_a_connected_chain(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/cpm").get_json()

    assert len(body["critical_path"]) > 1
    critical = [a for a in body["activities"] if a["is_critical"]]
    assert all(a["total_float"] == 0 for a in critical)


def test_float_distinguishes_critical_from_slack_activities(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/cpm").get_json()

    floats = {a["name"]: a["total_float"] for a in body["activities"]}
    # The dangling landscaping activity has no logic, so it carries huge float.
    assert floats["Landscaping (scope TBC)"] > 100
    assert floats["Mobilisation & site setup"] == 0


def test_health_endpoint_reports_all_fourteen_checks(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/health")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body["checks"]) == 14
    assert body["grade"] in {"A", "B", "C", "D", "F"}


def test_health_finds_the_defects_seeded_on_purpose(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/health").get_json()
    failed = {c["name"] for c in body["checks"] if c["status"] == "fail"}

    # The demo schedule deliberately contains a lead, excess lags, non-FS
    # logic and unresourced activities.
    assert "Leads" in failed
    assert "Lags" in failed
    assert "Resources" in failed


def test_checks_are_skipped_when_a_project_has_no_baseline(signed_in, app_context):
    """A project without baseline or actuals must report those checks as
    skipped rather than passing them vacuously — the score is only as honest
    as what it admits it could not measure."""
    from extensions import db
    from models import Task

    client, project, _ = signed_in
    for task in Task.query.filter_by(project_id=project.id).all():
        task.baseline_start = task.baseline_finish = task.baseline_duration = None
        task.actual_start = task.actual_finish = None
    db.session.commit()

    body = client.get(f"/api/schedule/projects/{project.id}/health").get_json()
    by_number = {c["number"]: c for c in body["checks"]}

    assert body["has_baseline"] is False
    for number in (9, 11, 14):
        assert by_number[number]["status"] == "skipped"
        assert "Skipped" in by_number[number]["detail"]


def test_critical_path_endpoint_returns_only_critical_activities(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/critical-path").get_json()

    assert body["success"] is True
    assert all(a["is_critical"] for a in body["activities"])


def test_anonymous_access_is_refused(client, seeded):
    response = client.get(f"/api/schedule/projects/{seeded.id}/cpm")
    assert response.status_code in (302, 401)


def test_other_tenants_project_is_indistinguishable_from_missing(signed_in, app_context):
    """A cross-company request must not confirm that the project exists."""
    from datetime import date

    from extensions import db
    from models import Company, Project

    client, own_project, _ = signed_in

    rival = Company(name="Rival Contractors")
    db.session.add(rival)
    db.session.flush()
    rival_project = Project(
        name="Confidential Bid",
        company_id=rival.id,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 6, 5),
    )
    db.session.add(rival_project)
    db.session.commit()

    rival_response = client.get(f"/api/schedule/projects/{rival_project.id}/cpm")
    missing_response = client.get("/api/schedule/projects/999999/cpm")

    assert rival_response.status_code == 404
    assert rival_response.get_json() == missing_response.get_json()


def test_admin_of_one_company_cannot_read_another_companys_project(app_context, client):
    """Admin is a role within a company, not a cross-tenant superuser."""
    from datetime import date

    from extensions import db
    from models import Company, Project, User, UserRole

    company_a = Company(name="Company A")
    company_b = Company(name="Company B")
    db.session.add_all([company_a, company_b])
    db.session.flush()

    admin = User(
        username="admin_a",
        email="admin@a.example",
        password_hash=generate_password_hash("x"),
        first_name="Ada",
        last_name="Admin",
        role=UserRole.ADMIN,
        company_id=company_a.id,
    )
    secret = Project(
        name="Company B Secret",
        company_id=company_b.id,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 6, 5),
    )
    db.session.add_all([admin, secret])
    db.session.commit()

    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    response = client.get(f"/projects/{secret.id}", follow_redirects=False)
    assert response.status_code == 302  # redirected away, not rendered


def test_task_update_rejects_an_unknown_status(signed_in):
    client, project, _ = signed_in
    from models import Task

    task = Task.query.filter_by(project_id=project.id).first()
    response = client.put(
        f"/scheduling/api/tasks/{task.id}/update",
        json={"status": "totally_made_up"},
    )

    assert response.status_code == 400
    assert "status must be one of" in response.get_json()["error"]


def test_task_update_accepts_a_valid_status(signed_in):
    client, project, _ = signed_in
    from models import Task, TaskStatus

    task = Task.query.filter_by(project_id=project.id).first()
    response = client.put(
        f"/scheduling/api/tasks/{task.id}/update",
        json={"status": "in_progress", "progress": 40},
    )

    assert response.status_code == 200
    assert Task.query.get(task.id).status is TaskStatus.IN_PROGRESS


def test_task_update_rejects_out_of_range_progress(signed_in):
    client, project, _ = signed_in
    from models import Task

    task = Task.query.filter_by(project_id=project.id).first()
    response = client.put(f"/scheduling/api/tasks/{task.id}/update", json={"progress": 150})

    assert response.status_code == 400


def test_seed_produces_an_internally_consistent_schedule(seeded):
    """Stored task dates must match what CPM computes, or the demo's own
    health report would be measuring a contradiction."""
    from services.schedule_analysis import analyse_project

    result = analyse_project(seeded.id)
    assert result["success"] is True
    assert result["calculated_finish"] == seeded.end_date.isoformat()


def test_browser_gets_an_html_error_page(client):
    """Every error handler used to return JSON, so a mistyped URL showed raw
    JSON to a person using a browser."""
    response = client.get("/no-such-page", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["Content-Type"].startswith("text/html")


def test_api_clients_get_json_errors(client):
    response = client.get("/no-such-page", headers={"Accept": "application/json"})

    assert response.status_code == 404
    assert response.get_json() == {"error": "Page not found"}


def test_api_paths_get_json_regardless_of_accept_header(client):
    response = client.get("/api/schedule/projects/1/nope", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.headers["Content-Type"].startswith("application/json")


# ── baselines and progress ────────────────────────────────────────────────


def test_all_fourteen_checks_run_once_a_baseline_and_actuals_exist(signed_in):
    """The demo project now carries both, so nothing should report skipped."""
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/health").get_json()

    assert body["has_baseline"] is True
    assert [c for c in body["checks"] if c["status"] == "skipped"] == []


def test_baseline_execution_index_reflects_the_seeded_slip(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/progress").get_json()

    assert body["success"] is True
    assert body["has_baseline"] is True
    assert body["has_actuals"] is True
    # Four of seven activities due by the data date are actually complete.
    assert 0 < body["baseline_execution_index"] < 1
    assert body["activities_behind"] > 0


def test_progress_names_the_activities_that_slipped(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/progress").get_json()

    names = {a["name"] for a in body["behind_activities"]}
    assert "Demolition & strip-out" in names


def test_setting_a_baseline_supersedes_the_previous_one(signed_in, app_context):
    from models import ScheduleBaseline

    client, project, _ = signed_in
    response = client.post(
        f"/api/schedule/projects/{project.id}/baseline",
        json={"name": "Rev B", "notes": "after the demolition slip"},
    )

    assert response.status_code == 201
    assert response.get_json()["baseline"]["task_count"] == 25

    current = ScheduleBaseline.query.filter_by(project_id=project.id, is_current=True).all()
    assert len(current) == 1
    assert current[0].name == "Rev B"
    # The superseded baseline is kept, not deleted.
    assert ScheduleBaseline.query.filter_by(project_id=project.id).count() == 2


def test_baseline_requires_a_json_body(signed_in):
    """The JSON requirement is half of what stands in for CSRF here."""
    client, project, _ = signed_in
    response = client.post(
        f"/api/schedule/projects/{project.id}/baseline",
        data="name=Rev+B",
        content_type="application/x-www-form-urlencoded",
    )

    assert response.status_code == 415


def test_baseline_requires_a_name(signed_in):
    client, project, _ = signed_in
    response = client.post(f"/api/schedule/projects/{project.id}/baseline", json={})

    assert response.status_code == 400


def test_baseline_is_refused_for_another_tenants_project(signed_in, app_context):
    from datetime import date

    from extensions import db
    from models import Company, Project

    client, _, _ = signed_in
    rival = Company(name="Rival Co")
    db.session.add(rival)
    db.session.flush()
    rival_project = Project(
        name="Rival", company_id=rival.id, start_date=date(2026, 1, 5), end_date=date(2026, 6, 5)
    )
    db.session.add(rival_project)
    db.session.commit()

    response = client.post(
        f"/api/schedule/projects/{rival_project.id}/baseline", json={"name": "Nope"}
    )
    assert response.status_code == 404


def test_task_baseline_variance_properties(seeded):
    from models import Task

    task = Task.query.filter_by(project_id=seeded.id, wbs_code="A110").one()

    assert task.is_complete is True
    # Demolition was seeded four working days late.
    assert task.finish_variance_days > 0
    assert task.baseline_finish is not None


# ── Monte Carlo risk ──────────────────────────────────────────────────────


def test_risk_endpoint_returns_dated_percentiles(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/risk?iterations=400")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert set(body["percentiles"]) == {"p10", "p50", "p80", "p90"}
    assert set(body["dates"]) == {"deterministic", "p10", "p50", "p80", "p90"}
    assert body["dates"]["p80"] > body["dates"]["p50"]


def test_risk_shows_the_deterministic_date_is_optimistic(signed_in):
    """The headline finding a single-number schedule hides."""
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/risk?iterations=600").get_json()

    assert body["percentiles"]["p80"] > body["deterministic_duration_days"]
    assert body["confidence_in_deterministic"] < 0.5


def test_risk_reports_criticality_per_activity(signed_in):
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/risk?iterations=400").get_json()

    assert len(body["activities"]) == 25
    top = body["activities"][0]
    assert top["criticality_index"] == 1.0
    assert "duration_sensitivity" in top


def test_risk_rejects_an_unknown_distribution(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/risk?distribution=gaussian")

    assert response.status_code == 400
    assert "distribution must be one of" in response.get_json()["error"]


def test_risk_rejects_non_numeric_iterations(signed_in):
    client, project, _ = signed_in
    response = client.get(f"/api/schedule/projects/{project.id}/risk?iterations=lots")

    assert response.status_code == 400


def test_risk_iterations_are_capped(signed_in):
    """An unbounded iteration count is a denial-of-service vector."""
    from services.schedule_risk import MAX_ITERATIONS

    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/risk?iterations=99999999").get_json()

    assert body["iterations"] == MAX_ITERATIONS


def test_risk_is_refused_for_another_tenants_project(signed_in, app_context):
    from datetime import date

    from extensions import db
    from models import Company, Project

    client, _, _ = signed_in
    rival = Company(name="Rival Risk Co")
    db.session.add(rival)
    db.session.flush()
    rival_project = Project(
        name="Rival", company_id=rival.id, start_date=date(2026, 1, 5), end_date=date(2026, 6, 5)
    )
    db.session.add(rival_project)
    db.session.commit()

    assert client.get(f"/api/schedule/projects/{rival_project.id}/risk").status_code == 404
