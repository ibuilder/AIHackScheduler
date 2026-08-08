"""Reading and writing Primavera P6 XER files.

XER is a tab-delimited text format. Each table is introduced by ``%T``, its
column names by ``%F``, and each row by ``%R``::

    ERMHDR	19.12	2026-08-08	Project	admin	...
    %T	PROJECT
    %F	proj_id	proj_short_name	plan_start_date
    %R	1	NGT-2026	2026-09-07 00:00
    %T	TASK
    ...
    %E

The tokenizer is the easy part. What makes an importer right or wrong is the
field mapping, and there are four traps worth naming because a previous
implementation in this project fell into all of them:

* **Relationship types are prefixed.** P6 writes ``PR_FS``, ``PR_SS``,
  ``PR_FF``, ``PR_SF``. Storing the raw string and later failing to parse it
  silently turns every SS/FF/SF tie into FS, which changes the critical path
  without any error being raised.
* **Durations are hours against a calendar.** They are not always eight-hour
  days. The CALENDAR table carries ``day_hr_cnt``; ignoring it rescales every
  duration in the schedule.
* **Milestones have zero duration.** Clamping with ``max(1, ...)`` turns them
  into one-day tasks and changes the logic network.
* **Costs and notes live in other tables.** ``TASK`` has no ``target_cost``;
  costs are in ``TASKRSRC`` and notes in ``TASKMEMO``. Reading them from
  ``TASK`` silently yields zero.
"""

from __future__ import annotations

import math
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

# P6 prefixes its relationship types. Mapping them by hand rather than by
# string-slicing keeps an unexpected value loud instead of silently wrong.
XER_RELATION_TYPES = {
    "PR_FS": RelationType.FS,
    "PR_SS": RelationType.SS,
    "PR_FF": RelationType.FF,
    "PR_SF": RelationType.SF,
}
RELATION_TYPES_TO_XER = {value: key for key, value in XER_RELATION_TYPES.items()}

XER_ACTIVITY_KINDS = {
    "TT_Task": ActivityKind.TASK,
    "TT_Rsrc": ActivityKind.TASK,
    "TT_Mile": ActivityKind.START_MILESTONE,
    "TT_FinMile": ActivityKind.FINISH_MILESTONE,
    "TT_LOE": ActivityKind.LEVEL_OF_EFFORT,
    "TT_WBS": ActivityKind.WBS_SUMMARY,
}
ACTIVITY_KINDS_TO_XER = {
    ActivityKind.TASK: "TT_Task",
    ActivityKind.START_MILESTONE: "TT_Mile",
    ActivityKind.FINISH_MILESTONE: "TT_FinMile",
    ActivityKind.LEVEL_OF_EFFORT: "TT_LOE",
    ActivityKind.WBS_SUMMARY: "TT_WBS",
}

XER_CONSTRAINTS = {
    "": ConstraintType.NONE,
    "CS_ALAP": ConstraintType.AS_LATE_AS_POSSIBLE,
    "CS_MEO": ConstraintType.FINISH_ON,
    "CS_MEOA": ConstraintType.FINISH_ON_OR_AFTER,
    "CS_MEOB": ConstraintType.FINISH_ON_OR_BEFORE,
    "CS_MSO": ConstraintType.START_ON,
    "CS_MSOA": ConstraintType.START_ON_OR_AFTER,
    "CS_MSOB": ConstraintType.START_ON_OR_BEFORE,
    "CS_MANDFIN": ConstraintType.MANDATORY_FINISH,
    "CS_MANDSTART": ConstraintType.MANDATORY_START,
}
CONSTRAINTS_TO_XER = {value: key for key, value in XER_CONSTRAINTS.items() if key}

DEFAULT_HOURS_PER_DAY = 8.0


class XERError(ValueError):
    """The file could not be read as XER."""


# ── tokenizer ────────────────────────────────────────────────────────────


