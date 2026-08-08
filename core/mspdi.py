"""Reading and writing Microsoft Project XML (MSPDI).

MSPDI is Microsoft's documented interchange schema, and it is the *only*
Microsoft Project format that can be written. The binary ``.mpp`` can be read
— see :mod:`services.schedule_io` for the optional MPXJ path — but not
produced: the format is proprietary and only partly understood, and MPXJ's own
maintainer says as much. A file written here opens in Microsoft Project
directly, and saving it there produces a genuine ``.mpp``.

Three details decide whether Project accepts the result:

* **Durations are ISO 8601 periods**, ``PT40H0M0S``, not day counts. They are
  measured in hours against the project calendar.
* **``Type`` on a link is an integer**: 0 FF, 1 FS, 2 SF, 3 SS. That ordering
  is not alphabetical and is easy to get wrong, which silently rewires the
  logic.
* **``UID`` and ``ID`` are different things.** ``UID`` is the stable key
  referenced by links and assignments; ``ID`` is display order. Conflating
  them breaks every relationship in the file.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime

from core.cpm import RelationType
from core.exchange import (
    ActivityKind,
    Calendar,
    ConstraintType,
    ExchangeActivity,
    ExchangeAssignment,
    ExchangeRelationship,
    ExchangeResource,
    ExchangeSchedule,
    WBSNode,
)

MSPDI_NS = "http://schemas.microsoft.com/project"

# Microsoft's link type codes. Deliberately not alphabetical.
MSPDI_LINK_TYPES = {
    0: RelationType.FF,
    1: RelationType.FS,
    2: RelationType.SF,
    3: RelationType.SS,
}
LINK_TYPES_TO_MSPDI = {value: key for key, value in MSPDI_LINK_TYPES.items()}

# ConstraintType codes from the MSPDI schema.
MSPDI_CONSTRAINTS = {
    0: ConstraintType.NONE,  # As Soon As Possible
    1: ConstraintType.AS_LATE_AS_POSSIBLE,
    2: ConstraintType.START_ON_OR_AFTER,
    3: ConstraintType.START_ON_OR_BEFORE,
    4: ConstraintType.FINISH_ON_OR_AFTER,
    5: ConstraintType.FINISH_ON_OR_BEFORE,
    6: ConstraintType.MANDATORY_START,
    7: ConstraintType.MANDATORY_FINISH,
}
CONSTRAINTS_TO_MSPDI = {
    ConstraintType.NONE: 0,
    ConstraintType.AS_LATE_AS_POSSIBLE: 1,
    ConstraintType.START_ON_OR_AFTER: 2,
    ConstraintType.START_ON: 2,
    ConstraintType.START_ON_OR_BEFORE: 3,
    ConstraintType.FINISH_ON_OR_AFTER: 4,
    ConstraintType.FINISH_ON: 5,
    ConstraintType.FINISH_ON_OR_BEFORE: 5,
    ConstraintType.MANDATORY_START: 6,
    ConstraintType.MANDATORY_FINISH: 7,
}

DEFAULT_HOURS_PER_DAY = 8.0
_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


class MSPDIError(ValueError):
    """The file could not be read as Microsoft Project XML."""


# ── helpers ──────────────────────────────────────────────────────────────


def _tag(name: str) -> str:
    return f"{{{MSPDI_NS}}}{name}"


def _text(parent, name: str, default: str = "") -> str:
    """Read a child's text, tolerating both namespaced and bare documents."""
    if parent is None:
        return default
    node = parent.find(_tag(name))
    if node is None:
        node = parent.find(name)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _children(parent, name: str):
    if parent is None:
        return []
    found = parent.findall(_tag(name))
    return found if found else parent.findall(name)


def _find(parent, name: str):
    if parent is None:
        return None
    node = parent.find(_tag(name))
    return node if node is not None else parent.find(name)


def _int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_duration_hours(value: str) -> float:
    """Turn an ISO 8601 period such as ``PT40H0M0S`` into hours."""
    if not value:
        return 0.0
    match = _DURATION_PATTERN.match(value.strip())
    if not match:
        return 0.0
    parts = match.groupdict()
    # A bare "D" component in MSPDI means whole days of *elapsed* time; Project
    # itself writes hours, so days here are converted at 24h only when present.
    hours = float(parts["hours"] or 0)
    hours += float(parts["minutes"] or 0) / 60
    hours += float(parts["seconds"] or 0) / 3600
    hours += float(parts["days"] or 0) * 24
    return hours


