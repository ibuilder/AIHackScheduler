"""Bridge between the database models and the pure scheduling engine.

Keeping the translation in one place means the algorithms in ``core`` never
import Flask or SQLAlchemy, and the blueprints never reimplement CPM.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from core.calendar import WorkCalendar
from core.cpm import (
    Activity,
    Relationship,
    RelationType,
    ScheduleCycleError,
    calculate_cpm,
    longest_path,
)
from core.schedule_health import assess_schedule
from models import Project, ResourceAssignment, Task, TaskDependency


def load_network(project_id: int) -> tuple[list[Activity], list[Relationship], WorkCalendar]:
    """Read a project out of the database as a pure logic network."""
    project = Project.query.get(project_id)
    if project is None:
        raise LookupError(f"Project {project_id} not found")

    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.start_date, Task.id).all()
    task_ids = {task.id for task in tasks}

    activities = [
        Activity(
            id=str(task.id),
            name=task.name,
            duration=task.duration or 0,
            constraint_start=_constraint_offset(task, project.start_date),
        )
        for task in tasks
    ]

    dependencies = (
        TaskDependency.query.filter(TaskDependency.task_id.in_(task_ids)).all() if task_ids else []
    )
    relationships = [
        Relationship(
            predecessor=str(dep.predecessor_task_id),
            successor=str(dep.task_id),
            type=_relation_type(dep.dependency_type),
            lag=dep.lag_days or 0,
        )
        for dep in dependencies
        # Guard against dependencies pointing outside this project, which the
        # schema permits but CPM cannot resolve.
        if dep.predecessor_task_id in task_ids and dep.task_id in task_ids
    ]

    calendar = WorkCalendar(project.start_date)
    return activities, relationships, calendar


def _relation_type(raw: str | None) -> RelationType:
    try:
        return RelationType((raw or "FS").upper())
    except ValueError:
        return RelationType.FS


def _constraint_offset(task: Task, project_start: date) -> int | None:
    """Treat a task pinned by an explicit constraint as a hard start.

    Only tasks that record a ``must_start_on`` constraint are pinned; ordinary
    planned start dates are an output of CPM, not an input to it.
    """
    constraints = task.constraints or {}
    if not isinstance(constraints, dict):
        return None
    pinned = constraints.get("must_start_on")
    if not pinned:
        return None
    try:
        pinned_date = date.fromisoformat(pinned)
    except (TypeError, ValueError):
        return None
    return max(0, WorkCalendar(project_start).work_days_between(project_start, pinned_date) - 1)


def analyse_project(project_id: int) -> dict[str, Any]:
    """Run CPM and return dated activities plus the driving path."""
    activities, relationships, calendar = load_network(project_id)

    if not activities:
        return {"success": False, "error": "Project has no tasks to schedule"}

    try:
        result = calculate_cpm(activities, relationships)
    except ScheduleCycleError as exc:
        return {
            "success": False,
            "error": "Schedule logic contains a circular dependency",
            "cycle": exc.cycle,
        }
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    driving_path = longest_path(result, relationships)

    return {
        "success": True,
        "project_id": project_id,
        "project_duration_days": result.project_duration,
        "calculated_finish": calendar.finish_date_for(0, result.project_duration).isoformat(),
        "critical_path": driving_path,
        "critical_activity_count": len(result.critical_path),
        "activities": [
            {
                "id": item.id,
                "name": item.name,
                "duration": item.duration,
                "early_start": calendar.date_for_offset(item.early_start).isoformat(),
                "early_finish": calendar.finish_date_for(
                    item.early_start, item.duration
                ).isoformat(),
                "late_start": calendar.date_for_offset(item.late_start).isoformat(),
                "late_finish": calendar.finish_date_for(item.late_start, item.duration).isoformat(),
                "total_float": item.total_float,
                "free_float": item.free_float,
                "is_critical": item.is_critical,
            }
            for item in result.ordered()
        ],
    }


def health_check(project_id: int) -> dict[str, Any]:
    """Run the DCMA 14-point assessment against a stored project."""
    activities, relationships, _ = load_network(project_id)

    if not activities:
        return {"success": False, "error": "Project has no tasks to assess"}

    try:
        result = calculate_cpm(activities, relationships)
    except ScheduleCycleError as exc:
        return {
            "success": False,
            "error": "Schedule logic contains a circular dependency",
            "cycle": exc.cycle,
        }

    task_ids = [int(a.id) for a in activities]
    resourced = {
        str(assignment.task_id)
        for assignment in ResourceAssignment.query.filter(
            ResourceAssignment.task_id.in_(task_ids)
        ).all()
    }

    # Checks 9, 11 and 14 need recorded actual and baseline finish dates. The
    # Task model has neither — only a status enum — so those checks report as
    # skipped. Deriving "actuals" from the CPM forward pass would make them
    # look assessed while measuring nothing but the plan against itself.
    report = assess_schedule(
        activities,
        relationships,
        result=result,
        resourced_activity_ids=sorted(resourced),
    )

    payload = report.to_dict()
    payload["success"] = True
    payload["project_id"] = project_id
    return payload


def critical_path_tasks(project_id: int) -> list[Task]:
    """The driving path as ORM objects, for templates that need task fields."""
    activities, relationships, _ = load_network(project_id)
    if not activities:
        return []
    result = calculate_cpm(activities, relationships)
    chain = longest_path(result, relationships)
    by_id = {str(t.id): t for t in Task.query.filter_by(project_id=project_id).all()}
    return [by_id[aid] for aid in chain if aid in by_id]
