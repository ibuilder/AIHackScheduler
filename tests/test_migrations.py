"""Migrations must build the schema the models describe, and keep doing so.

The schema changed six times during the rebuild with no migrations at all, so a
database from an earlier release had no upgrade path — `flask db upgrade` did
not exist and `create_all` only ever adds missing tables. These tests exist so
that cannot happen again quietly.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSIONS = REPO_ROOT / "migrations" / "versions"


def _run_flask(*args, database_url, expect_success=True):
    """Run a flask CLI command against a specific database."""
    import os

    env = {
        **os.environ,
        "FLASK_ENV": "development",
        "SESSION_SECRET": "migration-test-secret",
        "DATABASE_URL": database_url,
        "PYTHONPATH": str(REPO_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(f"flask {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
    return result


@pytest.fixture
def fresh_db(tmp_path):
    path = tmp_path / "fresh.db"
    return f"sqlite:///{path}", path


# ── the migration files themselves ───────────────────────────────────────


def test_migrations_directory_exists():
    assert (REPO_ROOT / "migrations" / "env.py").is_file()
    assert VERSIONS.is_dir()


def test_there_is_a_baseline_and_it_has_no_parent():
    """A database predating this work is stamped against the baseline, so the
    baseline has to describe the schema as it was, not as it is."""
    baseline = VERSIONS / "0001_baseline.py"
    assert baseline.is_file()

    source = baseline.read_text(encoding="utf-8")
    assert "down_revision = None" in source


def test_every_migration_has_a_unique_revision_and_a_single_head():
    revisions, parents = {}, {}
    for path in VERSIONS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = next(
            line.split("=", 1)[1].strip().strip("\"'")
            for line in source.splitlines()
            if line.startswith("revision =")
        )
        parent = next(
            line.split("=", 1)[1].strip().strip("\"'")
            for line in source.splitlines()
            if line.startswith("down_revision =")
        )
        assert revision not in revisions, f"duplicate revision {revision}"
        revisions[revision] = path.name
        parents[revision] = None if parent == "None" else parent

    # Exactly one revision must be nobody's parent, or `upgrade` is ambiguous.
    heads = set(revisions) - {p for p in parents.values() if p}
    assert len(heads) == 1, f"expected a single head, found {heads}"


def test_the_migration_drops_the_old_global_project_number_constraint():
    """The original schema declared project_number unique across all companies.
    Alembic cannot autodetect an unnamed constraint, so this has to be done by
    hand — and a batch block with no operations does not rebuild the table."""
    source = (VERSIONS / "0002_rebuild_schema.py").read_text(encoding="utf-8")

    assert "_projects_without_global_unique" in source
    assert "copy_from=_projects_without_global_unique()" in source


# ── running them ─────────────────────────────────────────────────────────


@pytest.mark.slow
def test_a_fresh_database_upgrades_from_empty(fresh_db):
    url, path = fresh_db
    _run_flask("db", "upgrade", database_url=url)

    tables = set(inspect(create_engine(url)).get_table_names())
    assert "alembic_version" in tables
    assert {"projects", "tasks", "task_dependencies"} <= tables
    # Everything the rebuild added.
    assert {"schedule_baselines", "equipment_usage_logs", "maintenance_records"} <= tables


@pytest.mark.slow
def test_the_migrated_schema_matches_the_models(fresh_db):
    """The check that keeps migrations honest: after upgrading, autogenerate
    must find nothing left to do."""
    url, _ = fresh_db
    _run_flask("db", "upgrade", database_url=url)

    result = _run_flask("db", "check", database_url=url, expect_success=False)
    combined = result.stdout + result.stderr

    assert "No new upgrade operations detected" in combined, combined


@pytest.mark.slow
def test_columns_the_rebuild_added_are_present(fresh_db):
    url, _ = fresh_db
    _run_flask("db", "upgrade", database_url=url)
    inspector = inspect(create_engine(url))

    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    assert {
        "baseline_start",
        "baseline_finish",
        "baseline_duration",
        "actual_start",
        "actual_finish",
    } <= task_columns

    project_columns = {c["name"] for c in inspector.get_columns("projects")}
    assert "data_date" in project_columns


@pytest.mark.slow
def test_project_number_is_unique_per_company_not_globally(fresh_db):
    """A second tenant importing a schedule with the same project code used to
    fail outright."""
    from datetime import date

    from sqlalchemy import text

    url, _ = fresh_db
    _run_flask("db", "upgrade", database_url=url)
    engine = create_engine(url)

    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO companies (id, name) VALUES (1, 'Alpha'), (2, 'Beta')")
        )
        for project_id, company_id in ((1, 1), (2, 2)):
            connection.execute(
                text(
                    "INSERT INTO projects (id, name, project_number, company_id, "
                    "start_date, end_date) VALUES (:pid, 'P', 'P-001', :cid, :s, :e)"
                ),
                {
                    "pid": project_id,
                    "cid": company_id,
                    "s": date(2026, 1, 5),
                    "e": date(2026, 6, 5),
                },
            )

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM projects WHERE project_number = 'P-001'")
        ).scalar()
    assert count == 2


@pytest.mark.slow
def test_the_downgrade_reverses_cleanly(fresh_db):
    """Downgrade to the baseline by name, not by one step.

    A bare `db downgrade` moves back a single revision, so this asserted the
    rebuild tables were gone only while 0002 happened to be the head. Naming
    the target keeps the test meaningful as migrations are added.
    """
    url, _ = fresh_db
    _run_flask("db", "upgrade", database_url=url)
    _run_flask("db", "downgrade", "0001_baseline", database_url=url)

    tables = set(inspect(create_engine(url)).get_table_names())
    assert not ({"schedule_baselines", "equipment_usage_logs", "maintenance_records"} & tables)
    # The baseline tables survive, so a downgrade lands on the original schema
    # rather than an empty database.
    assert {"projects", "tasks"} <= tables


@pytest.mark.slow
def test_upgrade_downgrade_upgrade_is_stable(fresh_db):
    url, _ = fresh_db
    _run_flask("db", "upgrade", database_url=url)
    _run_flask("db", "downgrade", database_url=url)
    _run_flask("db", "upgrade", database_url=url)

    result = _run_flask("db", "check", database_url=url, expect_success=False)
    assert "No new upgrade operations detected" in result.stdout + result.stderr
