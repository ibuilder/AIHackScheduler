"""Every GET route, requested for real.

Walking the URL map found things no unit test did: nine templates that were
never written, two analytics endpoints whose helpers did not exist, a health
check that had returned 503 since the SQLAlchemy 2.0 upgrade, and a column the
code assigned to but the schema never had. All of them were 500s that no test
covered, because no test had ever requested the page.

This walks the map rather than a hand-written list, so a route added tomorrow
is covered the day it appears.
"""

import re

import pytest

# Placeholders for the URL converters. A route whose parameters are not all
# covered here is skipped and reported by test_no_route_is_skipped_silently,
# so adding a parameter cannot quietly drop a route out of this walk.
PARAMETERS = {
    "project_id": "{project_id}",
    "task_id": "{task_id}",
    "user_id": "{user_id}",
    "id": "{project_id}",
    "company_id": "{company_id}",
    "equipment_id": "{equipment_id}",
    "invoice_id": "{invoice_id}",
    "template_id": "commercial_office",
    "export_format": "xer",
    "format": "xer",
}

# Routes that legitimately do not answer 2xx/3xx to a bare signed-in GET.
EXPECTED_NON_SUCCESS = {
    # Requires query parameters describing what to sync.
    "/api/powerbi/sync-projects": {400},
}


def _fill(rule, values) -> str | None:
    url = str(rule)
    for argument in rule.arguments:
        if argument not in PARAMETERS:
            return None
        replacement = PARAMETERS[argument].format(**values)
        url = re.sub(r"<[^<>]*\b" + re.escape(argument) + r">", str(replacement), url)
    return None if "<" in url else url


def _walkable_rules(flask_app):
    for rule in sorted(flask_app.url_map.iter_rules(), key=str):
        if "GET" not in rule.methods or rule.endpoint == "static":
            continue
        # Signing out and then continuing to walk would make every later
        # result meaningless.
        if "logout" in str(rule):
            continue
        yield rule


@pytest.fixture
def walk_context(signed_in):
    """A signed-in admin plus real ids for every converter."""
    from extensions import db
    from models import Equipment, Invoice, Task, User, UserRole

    client, project, user = signed_in
    user.role = UserRole.ADMIN
    project.template_used = "commercial_office"
    project.created_by = user.id
    db.session.commit()

    equipment = Equipment.query.first()
    invoice = Invoice.query.first()

    values = {
        "project_id": project.id,
        "task_id": Task.query.filter_by(project_id=project.id).first().id,
        "user_id": User.query.first().id,
        "company_id": user.company_id,
        # A missing row is a 404, which is a correct answer; the point of the
        # walk is that nothing raises.
        "equipment_id": equipment.id if equipment else 1,
        "invoice_id": invoice.id if invoice else 1,
    }
    return client, values


def test_no_get_route_returns_a_server_error(walk_context, flask_app):
    """The whole point. A 500 here is a page that breaks when clicked."""
    client, values = walk_context

    failures = []
    for rule in _walkable_rules(flask_app):
        url = _fill(rule, values)
        if url is None:
            continue
        try:
            response = client.get(url)
        except Exception as exc:  # a view raising before Flask can format it
            failures.append(f"{url} raised {type(exc).__name__}: {exc}")
            continue

        allowed = EXPECTED_NON_SUCCESS.get(url, set())
        if response.status_code >= 500 and response.status_code not in allowed:
            body = response.get_data(as_text=True)[:200]
            failures.append(f"{url} -> {response.status_code}: {body}")

    assert not failures, "Routes returning a server error:\n  " + "\n  ".join(failures)


def test_no_route_is_skipped_silently(walk_context, flask_app):
    """A converter this walk cannot fill drops the route from the check above.
    That must be a deliberate, visible decision rather than a quiet gap."""
    client, values = walk_context

    skipped = [
        f"{rule} (parameters: {sorted(rule.arguments)})"
        for rule in _walkable_rules(flask_app)
        if _fill(rule, values) is None
    ]

    assert not skipped, (
        "These routes were not walked because PARAMETERS has no placeholder "
        "for one of their converters:\n  " + "\n  ".join(skipped)
    )


def test_the_walk_actually_covers_the_application(walk_context, flask_app):
    """Guard against the filter silently matching nothing."""
    client, values = walk_context
    walked = [r for r in _walkable_rules(flask_app) if _fill(r, values)]
    assert len(walked) > 70, f"only {len(walked)} routes walked"


def test_the_pages_that_used_to_be_500s_now_render(walk_context):
    """Named explicitly, so a regression points straight at what broke.

    Each of these returned 500 before: the first four rendered templates that
    did not exist, the next two called helpers that did not exist, and the
    last raised AttributeError on a column the schema did not have.
    """
    client, values = walk_context

    pages = [
        f"/management/users/{values['user_id']}/edit",
        "/management/company/settings",
        "/management/audit-logs",
        "/management/system-status",
        "/azure/dashboard",
        f"/azure/configure/{values['project_id']}",
        "/project-templates/my-templates",
        "/project-templates/templates/commercial_office",
        f"/reports/project/{values['project_id']}",
        "/api/ai/company-insights",
        f"/api/ai/resource-optimization/{values['project_id']}",
    ]

    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, (
            f"{url} -> {response.status_code}: {response.get_data(as_text=True)[:200]}"
        )
