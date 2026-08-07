"""Pure scheduling algorithms with no Flask or database dependencies.

Everything in this package operates on plain dataclasses so it can be unit
tested, reused from a CLI, or called from a background worker without an
application context.
"""

from core.calendar import WorkCalendar
from core.cpm import (
    Activity,
    ActivityResult,
    Relationship,
    RelationType,
    ScheduleCycleError,
    ScheduleResult,
    calculate_cpm,
)
from core.schedule_health import CheckResult, HealthReport, assess_schedule

__all__ = [
    "Activity",
    "Relationship",
    "RelationType",
    "ScheduleResult",
    "ActivityResult",
    "ScheduleCycleError",
    "calculate_cpm",
    "WorkCalendar",
    "assess_schedule",
    "HealthReport",
    "CheckResult",
]
