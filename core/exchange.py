"""A format-neutral schedule model, for moving data between file formats.

:mod:`core.cpm` deliberately holds only what the algorithm needs — id, name,
duration, logic. A file exchange has to carry considerably more, and anything
it drops is lost on round trip: calendars, WBS structure, resources, costs,
actual dates, and the distinction between a constrained and a computed date.

This module is that richer model. It knows nothing about Primavera or
Microsoft; the readers and writers in :mod:`core.xer` and :mod:`core.mspdi`
translate to and from it, so adding a third format means one new module rather
than a new pairwise converter.

Everything here is plain dataclasses with no I/O, so it can be constructed in a
test without touching a file or a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from core.cpm import Activity, Relationship, RelationType


class ActivityKind(str, Enum):
    """What sort of thing an activity is.

    Milestones matter: they carry zero duration, and an importer that quietly
    turns them into one-day tasks changes the logic network.
    """

    TASK = "task"
    START_MILESTONE = "start_milestone"
    FINISH_MILESTONE = "finish_milestone"
    LEVEL_OF_EFFORT = "level_of_effort"
    WBS_SUMMARY = "wbs_summary"

    @property
    def is_milestone(self) -> bool:
        return self in (ActivityKind.START_MILESTONE, ActivityKind.FINISH_MILESTONE)


class ConstraintType(str, Enum):
    """A date imposed on an activity rather than derived from logic."""

    NONE = "none"
    START_ON = "start_on"
    START_ON_OR_AFTER = "start_on_or_after"
    START_ON_OR_BEFORE = "start_on_or_before"
    FINISH_ON = "finish_on"
    FINISH_ON_OR_AFTER = "finish_on_or_after"
    FINISH_ON_OR_BEFORE = "finish_on_or_before"
    AS_LATE_AS_POSSIBLE = "as_late_as_possible"
    MANDATORY_START = "mandatory_start"
    MANDATORY_FINISH = "mandatory_finish"


@dataclass
class CalendarException:
    """A single day that departs from the normal working pattern."""

    day: date
    working: bool = False
    hours: float = 0.0


@dataclass
class Calendar:
    """A working pattern.

    ``hours_per_day`` is what converts a duration in hours — which is how both
    XER and MSPDI store it — into days. Assuming 8 regardless of what the file
    says silently rescales every duration in the schedule.
    """

    id: str
    name: str
    hours_per_day: float = 8.0
    hours_per_week: float = 40.0
    # Monday=0 ... Sunday=6, matching datetime.weekday().
    working_weekdays: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})
    exceptions: list[CalendarException] = field(default_factory=list)
    is_default: bool = False

    def __post_init__(self) -> None:
        if self.hours_per_day <= 0:
            raise ValueError(f"Calendar {self.id!r} has non-positive hours_per_day")

    def is_working_day(self, day: date) -> bool:
        for exception in self.exceptions:
            if exception.day == day:
                return exception.working
        return day.weekday() in self.working_weekdays

    def hours_to_days(self, hours: float | None) -> float:
        """Convert a duration in hours to days using this calendar."""
        if not hours:
            return 0.0
        return hours / self.hours_per_day

    def days_to_hours(self, days: float | None) -> float:
        if not days:
            return 0.0
        return days * self.hours_per_day


@dataclass
class WBSNode:
    """One node of the work breakdown structure."""

    id: str
    name: str
    parent_id: str | None = None
    code: str = ""
    sequence: int = 0


@dataclass
class ExchangeResource:
    """A resource that can be assigned to activities."""

    id: str
    name: str
    kind: str = "labor"  # labor, material, equipment
    unit: str = ""
    standard_rate: float | None = None
    max_units_per_day: float | None = None
    calendar_id: str | None = None


@dataclass
class ExchangeAssignment:
    """A resource assigned to an activity."""

    activity_id: str
    resource_id: str
    units: float = 1.0
    budgeted_cost: float | None = None
    actual_cost: float | None = None
    budgeted_hours: float | None = None


@dataclass
class ExchangeActivity:
    """An activity, carrying everything a file format needs to round trip."""

    id: str
    name: str

    # Duration is held in days. Both XER and MSPDI store hours; the calendar
    # does the conversion, so the number here is meaningful without one.
    duration: float = 0.0
    remaining_duration: float | None = None

    kind: ActivityKind = ActivityKind.TASK
    wbs_id: str | None = None
    calendar_id: str | None = None
    code: str = ""  # activity id as the planner sees it, e.g. "A1010"
    notes: str = ""

    # Planned or computed
    early_start: date | None = None
    early_finish: date | None = None
    late_start: date | None = None
    late_finish: date | None = None

    # Baseline
    baseline_start: date | None = None
    baseline_finish: date | None = None

    # What happened
    actual_start: date | None = None
    actual_finish: date | None = None
    percent_complete: float = 0.0

    # Imposed dates
    constraint_type: ConstraintType = ConstraintType.NONE
    constraint_date: date | None = None

    total_float: float | None = None
    free_float: float | None = None

    budgeted_cost: float | None = None
    actual_cost: float | None = None

    @property
    def is_complete(self) -> bool:
        return self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        return self.actual_start is not None

    def __post_init__(self) -> None:
        if self.duration < 0:
            raise ValueError(f"Activity {self.id!r} has negative duration {self.duration}")
        if self.kind.is_milestone and self.duration:
            raise ValueError(f"Milestone {self.id!r} must have zero duration, got {self.duration}")


@dataclass
class ExchangeRelationship:
    """A logic tie, with lag held in days."""

    predecessor_id: str
    successor_id: str
    type: RelationType = RelationType.FS
    lag: float = 0.0


@dataclass
class ExchangeSchedule:
    """A whole schedule, independent of any file format."""

    name: str = "Imported Project"
    code: str = ""
    start_date: date | None = None
    finish_date: date | None = None
    data_date: date | None = None
    default_calendar_id: str | None = None

    activities: list[ExchangeActivity] = field(default_factory=list)
    relationships: list[ExchangeRelationship] = field(default_factory=list)
    calendars: list[Calendar] = field(default_factory=list)
    wbs: list[WBSNode] = field(default_factory=list)
    resources: list[ExchangeResource] = field(default_factory=list)
    assignments: list[ExchangeAssignment] = field(default_factory=list)

    # Anything the reader could not map. Surfaced rather than silently dropped,
    # so an import can tell you what it did not understand.
    warnings: list[str] = field(default_factory=list)
    source_format: str = ""
    exported_at: datetime | None = None

    # ── lookups ──────────────────────────────────────────────────────────

    def activity(self, activity_id: str) -> ExchangeActivity | None:
        return next((a for a in self.activities if a.id == activity_id), None)

    def calendar(self, calendar_id: str | None) -> Calendar | None:
        if calendar_id is None:
            return self.default_calendar
        return next((c for c in self.calendars if c.id == calendar_id), None)

    @property
    def default_calendar(self) -> Calendar | None:
        if self.default_calendar_id:
            match = next((c for c in self.calendars if c.id == self.default_calendar_id), None)
            if match:
                return match
        return next((c for c in self.calendars if c.is_default), None) or (
            self.calendars[0] if self.calendars else None
        )

    def calendar_for(self, activity: ExchangeActivity) -> Calendar | None:
        return self.calendar(activity.calendar_id)

    # ── validation ───────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Structural problems, as a list of messages. Empty means sound.

        Deliberately returns rather than raises: an import should be able to
        report everything wrong with a file at once instead of stopping at the
        first problem.
        """
        problems: list[str] = []

        ids = [a.id for a in self.activities]
        duplicates = sorted({aid for aid in ids if ids.count(aid) > 1})
        if duplicates:
            problems.append(f"Duplicate activity ids: {', '.join(duplicates)}")

        known = set(ids)
        for link in self.relationships:
            if link.predecessor_id not in known:
                problems.append(
                    f"Relationship references unknown predecessor {link.predecessor_id!r}"
                )
            if link.successor_id not in known:
                problems.append(f"Relationship references unknown successor {link.successor_id!r}")
            if link.predecessor_id == link.successor_id:
                problems.append(f"Activity {link.predecessor_id!r} depends on itself")

        calendar_ids = {c.id for c in self.calendars}
        for activity in self.activities:
            if activity.calendar_id and activity.calendar_id not in calendar_ids:
                problems.append(
                    f"Activity {activity.id!r} references unknown calendar {activity.calendar_id!r}"
                )

        wbs_ids = {node.id for node in self.wbs}
        for node in self.wbs:
            if node.parent_id and node.parent_id not in wbs_ids:
                problems.append(f"WBS node {node.id!r} references unknown parent")

        resource_ids = {r.id for r in self.resources}
        for assignment in self.assignments:
            if assignment.resource_id not in resource_ids:
                problems.append(
                    f"Assignment references unknown resource {assignment.resource_id!r}"
                )
            if assignment.activity_id not in known:
                problems.append(
                    f"Assignment references unknown activity {assignment.activity_id!r}"
                )

        return problems

    # ── handing off to the scheduling engine ─────────────────────────────

    def to_cpm(self) -> tuple[list[Activity], list[Relationship]]:
        """Reduce to what :func:`core.cpm.calculate_cpm` needs.

        Durations are rounded to whole days because the engine works in whole
        working days. Fractional durations from a file are rounded up, since a
        task needing 1.2 days occupies two.
        """
        import math

        activities = [
            Activity(
                id=a.id,
                name=a.name,
                duration=0 if a.kind.is_milestone else max(0, math.ceil(a.duration)),
            )
            for a in self.activities
            if a.kind is not ActivityKind.WBS_SUMMARY
        ]
        included = {a.id for a in activities}
        relationships = [
            Relationship(
                predecessor=link.predecessor_id,
                successor=link.successor_id,
                type=link.type,
                lag=round(link.lag),
            )
            for link in self.relationships
            if link.predecessor_id in included and link.successor_id in included
        ]
        return activities, relationships

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for activity in self.activities:
            kinds[activity.kind.value] = kinds.get(activity.kind.value, 0) + 1

        link_types: dict[str, int] = {}
        for link in self.relationships:
            link_types[link.type.value] = link_types.get(link.type.value, 0) + 1

        return {
            "name": self.name,
            "source_format": self.source_format,
            "activities": len(self.activities),
            "activity_kinds": kinds,
            "relationships": len(self.relationships),
            "relationship_types": link_types,
            "calendars": len(self.calendars),
            "wbs_nodes": len(self.wbs),
            "resources": len(self.resources),
            "assignments": len(self.assignments),
            "warnings": len(self.warnings),
        }