def parse_tables(content: str) -> dict[str, list[dict[str, str]]]:
    """Split XER text into ``{table_name: [row_dict, ...]}``.

    Rows with a different column count from the header are padded or trimmed
    rather than discarded — P6 exports occasionally carry a trailing empty
    field, and losing a whole activity over that would be worse.
    """
    tables: dict[str, list[dict[str, str]]] = {}
    current: str | None = None
    headers: list[str] = []

    for raw_line in content.splitlines():
        if not raw_line:
            continue
        # Only strip the line ending: leading spaces can be significant inside
        # a field, and rstrip('\n') alone leaves a stray '\r' on CRLF files.
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue

        parts = line.split("\t")
        marker = parts[0]

        if marker == "%T":
            current = parts[1] if len(parts) > 1 else None
            headers = []
            if current:
                tables.setdefault(current, [])
        elif marker == "%F":
            headers = parts[1:]
        elif marker == "%R":
            if not current or not headers:
                continue
            values = parts[1:]
            if len(values) < len(headers):
                values += [""] * (len(headers) - len(values))
            elif len(values) > len(headers):
                values = values[: len(headers)]
            tables[current].append(dict(zip(headers, values, strict=True)))
        elif marker == "%E":
            current = None
            headers = []

    return tables


def _parse_date(value: str | None) -> date | None:
    """P6 writes ``YYYY-MM-DD HH:MM``; tolerate a few near neighbours."""
    if not value or not value.strip():
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None or not str(value).strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_date(value: date | None) -> str:
    return (
        ""
        if value is None
        else value.strftime("%Y-%m-%d %H:%M")
        if isinstance(value, datetime)
        else value.strftime("%Y-%m-%d 00:00")
    )


# ── reading ──────────────────────────────────────────────────────────────


def read_xer(content: str) -> ExchangeSchedule:
    """Parse XER text into an :class:`ExchangeSchedule`."""
    if "%T" not in content:
        raise XERError("No %T table marker found; this does not look like an XER file")

    tables = parse_tables(content)
    schedule = ExchangeSchedule(source_format="xer")

    calendars = _read_calendars(tables, schedule)
    default_hours = (
        schedule.default_calendar.hours_per_day
        if schedule.default_calendar
        else DEFAULT_HOURS_PER_DAY
    )

    _read_project(tables, schedule)
    _read_wbs(tables, schedule)
    _read_activities(tables, schedule, calendars, default_hours)
    _read_relationships(tables, schedule, calendars, default_hours)
    _read_resources(tables, schedule)
    _read_assignments(tables, schedule, default_hours)

    for table in tables:
        if table not in _HANDLED_TABLES:
            schedule.warnings.append(f"Table {table} was present but not imported")

    return schedule


_HANDLED_TABLES = {
    "CURRTYPE",
    "PROJECT",
    "CALENDAR",
    "PROJWBS",
    "TASK",
    "TASKPRED",
    "RSRC",
    "TASKRSRC",
    "TASKMEMO",
    "MEMOTYPE",
    "PROJPROP",
    "SCHEDOPTIONS",
    "UDFTYPE",
    "UDFVALUE",
    "OBS",
    "ROLES",
    "ACCOUNT",
}


