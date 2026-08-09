"""The half of the application that writes.

Every GET route was walked; none of the 32 POST/PUT/DELETE routes were. That
is the half where authorisation lives, and it is where the damage is done when
authorisation is wrong.

It hid a live bug. Two admin blueprints each implemented ``create_user``, and
they disagreed about how to read the role field: ``UserRole(role)`` keys on the
enum value, ``UserRole[role]`` on its name. The form sends ``ADMIN``, a name, so
``POST /admin/users/create`` raised ``ValueError: 'ADMIN' is not a valid
UserRole`` on every submission. No test had ever posted to it.

This repository has also had a tenant-isolation bypass before —
``blueprints/projects.py`` checked ``role.name != 'ADMIN'`` and skipped the
company check for administrators, so any admin could read any other company's
project. The intruder tests below exist because that already happened once.
"""

from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from extensions import db
from models import Company, Project, Task, User, UserRole


@pytest.fixture
def intruder(seeded):
    """An administrator of a different company, and a client signed in as them.

    Deliberately an ADMIN: the bypass this guards against was specifically that
    an administrator skipped the company check. A viewer would be refused by
    the role check and prove nothing.
    """
    rival = Company(name="Rival Contractors")
    db.session.add(rival)
    db.session.flush()

    user = User(
        username="intruder",
        email="intruder@rival.test",
        password_hash=generate_password_hash("intruder-password"),
        first_name="In",
        last_name="Truder",
        role=UserRole.ADMIN,
        company_id=rival.id,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()

    from flask import current_app

    client = current_app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True
    return client, user


def _victim(seeded):
    task = Task.query.filter_by(project_id=seeded.id).first()
    return seeded, task


# ── tenant isolation on writes ───────────────────────────────────────────


def test_a_rival_admin_cannot_write_to_another_companys_project(intruder, seeded):
    """The headline. Each of these is a write against a project the caller's
    company does not own, and each must be refused."""
    client, _ = intruder
    project, task = _victim(seeded)

    attempts = [
        ("post", f"/api/schedule/projects/{project.id}/baseline", {"name": "stolen baseline"}),
        ("post", f"/azure/configure/{project.id}", {"service_type": "ai", "configuration": "{}"}),
        ("put", f"/scheduling/api/tasks/{task.id}/update", {"name": "HACKED"}),
        ("post", "/api/projects/quick-task", {"project_id": project.id, "name": "HACKED"}),
    ]

    allowed = []
    for method, url, payload in attempts:
        send = getattr(client, method)
        use_json = url.startswith("/api") or method == "put"
        response = send(url, json=payload) if use_json else send(url, data=payload)
        # 2xx means the write went through. Anything else refused it.
        if 200 <= response.status_code < 300:
            allowed.append(f"{url} -> {response.status_code}")

    assert not allowed, "A rival company's admin was allowed to write: " + ", ".join(allowed)


def test_the_victims_data_is_untouched_after_the_attempts(intruder, seeded):
    """Status codes can lie. This checks the database."""
    client, _ = intruder
    project, task = _victim(seeded)
    original_name = task.name
    original_task_count = Task.query.filter_by(project_id=project.id).count()

    client.put(f"/scheduling/api/tasks/{task.id}/update", json={"name": "HACKED"})
    client.post("/api/projects/quick-task", json={"project_id": project.id, "name": "HACKED"})

    db.session.expire_all()
    assert db.session.get(Task, task.id).name == original_name
    assert Task.query.filter_by(project_id=project.id).count() == original_task_count


def test_a_rival_admin_cannot_edit_a_user_in_another_company(intruder, seeded):
    """Administrators administer their own company. The role alone is not a
    licence over every tenant."""
    client, _ = intruder
    victim = User.query.filter_by(username="demo").first()
    original_email = victim.email

    client.post(
        f"/admin/users/{victim.id}/edit",
        data={
            "first_name": "Taken",
            "last_name": "Over",
            "email": "attacker@rival.test",
            "role": "VIEWER",
            "is_active": "on",
        },
    )

    db.session.expire_all()
    refreshed = db.session.get(User, victim.id)
    assert refreshed.email == original_email
    assert refreshed.role is not UserRole.VIEWER


def test_a_rival_admin_cannot_deactivate_another_companys_user(intruder, seeded):
    client, _ = intruder
    victim = User.query.filter_by(username="demo").first()

    client.post(f"/admin/users/{victim.id}/deactivate")
    client.post(f"/admin/api/users/{victim.id}/toggle-status")

    db.session.expire_all()
    assert db.session.get(User, victim.id).is_active is True


# ── the writes an owner is entitled to make ──────────────────────────────


def test_an_admin_can_create_a_user(signed_in):
    """The bug the missing coverage hid: POST here raised ValueError on every
    submission, because the role was read by value and the form sends a name."""
    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    response = client.post(
        "/admin/users/create",
        data={
            "username": "newjoiner",
            "email": "newjoiner@example.test",
            "first_name": "New",
            "last_name": "Joiner",
            "role": "PROJECT_MANAGER",
            "password": "a-long-enough-password",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    created = User.query.filter_by(username="newjoiner").first()
    assert created is not None, "the user was not created"
    assert created.role is UserRole.PROJECT_MANAGER
    assert created.company_id == user.company_id


def test_an_unknown_role_is_refused_rather_than_raising(signed_in):
    """A hand-crafted POST with a bogus role must not produce a 500."""
    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    response = client.post(
        "/admin/users/create",
        data={
            "username": "bogus",
            "email": "bogus@example.test",
            "first_name": "B",
            "last_name": "B",
            "role": "SUPREME_OVERLORD",
            "password": "a-long-enough-password",
        },
    )
    assert response.status_code < 500
    assert User.query.filter_by(username="bogus").first() is None


def test_an_admin_cannot_deactivate_their_own_account(signed_in):
    """Recoverable only by editing the database directly, so it is refused."""
    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    client.post(f"/admin/users/{user.id}/deactivate", follow_redirects=True)
    db.session.expire_all()
    assert db.session.get(User, user.id).is_active is True

    response = client.post(f"/admin/api/users/{user.id}/toggle-status")
    assert response.status_code == 400
    db.session.expire_all()
    assert db.session.get(User, user.id).is_active is True


def test_an_admin_can_update_their_own_company(signed_in):
    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    response = client.post(
        "/admin/company/settings",
        data={
            "name": "Renamed Contractors",
            "address": "1 New Street",
            "phone": "0100 000000",
            "email": "hello@renamed.test",
            "azure_tenant_id": "",
            "fabric_workspace_id": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    db.session.expire_all()
    assert db.session.get(Company, user.company_id).name == "Renamed Contractors"


# ── the retired /management surface ──────────────────────────────────────


def test_every_retired_management_path_redirects(signed_in):
    """Existing links and bookmarks must not 404 after the merge."""
    from admin.user_management import REDIRECTS, REDIRECTS_WITH_USER

    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    for path in REDIRECTS:
        response = client.get(f"/management{path}")
        assert response.status_code == 308, f"/management{path} -> {response.status_code}"
        assert "/admin" in response.headers["Location"]

    for path in REDIRECTS_WITH_USER:
        concrete = path.replace("<int:user_id>", str(user.id))
        response = client.get(f"/management{concrete}")
        assert response.status_code == 308, f"/management{concrete} -> {response.status_code}"


def test_the_redirect_preserves_the_method(signed_in):
    """308, not 302. A 302 turns a POST into a GET and drops the form body, so
    a bookmarked form would silently stop working instead of failing loudly."""
    client, _, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    response = client.post(f"/management/users/{user.id}/deactivate")
    assert response.status_code == 308


def test_no_endpoint_is_defined_twice(flask_app):
    """The merge exists to stop two blueprints implementing the same view. This
    fails if a third copy appears."""
    seen = {}
    for rule in flask_app.url_map.iter_rules():
        seen.setdefault(str(rule), []).append(rule.endpoint)

    duplicates = {url: names for url, names in seen.items() if len(set(names)) > 1}
    assert not duplicates, f"Several endpoints serve the same URL: {duplicates}"


# ── the walk ─────────────────────────────────────────────────────────────


def test_no_mutating_route_returns_a_server_error(signed_in):
    """Post an empty body to every write route and require that nothing
    explodes. A 400 or 404 is a correct answer to nonsense; a 500 is not.

    This is deliberately shallow — it cannot know what each route wants — but
    it is what catches an import error, a missing column or an unguarded
    ``request.form[...]`` on a route nobody has opened in months.
    """
    client, project, user = signed_in
    user.role = UserRole.ADMIN
    db.session.commit()

    task = Task.query.filter_by(project_id=project.id).first()
    substitutions = {
        "project_id": project.id,
        "task_id": task.id,
        "user_id": user.id,
        "id": project.id,
        "equipment_id": 1,
        "invoice_id": 1,
        "company_id": user.company_id,
        "template_id": "commercial_office",
    }

    import re

    from flask import current_app

    failures, walked = [], 0
    for rule in current_app.url_map.iter_rules():
        methods = rule.methods - {"HEAD", "OPTIONS", "GET"}
        if not methods or rule.endpoint == "static":
            continue

        url = str(rule)
        skip = False
        for argument in rule.arguments:
            if argument not in substitutions:
                skip = True
                break
            url = re.sub(
                r"<[^<>]*\b" + re.escape(argument) + r">", str(substitutions[argument]), url
            )
        if skip or "<" in url:
            continue
        # Signing out mid-walk would invalidate every later result.
        if "logout" in url or "login" in url:
            continue

        walked += 1
        try:
            response = client.post(url, data={}, follow_redirects=False)
        except Exception as exc:
            failures.append(f"{url} raised {type(exc).__name__}: {exc}")
            continue
        if response.status_code >= 500:
            failures.append(
                f"{url} -> {response.status_code}: {response.get_data(as_text=True)[:160]}"
            )

    assert walked > 15, f"only {walked} mutating routes walked"
    assert not failures, "Mutating routes returning a server error:\n  " + "\n  ".join(failures)


def test_a_write_route_rejects_an_anonymous_caller(seeded):
    """Every mutating route except login and register requires a session."""
    from flask import current_app

    anonymous = current_app.test_client()
    task = Task.query.filter_by(project_id=seeded.id).first()

    for method, url in (
        ("put", f"/scheduling/api/tasks/{task.id}/update"),
        ("post", "/admin/users/create"),
        ("post", "/admin/users/1/deactivate"),
    ):
        response = getattr(anonymous, method)(url, json={})
        assert response.status_code in (302, 401, 403), (
            f"{url} answered an anonymous write with {response.status_code}"
        )


def test_a_project_created_through_the_api_belongs_to_the_caller(signed_in):
    """A create route that trusts a company_id in the body would let a caller
    plant a project in someone else's tenant."""
    client, _, user = signed_in
    other = Company(name="Somebody Else")
    db.session.add(other)
    db.session.commit()

    client.post(
        "/api/projects/create",
        json={
            "name": "Planted",
            "company_id": other.id,
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )

    planted = Project.query.filter_by(name="Planted").first()
    if planted is not None:
        assert planted.company_id == user.company_id, (
            "a project was created in another company because the request body said so"
        )
