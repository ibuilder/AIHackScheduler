"""Every template a view renders must actually exist.

Nine routes rendered templates that were never written, so they raised
TemplateNotFound and returned 500. Nothing caught it because nothing ever
requested those pages. This test walks the source for ``render_template``
calls and checks each target resolves.

The allowlist below records the pages still outstanding. Removing an entry as
each page is built is the point; adding one should need a reason.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = REPO_ROOT / "templates"

# Pages a view renders that have not been written yet. Each 500s if requested.
# Every template a view names now exists. This set is deliberately empty:
# a new view rendering a template nobody wrote fails the test below rather
# than returning 500 to whoever clicks the link first.
KNOWN_MISSING: set[str] = set()

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "tests",
    # `python -m build` writes a verbatim copy of the source tree to build/lib,
    # so without these a packaged working tree gets scanned twice. See the same
    # list in tests/test_static_integrity.py, where it caused a real failure.
    "build",
    "dist",
    ".eggs",
    ".tox",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
}


def _referenced_templates() -> set[str]:
    """Every literal template name passed to render_template across the app."""
    found = set()

    for path in REPO_ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - would fail elsewhere first
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "render_template" or not node.args:
                continue
            first = node.args[0]
            # Only literals can be checked statically; a computed name is
            # outside what this test can verify.
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.add(first.value)

    return found


def test_the_scan_finds_templates_at_all():
    """Guard against the AST walk silently matching nothing."""
    assert len(_referenced_templates()) > 15


def test_every_referenced_template_exists():
    referenced = _referenced_templates()
    missing = {name for name in referenced if not (TEMPLATE_ROOT / name).is_file()}

    unexpected = missing - KNOWN_MISSING
    assert not unexpected, (
        "These views render templates that do not exist and will return 500: "
        + ", ".join(sorted(unexpected))
    )


def test_the_allowlist_does_not_go_stale():
    """A page that has since been written must come off the allowlist."""
    referenced = _referenced_templates()
    missing = {name for name in referenced if not (TEMPLATE_ROOT / name).is_file()}

    now_present = KNOWN_MISSING - missing
    assert not now_present, (
        "These templates now exist; remove them from KNOWN_MISSING: "
        + ", ".join(sorted(now_present))
    )


@pytest.mark.parametrize("name", sorted(KNOWN_MISSING))
def test_known_missing_pages_are_still_missing(name):
    """Documents the outstanding gap, one page per line in the test report."""
    assert not (TEMPLATE_ROOT / name).is_file()


def test_the_invoice_pages_render(signed_in, app_context):
    """The two financial templates were among the missing set; they are the
    ones the payment flow needs, so they are built and exercised here."""
    from datetime import date, timedelta
    from decimal import Decimal

    from extensions import db
    from models import Invoice, InvoiceStatus, User

    client, project, _ = signed_in
    user = User.query.filter_by(username="demo").first()

    invoice = Invoice(
        invoice_number="INV-0001",
        client_name="Acme Developments",
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        subtotal=Decimal("1000.00"),
        total_amount=Decimal("1000.00"),
        status=InvoiceStatus.SENT,
        project_id=project.id,
        company_id=user.company_id,
        created_by_id=user.id,
    )
    db.session.add(invoice)
    db.session.commit()

    detail = client.get(f"/invoices/{invoice.id}")
    assert detail.status_code == 200
    assert b"Record a payment" in detail.data

    create = client.get("/invoices/create")
    assert create.status_code == 200


# ── url_for endpoints ─────────────────────────────────────────────────────


def _template_endpoints() -> dict:
    """Every endpoint name passed to url_for in a template, with its files."""
    import re

    pattern = re.compile(r"""url_for\(\s*['"]([a-zA-Z0-9_.]+)['"]""")
    found = {}
    for path in TEMPLATE_ROOT.rglob("*.html"):
        for name in set(pattern.findall(path.read_text(encoding="utf-8"))):
            found.setdefault(name, set()).add(path.relative_to(TEMPLATE_ROOT).as_posix())
    return found


def test_the_endpoint_scan_finds_something():
    assert len(_template_endpoints()) > 10


def test_every_url_for_in_a_template_resolves(flask_app):
    """A url_for naming an endpoint that does not exist raises BuildError,
    which fails the entire page render rather than just that one link. Six
    templates pointed at endpoints that had been renamed or never written."""
    registered = {rule.endpoint for rule in flask_app.url_map.iter_rules()}

    broken = {
        name: sorted(files)
        for name, files in _template_endpoints().items()
        if name not in registered
    }

    assert not broken, "Templates reference endpoints that do not exist: " + "; ".join(
        f"{name} (in {', '.join(files)})" for name, files in sorted(broken.items())
    )


def test_equipment_pages_render_with_a_project_assigned(signed_in):
    """The equipment list only hit its broken project link when a machine had
    a current project, which the seed now gives it."""
    from models import Equipment

    client, _, _ = signed_in
    machine = Equipment.query.filter(Equipment.current_project_id.isnot(None)).first()
    assert machine is not None, "seed should assign equipment to the demo project"

    assert client.get("/equipment").status_code == 200
    assert client.get(f"/equipment/{machine.id}").status_code == 200
    assert client.get("/maintenance").status_code == 200


def test_admin_users_page_renders(signed_in):
    """It linked to admin.edit_user, which has no route, so the page 500ed."""
    from extensions import db
    from models import User, UserRole

    client, _, _ = signed_in
    user = User.query.filter_by(username="demo").first()
    user.role = UserRole.ADMIN
    db.session.commit()

    assert client.get("/admin/users").status_code == 200


# ── every main page renders ───────────────────────────────────────────────


def test_every_main_page_renders(signed_in):
    """Templates read variables their views never passed, so Jinja resolved
    them to Undefined and `|round(1)` raised TypeError at render time. Nothing
    caught it because no test had ever requested these pages."""
    from models import Equipment

    client, project, _ = signed_in
    machine = Equipment.query.first()

    pages = [
        "/dashboard",
        "/projects/",
        f"/projects/{project.id}",
        f"/scheduling/gantt/{project.id}",
        f"/scheduling/linear/{project.id}",
        f"/scheduling/pull-planning/{project.id}",
        "/financial",
        "/transactions",
        "/transactions/create",
        "/invoices",
        "/invoices/create",
        "/equipment",
        f"/equipment/{machine.id}",
        "/maintenance",
        "/maintenance/create",
    ]

    failures = []
    for path in pages:
        response = client.get(path, follow_redirects=True)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code}")

    assert not failures, "Pages that do not render: " + ", ".join(failures)


def test_the_linear_view_reports_real_stationing(signed_in):
    """The seed gives the slab and facade activities station ranges, so the
    time-distance summary should be computed from them, not left Undefined."""
    client, project, _ = signed_in
    response = client.get(f"/scheduling/linear/{project.id}")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Location:" in body