def _read_calendars(tables, schedule: ExchangeSchedule) -> dict[str, Calendar]:
    calendars: dict[str, Calendar] = {}

    for row in tables.get("CALENDAR", []):
        calendar_id = row.get("clndr_id", "")
        if not calendar_id:
            continue

        # day_hr_cnt is what makes an hours-to-days conversion correct. When
        # absent, fall back to eight and say so rather than assuming silently.
        hours_per_day = _parse_float(row.get("day_hr_cnt"))
        if hours_per_day is None or hours_per_day <= 0:
            hours_per_day = DEFAULT_HOURS_PER_DAY
            schedule.warnings.append(
                f"Calendar {row.get('clndr_name', calendar_id)!r} has no day_hr_cnt; "
                f"assuming {DEFAULT_HOURS_PER_DAY} hours per day"
            )

        week_hours = _parse_float(row.get("week_hr_cnt")) or hours_per_day * 5
        working_weekdays, exceptions = _parse_calendar_data(row.get("clndr_data", ""))

        calendar = Calendar(
            id=calendar_id,
            name=row.get("clndr_name", f"Calendar {calendar_id}"),
            hours_per_day=hours_per_day,
            hours_per_week=week_hours,
            working_weekdays=working_weekdays,
            exceptions=exceptions,
            is_default=row.get("default_flag", "").upper() == "Y",
        )
        calendars[calendar_id] = calendar
        schedule.calendars.append(calendar)

    if not calendars:
        fallback = Calendar(
            id="default",
            name="Standard 5-day",
            hours_per_day=DEFAULT_HOURS_PER_DAY,
            is_default=True,
        )
        calendars["default"] = fallback
        schedule.calendars.append(fallback)
        schedule.warnings.append("File contained no CALENDAR table; assumed a standard 5-day week")

    default = next((c for c in schedule.calendars if c.is_default), schedule.calendars[0])
    schedule.default_calendar_id = default.id
    return calendars


