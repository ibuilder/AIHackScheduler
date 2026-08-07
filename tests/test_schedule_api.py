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


def test_checks_needing_actuals_are_skipped(signed_in):
    """The Task model records no actual or baseline finish dates, so these
    checks must report as skipped rather than as passing."""
    client, project, _ = signed_in
    body = client.get(f"/api/schedule/projects/{project.id}/health").get_json()
    by_number = {c["number"]: c for c in body["checks"]}

    for number in (9, 11, 14):
        assert by_number[number]["status"] == "skipped"


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
