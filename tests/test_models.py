"""Tests for data-model invariants that the schema alone does not enforce."""

from datetime import date

import pytest

from extensions import db
from models import (
    Company,
    Project,
    Resource,
    ResourceAssignment,
    Task,
    TaskDependency,
    TaskStatus,
)


def _project_with_logic():
    company = Company(name="Cascade Test Co")
    db.session.add(company)
    db.session.flush()

    project = Project(
        name="Cascade Test",
        company_id=company.id,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 6, 5),
    )
    db.session.add(project)
    db.session.flush()

    first = Task(
        name="First",
        project_id=project.id,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 9),
        duration=5,
    )
    second = Task(
        name="Second",
        project_id=project.id,
        start_date=date(2026, 1, 12),
        end_date=date(2026, 1, 16),
        duration=5,
    )
    db.session.add_all([first, second])
    db.session.flush()

    db.session.add(
        TaskDependency(task_id=second.id, predecessor_task_id=first.id, dependency_type="FS")
    )
    resource = Resource(name="Crew", type="labor", project_id=project.id, total_quantity=1)
    db.session.add(resource)
    db.session.flush()
    db.session.add(ResourceAssignment(task_id=first.id, resource_id=resource.id, quantity=1))
    db.session.commit()

    return project


def test_deleting_a_project_removes_its_dependencies(app_context):
    """Deleting a project used to null out task_dependencies.task_id, which
    both violated NOT NULL and corrupted every other project's logic."""
    project = _project_with_logic()
    assert TaskDependency.query.count() == 1

    db.session.delete(project)
    db.session.commit()

    assert TaskDependency.query.count() == 0
    assert Task.query.count() == 0


def test_deleting_a_project_removes_its_resource_assignments(app_context):
    project = _project_with_logic()
    assert ResourceAssignment.query.count() == 1

    db.session.delete(project)
    db.session.commit()

    assert ResourceAssignment.query.count() == 0


def test_deleting_a_task_removes_links_on_both_sides(app_context):
    _project_with_logic()
    predecessor = Task.query.filter_by(name="First").one()

    db.session.delete(predecessor)
    db.session.commit()

    # The link named this task as its predecessor, so it must go too.
    assert TaskDependency.query.count() == 0


def test_duplicate_dependency_pair_is_rejected(app_context):
    """A repeated link silently doubles the constraint in the forward pass."""
    from sqlalchemy.exc import IntegrityError

    project = _project_with_logic()
    tasks = {t.name: t for t in Task.query.filter_by(project_id=project.id).all()}

    db.session.add(
        TaskDependency(
            task_id=tasks["Second"].id,
            predecessor_task_id=tasks["First"].id,
            dependency_type="SS",
        )
    )
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_seed_can_be_run_twice(app_context):
    """Re-seeding replaces the demo data rather than failing on cascade."""
    from seed_demo import seed

    seed()
    seed()

    # The second run replaces the first rather than duplicating or failing.
    assert Project.query.count() == 1
    assert Task.query.count() == 25
    assert TaskDependency.query.count() == 27


def test_task_status_round_trips_through_the_enum(app_context):
    project = _project_with_logic()
    task = Task.query.filter_by(project_id=project.id).first()

    task.status = TaskStatus.ON_HOLD
    db.session.commit()
    db.session.expire_all()

    assert Task.query.get(task.id).status is TaskStatus.ON_HOLD