def _parse_calendar_data(blob: str) -> tuple[set[int], list]:
    """Extract the working weekdays from P6's packed calendar string.

    The format is a nested ``(0||N()...)`` structure where N is 1 for Sunday
    through 7 for Saturday, and a day with no work hours listed is non-working.
    Only the weekly pattern is read; individual holiday exceptions are left for
    a later pass rather than guessed at.
    """
    if not blob or "DaysOfWeek" not in blob:
        return {0, 1, 2, 3, 4}, []

    working: set[int] = set()
    # P6 numbers Sunday=1 .. Saturday=7; Python numbers Monday=0 .. Sunday=6.
    p6_to_python = {1: 6, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

    section = blob.split("DaysOfWeek", 1)[1]
    for p6_day, python_day in p6_to_python.items():
        block = _day_block(section, p6_day)
        # A working day lists at least one shift, e.g. "(2()(s|08:00|f|16:00))";
        # a non-working day is just "(2())". The block has to be delimited by
        # matching parentheses rather than a fixed window, because the days run
        # together and a fixed window reads into the next day's shift.
        if block and "s|" in block:
            working.add(python_day)

    if not working:
        working = {0, 1, 2, 3, 4}

    return working, []


def _day_block(section: str, p6_day: int) -> str:
    """The parenthesised block for one day, delimited by matching brackets."""
    marker = f"({p6_day}("
    start = section.find(marker)
    if start == -1:
        return ""

    depth = 0
    for index in range(start, len(section)):
        char = section[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return section[start : index + 1]
    return ""


def _read_project(tables, schedule: ExchangeSchedule) -> None:
    rows = tables.get("PROJECT", [])
    if not rows:
        schedule.warnings.append("File contained no PROJECT table")
        return

    row = rows[0]
    if len(rows) > 1:
        schedule.warnings.append(
            f"File contains {len(rows)} projects; imported the first ({row.get('proj_short_name')})"
        )

    # proj_short_name is the project code. There is no proj_name column on
    # PROJECT — the long name lives on the root PROJWBS node, picked up later.
    schedule.code = row.get("proj_short_name", "")
    schedule.name = row.get("proj_short_name") or "Imported Project"
    schedule.start_date = _parse_date(row.get("plan_start_date"))
    schedule.finish_date = _parse_date(row.get("plan_end_date")) or _parse_date(
        row.get("scd_end_date")
    )
    schedule.data_date = _parse_date(row.get("last_recalc_date"))

    calendar_id = row.get("clndr_id")
    if calendar_id and schedule.calendar(calendar_id):
        schedule.default_calendar_id = calendar_id


def _read_wbs(tables, schedule: ExchangeSchedule) -> None:
    rows = tables.get("PROJWBS", [])
    root_name = None

    for row in rows:
        wbs_id = row.get("wbs_id", "")
        if not wbs_id:
            continue
        parent = row.get("parent_wbs_id") or None
        node = WBSNode(
            id=wbs_id,
            name=row.get("wbs_name", ""),
            parent_id=parent,
            code=row.get("wbs_short_name", ""),
            sequence=int(_parse_float(row.get("seq_num")) or 0),
        )
        schedule.wbs.append(node)
        # The root node carries the project's long name, which PROJECT lacks.
        if row.get("proj_node_flag", "").upper() == "Y":
            root_name = node.name

    if root_name:
        schedule.name = root_name


def _read_activities(tables, schedule, calendars, default_hours) -> None:
    for row in tables.get("TASK", []):
        task_id = row.get("task_id", "")
        if not task_id:
            continue

        raw_kind = row.get("task_type", "TT_Task")
        kind = XER_ACTIVITY_KINDS.get(raw_kind)
        if kind is None:
            kind = ActivityKind.TASK
            schedule.warnings.append(
                f"Activity {row.get('task_code', task_id)} has unrecognised type "
                f"{raw_kind!r}; treated as a task"
            )

        calendar_id = row.get("clndr_id") or schedule.default_calendar_id
        calendar = calendars.get(calendar_id)
        hours_per_day = calendar.hours_per_day if calendar else default_hours

        target_hours = _parse_float(row.get("target_drtn_hr_cnt")) or 0.0
        remaining_hours = _parse_float(row.get("remain_drtn_hr_cnt"))

        # Milestones are zero-duration by definition. Preserving that matters:
        # rounding them up to a day changes every downstream date.
        duration = 0.0 if kind.is_milestone else target_hours / hours_per_day

        constraint_raw = row.get("cstr_type", "")
        constraint = XER_CONSTRAINTS.get(constraint_raw)
        if constraint is None:
            constraint = ConstraintType.NONE
            schedule.warnings.append(
                f"Activity {row.get('task_code', task_id)} has unrecognised constraint "
                f"{constraint_raw!r}; ignored"
            )

        percent = _parse_float(row.get("phys_complete_pct")) or 0.0
        if not percent and target_hours and remaining_hours is not None:
            percent = max(0.0, min(100.0, (target_hours - remaining_hours) / target_hours * 100))

        schedule.activities.append(
            ExchangeActivity(
                id=task_id,
                name=row.get("task_name", "Unnamed activity"),
                code=row.get("task_code", ""),
                duration=duration,
                remaining_duration=(
                    None if remaining_hours is None else remaining_hours / hours_per_day
                ),
                kind=kind,
                wbs_id=row.get("wbs_id") or None,
                calendar_id=calendar_id,
                early_start=_parse_date(row.get("early_start_date")),
                early_finish=_parse_date(row.get("early_end_date")),
                late_start=_parse_date(row.get("late_start_date")),
                late_finish=_parse_date(row.get("late_end_date")),
                baseline_start=_parse_date(row.get("target_start_date")),
                baseline_finish=_parse_date(row.get("target_end_date")),
                actual_start=_parse_date(row.get("act_start_date")),
                actual_finish=_parse_date(row.get("act_end_date")),
                percent_complete=percent,
                constraint_type=constraint,
                constraint_date=_parse_date(row.get("cstr_date")),
                total_float=(
                    None
                    if _parse_float(row.get("total_float_hr_cnt")) is None
                    else _parse_float(row.get("total_float_hr_cnt")) / hours_per_day
                ),
                free_float=(
                    None
                    if _parse_float(row.get("free_float_hr_cnt")) is None
                    else _parse_float(row.get("free_float_hr_cnt")) / hours_per_day
                ),
            )
        )

    # Notes live in TASKMEMO, not on TASK.
    notes: dict[str, list[str]] = {}
    for row in tables.get("TASKMEMO", []):
        task_id = row.get("task_id")
        text = (row.get("task_memo") or "").strip()
        if task_id and text:
            notes.setdefault(task_id, []).append(text)
    for activity in schedule.activities:
        if activity.id in notes:
            activity.notes = "\n\n".join(notes[activity.id])


def _read_relationships(tables, schedule, calendars, default_hours) -> None:
    for row in tables.get("TASKPRED", []):
        predecessor = row.get("pred_task_id")
        successor = row.get("task_id")
        if not predecessor or not successor:
            continue

        raw_type = row.get("pred_type", "PR_FS")
        relation = XER_RELATION_TYPES.get(raw_type)
        if relation is None:
            relation = RelationType.FS
            schedule.warnings.append(
                f"Relationship {predecessor}->{successor} has unrecognised type "
                f"{raw_type!r}; treated as Finish-to-Start"
            )

        # Lag is in hours against the successor's calendar.
        successor_activity = next((a for a in schedule.activities if a.id == successor), None)
        calendar = calendars.get(successor_activity.calendar_id) if successor_activity else None
        hours_per_day = calendar.hours_per_day if calendar else default_hours
        lag_hours = _parse_float(row.get("lag_hr_cnt")) or 0.0

        schedule.relationships.append(
            ExchangeRelationship(
                predecessor_id=predecessor,
                successor_id=successor,
                type=relation,
                lag=lag_hours / hours_per_day,
            )
        )


def _read_resources(tables, schedule: ExchangeSchedule) -> None:
    kinds = {"RT_Labor": "labor", "RT_Mat": "material", "RT_Equip": "equipment"}
    for row in tables.get("RSRC", []):
        resource_id = row.get("rsrc_id")
        if not resource_id:
            continue
        schedule.resources.append(
            ExchangeResource(
                id=resource_id,
                name=row.get("rsrc_name", row.get("rsrc_short_name", "Unnamed resource")),
                kind=kinds.get(row.get("rsrc_type", "RT_Labor"), "labor"),
                unit=row.get("unit_of_measure", ""),
                max_units_per_day=_parse_float(row.get("def_qty_per_hr")),
                calendar_id=row.get("clndr_id") or None,
            )
        )


def _read_assignments(tables, schedule: ExchangeSchedule, default_hours: float) -> None:
    """Costs live here, on TASKRSRC — not on TASK."""
    costs: dict[str, dict[str, float]] = {}

    for row in tables.get("TASKRSRC", []):
        task_id = row.get("task_id")
        resource_id = row.get("rsrc_id")
        if not task_id:
            continue

        budgeted = _parse_float(row.get("target_cost")) or 0.0
        actual = _parse_float(row.get("act_reg_cost")) or 0.0
        actual += _parse_float(row.get("act_ot_cost")) or 0.0

        bucket = costs.setdefault(task_id, {"budgeted": 0.0, "actual": 0.0})
        bucket["budgeted"] += budgeted
        bucket["actual"] += actual

        if resource_id:
            schedule.assignments.append(
                ExchangeAssignment(
                    activity_id=task_id,
                    resource_id=resource_id,
                    units=_parse_float(row.get("target_qty")) or 1.0,
                    budgeted_cost=budgeted,
                    actual_cost=actual,
                    budgeted_hours=_parse_float(row.get("target_qty")),
                )
            )

    for activity in schedule.activities:
        if activity.id in costs:
            activity.budgeted_cost = costs[activity.id]["budgeted"]
            activity.actual_cost = costs[activity.id]["actual"]


# ── writing ──────────────────────────────────────────────────────────────


def _table(name: str, columns: list[str], rows: list[list[str]]) -> list[str]:
    lines = [f"%T\t{name}", "%F\t" + "\t".join(columns)]
    lines += ["%R\t" + "\t".join("" if v is None else str(v) for v in row) for row in rows]
    return lines


def write_xer(schedule: ExchangeSchedule, *, exported_at: datetime | None = None) -> str:
    """Serialise an :class:`ExchangeSchedule` back to XER text.

    Written so that :func:`read_xer` recovers the same schedule — the round
    trip is what the tests assert, because a writer nobody reads back is a
    writer nobody can trust.
    """
    stamp = exported_at or datetime.now()
    lines: list[str] = [
        "\t".join(
            [
                "ERMHDR",
                "19.12",
                stamp.strftime("%Y-%m-%d"),
                "Project",
                "BBSchedule",
                "BBSchedule",
                "",
                "Project Management",
                "USD",
            ]
        )
    ]

    calendars = schedule.calendars or [Calendar(id="default", name="Standard", is_default=True)]
    default_calendar = schedule.default_calendar or calendars[0]

    lines += _table(
        "CALENDAR",
        ["clndr_id", "clndr_name", "day_hr_cnt", "week_hr_cnt", "default_flag", "clndr_data"],
        [
            [
                c.id,
                c.name,
                f"{c.hours_per_day:g}",
                f"{c.hours_per_week:g}",
                "Y" if c.is_default else "N",
                _write_calendar_data(c),
            ]
            for c in calendars
        ],
    )

    lines += _table(
        "PROJECT",
        [
            "proj_id",
            "proj_short_name",
            "plan_start_date",
            "plan_end_date",
            "last_recalc_date",
            "clndr_id",
        ],
        [
            [
                "1",
                schedule.code or schedule.name[:20],
                _format_date(schedule.start_date),
                _format_date(schedule.finish_date),
                _format_date(schedule.data_date),
                default_calendar.id,
            ]
        ],
    )

    wbs_rows = [
        [n.id, "1", n.parent_id or "", n.code, n.name, str(n.sequence), "N"] for n in schedule.wbs
    ]
    if not wbs_rows:
        # A root node carries the project's long name, which PROJECT cannot.
        wbs_rows = [["1", "1", "", schedule.code or "ROOT", schedule.name, "0", "Y"]]
    else:
        wbs_rows[0][6] = "Y"
    lines += _table(
        "PROJWBS",
        [
            "wbs_id",
            "proj_id",
            "parent_wbs_id",
            "wbs_short_name",
            "wbs_name",
            "seq_num",
            "proj_node_flag",
        ],
        wbs_rows,
    )

    root_wbs = wbs_rows[0][0]
    task_rows = []
    for activity in schedule.activities:
        calendar = schedule.calendar_for(activity) or default_calendar
        hours = calendar.hours_per_day
        remaining = (
            activity.remaining_duration
            if activity.remaining_duration is not None
            else activity.duration
        )
        task_rows.append(
            [
                activity.id,
                "1",
                activity.wbs_id or root_wbs,
                activity.calendar_id or default_calendar.id,
                activity.code or activity.id,
                activity.name,
                ACTIVITY_KINDS_TO_XER.get(activity.kind, "TT_Task"),
                f"{activity.duration * hours:g}",
                f"{remaining * hours:g}",
                _format_date(activity.early_start),
                _format_date(activity.early_finish),
                _format_date(activity.late_start),
                _format_date(activity.late_finish),
                _format_date(activity.baseline_start),
                _format_date(activity.baseline_finish),
                _format_date(activity.actual_start),
                _format_date(activity.actual_finish),
                f"{activity.percent_complete:g}",
                CONSTRAINTS_TO_XER.get(activity.constraint_type, ""),
                _format_date(activity.constraint_date),
                "" if activity.total_float is None else f"{activity.total_float * hours:g}",
                "" if activity.free_float is None else f"{activity.free_float * hours:g}",
            ]
        )

    lines += _table(
        "TASK",
        [
            "task_id",
            "proj_id",
            "wbs_id",
            "clndr_id",
            "task_code",
            "task_name",
            "task_type",
            "target_drtn_hr_cnt",
            "remain_drtn_hr_cnt",
            "early_start_date",
            "early_end_date",
            "late_start_date",
            "late_end_date",
            "target_start_date",
            "target_end_date",
            "act_start_date",
            "act_end_date",
            "phys_complete_pct",
            "cstr_type",
            "cstr_date",
            "total_float_hr_cnt",
            "free_float_hr_cnt",
        ],
        task_rows,
    )

    pred_rows = []
    for index, link in enumerate(schedule.relationships, start=1):
        successor = schedule.activity(link.successor_id)
        calendar = schedule.calendar_for(successor) if successor else default_calendar
        hours = (calendar or default_calendar).hours_per_day
        pred_rows.append(
            [
                str(index),
                link.successor_id,
                link.predecessor_id,
                "1",
                "1",
                RELATION_TYPES_TO_XER[link.type],
                f"{link.lag * hours:g}",
            ]
        )
    lines += _table(
        "TASKPRED",
        [
            "task_pred_id",
            "task_id",
            "pred_task_id",
            "proj_id",
            "pred_proj_id",
            "pred_type",
            "lag_hr_cnt",
        ],
        pred_rows,
    )

    if schedule.resources:
        kinds = {"labor": "RT_Labor", "material": "RT_Mat", "equipment": "RT_Equip"}
        lines += _table(
            "RSRC",
            ["rsrc_id", "rsrc_name", "rsrc_short_name", "rsrc_type", "unit_of_measure", "clndr_id"],
            [
                [
                    r.id,
                    r.name,
                    r.name[:20],
                    kinds.get(r.kind, "RT_Labor"),
                    r.unit,
                    r.calendar_id or default_calendar.id,
                ]
                for r in schedule.resources
            ],
        )

    if schedule.assignments:
        lines += _table(
            "TASKRSRC",
            [
                "taskrsrc_id",
                "task_id",
                "rsrc_id",
                "proj_id",
                "target_qty",
                "target_cost",
                "act_reg_cost",
            ],
            [
                [
                    str(index),
                    a.activity_id,
                    a.resource_id,
                    "1",
                    f"{a.units:g}",
                    "" if a.budgeted_cost is None else f"{a.budgeted_cost:g}",
                    "" if a.actual_cost is None else f"{a.actual_cost:g}",
                ]
                for index, a in enumerate(schedule.assignments, start=1)
            ],
        )

    notes = [(a.id, a.notes) for a in schedule.activities if a.notes]
    if notes:
        lines += _table(
            "TASKMEMO",
            ["memo_id", "task_id", "proj_id", "memo_type_id", "task_memo"],
            [
                [str(index), task_id, "1", "1", text.replace("\t", " ").replace("\n", " ")]
                for index, (task_id, text) in enumerate(notes, start=1)
            ],
        )

    lines.append("%E")
    return "\n".join(lines) + "\n"


def _write_calendar_data(calendar: Calendar) -> str:
    """Emit the packed weekly pattern P6 expects."""
    python_to_p6 = {6: 1, 0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 7}
    shift_hours = calendar.hours_per_day
    finish = 8 + int(shift_hours)
    parts = []
    for python_day in range(7):
        p6_day = python_to_p6[python_day]
        if python_day in calendar.working_weekdays:
            parts.append(f"({p6_day}()(s|08:00|f|{min(finish, 23):02d}:00))")
        else:
            parts.append(f"({p6_day}())")
    return "(0||CalendarData()(DaysOfWeek()" + "".join(parts) + "))"


def duration_days(hours: float | None, calendar: Calendar | None) -> float:
    """Public helper: hours to days against a calendar, rounded up to a day."""
    if not hours:
        return 0.0
    per_day = calendar.hours_per_day if calendar else DEFAULT_HOURS_PER_DAY
    return math.ceil(hours / per_day * 100) / 100
