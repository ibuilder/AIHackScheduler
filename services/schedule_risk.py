"""Running Monte Carlo schedule risk against a stored project.

The simulation itself lives in :mod:`core.risk` and knows nothing about the
database. This module reads the network, supplies three-point estimates, and
maps working-day results back onto calendar dates.
"""

from __future__ import annotations

from typing import Any

from core.cpm import ScheduleCycleError
from core.risk import Distribution, DurationEstimate, simulate
from models import Task
from services.schedule_analysis import load_network

DEFAULT_ITERATIONS = 2000
MAX_ITERATIONS = 20000


def _estimates_from_tasks(project_id: int, activities) -> list[DurationEstimate] | None:
    """Read explicit three-point estimates where a task carries them.

    A task can record its own range under ``constraints`` as
    ``{"optimistic": 8, "pessimistic": 20}``. Where no task does, ``None`` is
    returned so the simulation falls back to its derived defaults rather than
    silently mixing measured ranges with assumed ones.
    """
    tasks = {str(t.id): t for t in Task.query.filter_by(project_id=project_id).all()}
    explicit = 0
    estimates = []

    for activity in activities:
        task = tasks.get(activity.id)
        constraints = (task.constraints if task else None) or {}
        if not isinstance(constraints, dict):
            constraints = {}

        optimistic = constraints.get("optimistic")
        pessimistic = constraints.get("pessimistic")
        if optimistic is not None and pessimistic is not None:
            try:
                low, high = float(optimistic), float(pessimistic)
            except (TypeError, ValueError):
                low = high = None
            if low is not None and low <= activity.duration <= high:
                estimates.append(DurationEstimate(activity.id, low, float(activity.duration), high))
                explicit += 1
                continue

        # No usable range on this task: bracket the planned duration.
        estimates.append(
            DurationEstimate(
                activity.id,
                activity.duration * 0.90,
                float(activity.duration),
                activity.duration * 1.45,
            )
        )

    return estimates if explicit else None


def simulate_project(
    project_id: int,
    iterations: int = DEFAULT_ITERATIONS,
    distribution: Distribution = Distribution.PERT,
) -> dict[str, Any]:
    """Run the simulation and return calendar-dated percentiles."""
    iterations = max(1, min(int(iterations), MAX_ITERATIONS))

    try:
        activities, relationships, calendar = load_network(project_id)
    except LookupError as exc:
        return {"success": False, "error": str(exc)}

    if not activities:
        return {"success": False, "error": "Project has no tasks to simulate"}

    try:
        result = simulate(
            activities,
            relationships,
            estimates=_estimates_from_tasks(project_id, activities),
            iterations=iterations,
            distribution=distribution,
        )
    except ScheduleCycleError as exc:
        return {
            "success": False,
            "error": "Schedule logic contains a circular dependency",
            "cycle": exc.cycle,
        }
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    payload = result.to_dict()
    payload["success"] = True
    payload["project_id"] = project_id
    payload["distribution"] = distribution.value

    # Percentiles are only meaningful to a planner as dates.
    payload["dates"] = {
        "deterministic": calendar.finish_date_for(0, result.deterministic_duration).isoformat(),
        **{
            name: calendar.finish_date_for(0, result.percentile(p)).isoformat()
            for name, p in (("p10", 10), ("p50", 50), ("p80", 80), ("p90", 90))
        },
    }
    return payload