def format_duration_hours(hours: float) -> str:
    """Render hours as the ISO 8601 period Project expects."""
    total_seconds = round(max(0.0, hours) * 3600)
    whole_hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"PT{whole_hours}H{minutes}M{seconds}S"


def _parse_datetime(value: str) -> date | None:
    if not value:
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _format_datetime(value: date | None, *, end_of_day: bool = False) -> str:
    if value is None:
        return ""
    clock = "17:00:00" if end_of_day else "08:00:00"
    return f"{value.isoformat()}T{clock}"


# ── reading ──────────────────────────────────────────────────────────────


def read_mspdi(content: str | bytes) -> ExchangeSchedule:
    """Parse Microsoft Project XML into an :class:`ExchangeSchedule`."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise MSPDIError(f"Not valid XML: {exc}") from exc

    if not root.tag.endswith("Project"):
        raise MSPDIError(
            f"Root element is {root.tag!r}, expected Project; this is not an MSPDI file"
        )

    schedule = ExchangeSchedule(source_format="mspdi")
    schedule.name = _text(root, "Name") or _text(root, "Title") or "Imported Project"
    schedule.code = _text(root, "Subject")
    schedule.start_date = _parse_datetime(_text(root, "StartDate"))
    schedule.finish_date = _parse_datetime(_text(root, "FinishDate"))
    schedule.data_date = _parse_datetime(_text(root, "StatusDate"))

    hours_per_day = _read_calendars(root, schedule)
    _read_tasks(root, schedule, hours_per_day)
    _read_relationships(root, schedule, hours_per_day)
    _read_resources(root, schedule)
    _read_assignments(root, schedule, hours_per_day)

    return schedule


def _read_calendars(root, schedule: ExchangeSchedule) -> float:
    # MSPDI states the working day length on the project, not the calendar.
    minutes_per_day = _float(_text(root, "MinutesPerDay"), 480.0) or 480.0
    minutes_per_week = _float(_text(root, "MinutesPerWeek"), 2400.0) or 2400.0
    hours_per_day = minutes_per_day / 60
    default_uid = _text(root, "CalendarUID")

    calendars_node = _find(root, "Calendars")
    for node in _children(calendars_node, "Calendar"):
        uid = _text(node, "UID")
        if not uid:
            continue

        working: set[int] = set()
        week_days = _find(node, "WeekDays")
        for day_node in _children(week_days, "WeekDay"):
            # MSPDI numbers Sunday=1 .. Saturday=7.
            day_type = _int(_text(day_node, "DayType"), 0)
            if not 1 <= day_type <= 7:
                continue  # 0 means an exception date rather than a weekday
            is_working = _text(day_node, "DayWorking") in ("1", "true")
            if is_working:
                working.add({1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}[day_type])

        calendar = Calendar(
            id=uid,
            name=_text(node, "Name", f"Calendar {uid}"),
            hours_per_day=hours_per_day,
            hours_per_week=minutes_per_week / 60,
            working_weekdays=working or {0, 1, 2, 3, 4},
            is_default=(uid == default_uid),
        )
        schedule.calendars.append(calendar)

    if not schedule.calendars:
        schedule.calendars.append(
            Calendar(
                id="1",
                name="Standard",
                hours_per_day=hours_per_day,
                hours_per_week=minutes_per_week / 60,
                is_default=True,
            )
        )
        schedule.warnings.append("File contained no Calendars; assumed a standard 5-day week")

    default = next((c for c in schedule.calendars if c.is_default), schedule.calendars[0])
    schedule.default_calendar_id = default.id
    return hours_per_day


def _read_tasks(root, schedule: ExchangeSchedule, hours_per_day: float) -> None:
    tasks_node = _find(root, "Tasks")

    for node in _children(tasks_node, "Task"):
        uid = _text(node, "UID")
        # UID 0 is the project summary row, not a real activity.
        if not uid or uid == "0":
            continue

        is_summary = _text(node, "Summary") in ("1", "true")
        is_milestone = _text(node, "Milestone") in ("1", "true")
        duration_hours = parse_duration_hours(_text(node, "Duration"))

        if is_summary:
            kind = ActivityKind.WBS_SUMMARY
        elif is_milestone or duration_hours == 0:
            kind = ActivityKind.FINISH_MILESTONE
        else:
            kind = ActivityKind.TASK

        # Summary rows roll up their children; importing their duration would
        # double-count the work beneath them.
        duration = 0.0 if kind.is_milestone or is_summary else duration_hours / hours_per_day

        remaining_hours = parse_duration_hours(_text(node, "RemainingDuration"))
        constraint = MSPDI_CONSTRAINTS.get(
            _int(_text(node, "ConstraintType"), 0), ConstraintType.NONE
        )

        outline = _text(node, "OutlineNumber")
        if outline and "." in outline:
            wbs_id = outline.rsplit(".", 1)[0]
        else:
            wbs_id = None

        # An Element with no children is falsey, so `if baseline:` is False for
        # a perfectly present <Baseline/> that happens to hold only text nodes.
        # ElementTree deprecated the truthiness test for exactly this ambiguity.
        baseline = _find(node, "Baseline")
        baseline_start = _parse_datetime(_text(baseline, "Start")) if baseline is not None else None
        baseline_finish = (
            _parse_datetime(_text(baseline, "Finish")) if baseline is not None else None
        )

        schedule.activities.append(
            ExchangeActivity(
                id=uid,
                name=_text(node, "Name", "Unnamed activity"),
                code=_text(node, "WBS") or outline,
                duration=duration,
                remaining_duration=(
                    None if not remaining_hours else remaining_hours / hours_per_day
                ),
                kind=kind,
                wbs_id=wbs_id,
                calendar_id=_text(node, "CalendarUID") or schedule.default_calendar_id,
                notes=_text(node, "Notes"),
                early_start=_parse_datetime(_text(node, "EarlyStart"))
                or _parse_datetime(_text(node, "Start")),
                early_finish=_parse_datetime(_text(node, "EarlyFinish"))
                or _parse_datetime(_text(node, "Finish")),
                late_start=_parse_datetime(_text(node, "LateStart")),
                late_finish=_parse_datetime(_text(node, "LateFinish")),
                baseline_start=baseline_start,
                baseline_finish=baseline_finish,
                actual_start=_parse_datetime(_text(node, "ActualStart")),
                actual_finish=_parse_datetime(_text(node, "ActualFinish")),
                percent_complete=_float(_text(node, "PercentComplete"), 0.0) or 0.0,
                constraint_type=constraint,
                constraint_date=_parse_datetime(_text(node, "ConstraintDate")),
                total_float=parse_duration_hours(_text(node, "TotalSlack")) / hours_per_day
                if _text(node, "TotalSlack")
                else None,
                free_float=parse_duration_hours(_text(node, "FreeSlack")) / hours_per_day
                if _text(node, "FreeSlack")
                else None,
                budgeted_cost=_float(_text(node, "Cost")),
                actual_cost=_float(_text(node, "ActualCost")),
            )
        )

        if is_summary and outline:
            schedule.wbs.append(
                WBSNode(
                    id=outline,
                    name=_text(node, "Name", ""),
                    parent_id=outline.rsplit(".", 1)[0] if "." in outline else None,
                    code=_text(node, "WBS"),
                    sequence=_int(_text(node, "ID"), 0),
                )
            )


def _read_relationships(root, schedule: ExchangeSchedule, hours_per_day: float) -> None:
    tasks_node = _find(root, "Tasks")
    known = {a.id for a in schedule.activities}

    for node in _children(tasks_node, "Task"):
        successor = _text(node, "UID")
        if not successor or successor == "0":
            continue

        for link in _children(node, "PredecessorLink"):
            predecessor = _text(link, "PredecessorUID")
            if not predecessor:
                continue
            if predecessor not in known or successor not in known:
                schedule.warnings.append(
                    f"Link {predecessor}->{successor} references a task that was not imported"
                )
                continue

            raw_type = _int(_text(link, "Type"), 1)
            relation = MSPDI_LINK_TYPES.get(raw_type)
            if relation is None:
                relation = RelationType.FS
                schedule.warnings.append(
                    f"Link {predecessor}->{successor} has unrecognised type {raw_type}; "
                    "treated as Finish-to-Start"
                )

            # LinkLag is in tenths of a minute unless LagFormat says otherwise.
            lag_units = _float(_text(link, "LinkLag"), 0.0) or 0.0
            lag_hours = lag_units / 600
            schedule.relationships.append(
                ExchangeRelationship(
                    predecessor_id=predecessor,
                    successor_id=successor,
                    type=relation,
                    lag=lag_hours / hours_per_day,
                )
            )


def _read_resources(root, schedule: ExchangeSchedule) -> None:
    kinds = {0: "material", 1: "labor", 2: "material"}
    resources_node = _find(root, "Resources")

    for node in _children(resources_node, "Resource"):
        uid = _text(node, "UID")
        if not uid or uid == "0":
            continue
        schedule.resources.append(
            ExchangeResource(
                id=uid,
                name=_text(node, "Name", f"Resource {uid}"),
                kind=kinds.get(_int(_text(node, "Type"), 1), "labor"),
                unit=_text(node, "MaterialLabel"),
                standard_rate=_float(_text(node, "StandardRate")),
                calendar_id=_text(node, "CalendarUID") or None,
            )
        )


def _read_assignments(root, schedule: ExchangeSchedule, hours_per_day: float) -> None:
    assignments_node = _find(root, "Assignments")
    known_activities = {a.id for a in schedule.activities}
    known_resources = {r.id for r in schedule.resources}

    for node in _children(assignments_node, "Assignment"):
        activity_id = _text(node, "TaskUID")
        resource_id = _text(node, "ResourceUID")
        if activity_id not in known_activities or resource_id not in known_resources:
            continue
        schedule.assignments.append(
            ExchangeAssignment(
                activity_id=activity_id,
                resource_id=resource_id,
                units=_float(_text(node, "Units"), 1.0) or 1.0,
                budgeted_cost=_float(_text(node, "Cost")),
                actual_cost=_float(_text(node, "ActualCost")),
                budgeted_hours=parse_duration_hours(_text(node, "Work")) or None,
            )
        )


# ── writing ──────────────────────────────────────────────────────────────


def write_mspdi(schedule: ExchangeSchedule, *, exported_at: datetime | None = None) -> str:
    """Serialise to Microsoft Project XML.

    The output opens in Microsoft Project without a conversion prompt. This is
    the export path for Microsoft users, because ``.mpp`` cannot be written.
    """
    calendar = schedule.default_calendar or Calendar(id="1", name="Standard", is_default=True)
    hours_per_day = calendar.hours_per_day

    ET.register_namespace("", MSPDI_NS)
    root = ET.Element(_tag("Project"))

    def add(parent, name: str, value) -> None:
        if value is None or value == "":
            return
        ET.SubElement(parent, _tag(name)).text = str(value)

    add(root, "SaveVersion", "14")
    add(root, "Name", schedule.name)
    add(root, "Title", schedule.name)
    add(root, "Subject", schedule.code)
    add(root, "CreationDate", _format_datetime((exported_at or datetime.now()).date()))
    add(root, "StartDate", _format_datetime(schedule.start_date))
    add(root, "FinishDate", _format_datetime(schedule.finish_date, end_of_day=True))
    add(root, "StatusDate", _format_datetime(schedule.data_date))
    add(root, "CalendarUID", calendar.id)
    add(root, "ScheduleFromStart", "1")
    add(root, "MinutesPerDay", int(hours_per_day * 60))
    add(root, "MinutesPerWeek", int(calendar.hours_per_week * 60))
    add(root, "DaysPerMonth", "20")
    add(root, "DurationFormat", "7")  # days
    add(root, "WorkFormat", "2")  # hours

    # Calendars
    calendars_node = ET.SubElement(root, _tag("Calendars"))
    for entry in schedule.calendars or [calendar]:
        node = ET.SubElement(calendars_node, _tag("Calendar"))
        add(node, "UID", entry.id)
        add(node, "Name", entry.name)
        add(node, "IsBaseCalendar", "1")
        add(node, "BaseCalendarUID", "-1")
        week_days = ET.SubElement(node, _tag("WeekDays"))
        python_to_mspdi = {6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7}
        for python_day in range(7):
            day = ET.SubElement(week_days, _tag("WeekDay"))
            add(day, "DayType", python_to_mspdi[python_day])
            working = python_day in entry.working_weekdays
            add(day, "DayWorking", "1" if working else "0")
            if working:
                times = ET.SubElement(day, _tag("WorkingTimes"))
                period = ET.SubElement(times, _tag("WorkingTime"))
                add(period, "FromTime", "08:00:00")
                finish_hour = min(8 + int(entry.hours_per_day), 23)
                add(period, "ToTime", f"{finish_hour:02d}:00:00")

    # Tasks
    tasks_node = ET.SubElement(root, _tag("Tasks"))
    for index, activity in enumerate(schedule.activities, start=1):
        node = ET.SubElement(tasks_node, _tag("Task"))
        # UID is the stable key links point at; ID is display order. They are
        # not interchangeable.
        add(node, "UID", activity.id)
        add(node, "ID", index)
        add(node, "Name", activity.name)
        add(node, "Active", "1")
        add(node, "Type", "1")  # fixed duration
        add(node, "OutlineLevel", "1")
        add(node, "WBS", activity.code or activity.id)
        add(node, "Summary", "1" if activity.kind is ActivityKind.WBS_SUMMARY else "0")
        add(node, "Milestone", "1" if activity.kind.is_milestone else "0")
        add(node, "Duration", format_duration_hours(activity.duration * hours_per_day))
        add(node, "DurationFormat", "7")
        if activity.remaining_duration is not None:
            add(
                node,
                "RemainingDuration",
                format_duration_hours(activity.remaining_duration * hours_per_day),
            )
        add(node, "Start", _format_datetime(activity.early_start))
        add(node, "Finish", _format_datetime(activity.early_finish, end_of_day=True))
        add(node, "EarlyStart", _format_datetime(activity.early_start))
        add(node, "EarlyFinish", _format_datetime(activity.early_finish, end_of_day=True))
        add(node, "LateStart", _format_datetime(activity.late_start))
        add(node, "LateFinish", _format_datetime(activity.late_finish, end_of_day=True))
        add(node, "ActualStart", _format_datetime(activity.actual_start))
        add(node, "ActualFinish", _format_datetime(activity.actual_finish, end_of_day=True))
        add(node, "PercentComplete", int(activity.percent_complete))
        add(node, "ConstraintType", CONSTRAINTS_TO_MSPDI.get(activity.constraint_type, 0))
        add(node, "ConstraintDate", _format_datetime(activity.constraint_date))
        add(node, "CalendarUID", activity.calendar_id or calendar.id)
        add(node, "Notes", activity.notes)
        if activity.total_float is not None:
            add(node, "TotalSlack", format_duration_hours(activity.total_float * hours_per_day))
        if activity.free_float is not None:
            add(node, "FreeSlack", format_duration_hours(activity.free_float * hours_per_day))
        if activity.budgeted_cost is not None:
            add(node, "Cost", f"{activity.budgeted_cost:g}")
        if activity.actual_cost is not None:
            add(node, "ActualCost", f"{activity.actual_cost:g}")
        if activity.baseline_start or activity.baseline_finish:
            baseline = ET.SubElement(node, _tag("Baseline"))
            add(baseline, "Number", "0")
            add(baseline, "Start", _format_datetime(activity.baseline_start))
            add(baseline, "Finish", _format_datetime(activity.baseline_finish, end_of_day=True))

        for link in schedule.relationships:
            if link.successor_id != activity.id:
                continue
            link_node = ET.SubElement(node, _tag("PredecessorLink"))
            add(link_node, "PredecessorUID", link.predecessor_id)
            add(link_node, "Type", LINK_TYPES_TO_MSPDI[link.type])
            add(link_node, "CrossProject", "0")
            # Tenths of a minute, which is how Project stores lag.
            add(link_node, "LinkLag", int(round(link.lag * hours_per_day * 600)))
            add(link_node, "LagFormat", "7")

    if schedule.resources:
        resources_node = ET.SubElement(root, _tag("Resources"))
        kinds = {"labor": 1, "material": 0, "equipment": 1}
        for resource in schedule.resources:
            node = ET.SubElement(resources_node, _tag("Resource"))
            add(node, "UID", resource.id)
            add(node, "Name", resource.name)
            add(node, "Type", kinds.get(resource.kind, 1))
            add(node, "MaterialLabel", resource.unit)
            if resource.standard_rate is not None:
                add(node, "StandardRate", f"{resource.standard_rate:g}")

    if schedule.assignments:
        assignments_node = ET.SubElement(root, _tag("Assignments"))
        for index, assignment in enumerate(schedule.assignments, start=1):
            node = ET.SubElement(assignments_node, _tag("Assignment"))
            add(node, "UID", index)
            add(node, "TaskUID", assignment.activity_id)
            add(node, "ResourceUID", assignment.resource_id)
            add(node, "Units", f"{assignment.units:g}")
            if assignment.budgeted_cost is not None:
                add(node, "Cost", f"{assignment.budgeted_cost:g}")
            if assignment.budgeted_hours is not None:
                add(node, "Work", format_duration_hours(assignment.budgeted_hours))

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
