"""Importing and exporting schedules against the database.

The file formats live in :mod:`core.xer` and :mod:`core.mspdi` and know nothing
about SQLAlchemy. This module is the bridge in both directions, plus format
detection and the optional MPXJ path for reading binary ``.mpp``.

What can and cannot be done per format:

===========  ======  ======  ==========================================
Format       Read    Write   Notes
===========  ======  ======  ==========================================
``.xer``     yes     yes     Native, no external dependency
``.xml``     yes     yes     MSPDI — the writable Microsoft format
``.mpp``     yes     **no**  Read needs MPXJ and a JVM. Nobody can write
                             the binary format; export MSPDI instead and
                             open it in Project.
===========  ======  ======  ==========================================
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.calendar import WorkCalendar
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
)
from core.mspdi import MSPDIError, read_mspdi, write_mspdi
from core.xer import XERError, read_xer, write_xer
from extensions import db
from models import (
    Project,
    Resource,
    ResourceAssignment,
    ScheduleType,
    Task,
    TaskDependency,
    TaskStatus,
)
from services.optional import IntegrationUnavailable, require

READABLE = (".xer", ".xml", ".mpp")
WRITABLE = (".xer", ".xml")

# .mpp is deliberately absent from WRITABLE. See the module docstring.
EXPORT_FORMATS = {
    "xer": {"extension": ".xer", "label": "Primavera P6 (XER)"},
    "mspdi": {"extension": ".xml", "label": "Microsoft Project XML (MSPDI)"},
}


class ImportError_(ValueError):
    """A schedule file could not be imported."""


def detect_format(filename: str) -> str:
    """Map a filename to a reader key, by extension."""
    lowered = (filename or "").lower()
    if lowered.endswith(".xer"):
        return "xer"
    if lowered.endswith(".xml"):
        return "mspdi"
    if lowered.endswith(".mpp"):
        return "mpp"
    raise ImportError_(
        f"Unsupported file type {filename!r}. Readable formats: {', '.join(READABLE)}"
    )


# ── reading files ────────────────────────────────────────────────────────


def read_schedule_file(data: bytes, filename: str) -> ExchangeSchedule:
    """Parse an uploaded file into an :class:`ExchangeSchedule`."""
    kind = detect_format(filename)

    if kind == "mpp":
        return read_mpp(data, filename)

    # XER is usually windows-1252; MSPDI declares its own encoding but is
    # almost always UTF-8. Decode leniently rather than rejecting a schedule
    # over one stray byte in a task name.
    for encoding in ("utf-8-sig", "utf-8", "windows-1252", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 decodes any byte sequence
        raise ImportError_("Could not decode the file as text")

    try:
        if kind == "xer":
            return read_xer(text)
        return read_mspdi(text)
    except (XERError, MSPDIError) as exc:
        raise ImportError_(str(exc)) from exc


def read_mpp(data: bytes, filename: str) -> ExchangeSchedule:
    """Read a binary ``.mpp`` via MPXJ.

    MPXJ is a Java library reached through JPype, so this needs a JVM. It is
    optional: without it the application still reads and writes XER and MSPDI,
    and this raises a clear message rather than failing obscurely.
    """
    import tempfile
    from pathlib import Path

    mpxj = require("mpxj", feature="MS Project .mpp reading")
    jpype = require("jpype", feature="MS Project .mpp reading")

    if not jpype.isJVMStarted():  # pragma: no cover - needs a JVM
        mpxj.initialize()

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / (filename or "schedule.mpp")
        path.write_bytes(data)

        from net.sf.mpxj.reader import UniversalProjectReader  # noqa: E402

        project = UniversalProjectReader().read(str(path))
        if project is None:
            raise ImportError_("MPXJ could not read this file as a Microsoft Project schedule")
        return _from_mpxj(project, filename)


def _from_mpxj(project, filename: str) -> ExchangeSchedule:  # pragma: no cover - needs a JVM
    """Translate an MPXJ ProjectFile into the neutral model."""
    schedule = ExchangeSchedule(source_format="mpp")
    properties = project.getProjectProperties()
    schedule.name = str(properties.getName() or filename or "Imported Project")

    minutes_per_day = properties.getMinutesPerDay()
    hours_per_day = float(minutes_per_day) / 60 if minutes_per_day else 8.0
    calendar = Calendar(id="1", name="Standard", hours_per_day=hours_per_day, is_default=True)
    schedule.calendars.append(calendar)
    schedule.default_calendar_id = calendar.id

    link_types = {
        "FINISH_START": RelationType.FS,
        "START_START": RelationType.SS,
        "FINISH_FINISH": RelationType.FF,
        "START_FINISH": RelationType.SF,
    }

    def as_date(value):
        return (
            None
            if value is None
            else date(value.getYear(), value.getMonthValue(), value.getDayOfMonth())
        )

    for task in project.getTasks():
        uid = task.getUniqueID()
        if uid is None or int(uid) == 0:
            continue
        duration = task.getDuration()
        hours = float(duration.getDuration()) if duration else 0.0
        is_milestone = bool(task.getMilestone())

        schedule.activities.append(
            ExchangeActivity(
                id=str(uid),
                name=str(task.getName() or "Unnamed activity"),
                duration=0.0 if is_milestone else hours / hours_per_day,
                kind=ActivityKind.FINISH_MILESTONE if is_milestone else ActivityKind.TASK,
                calendar_id=calendar.id,
                early_start=as_date(task.getStart()),
                early_finish=as_date(task.getFinish()),
                actual_start=as_date(task.getActualStart()),
                actual_finish=as_date(task.getActualFinish()),
                percent_complete=float(task.getPercentageComplete() or 0),
            )
        )

    known = {a.id for a in schedule.activities}
    for task in project.getTasks():
        successor = str(task.getUniqueID() or "")
        if successor not in known:
            continue
        for relation in task.getPredecessors():
            predecessor = str(relation.getPredecessorTask().getUniqueID())
            if predecessor not in known:
                continue
            lag = relation.getLag()
            schedule.relationships.append(
                ExchangeRelationship(
                    predecessor_id=predecessor,
                    successor_id=successor,
                    type=link_types.get(str(relation.getType()), RelationType.FS),
                    lag=(float(lag.getDuration()) if lag else 0.0) / hours_per_day,
                )
            )

    return schedule


def _unique_project_number(code: str | None, company_id: int) -> str | None:
    """Return ``code``, suffixed if that number is already used by the company."""
    if not code:
        return None

    base = code[:50]
    if not Project.query.filter_by(company_id=company_id, project_number=base).first():
        return base

    for suffix in range(2, 1000):
        candidate = f"{base[: 50 - len(str(suffix)) - 1]}-{suffix}"
        if not Project.query.filter_by(company_id=company_id, project_number=candidate).first():
            return candidate
    return None


# ── exchange model to database ───────────────────────────────────────────


def import_into_project(
    schedule: ExchangeSchedule,
    company_id: int,
    user_id: int,
    *,
    project_name: str | None = None,
) -> Project:
    """Create a new project from an imported schedule.

    Always creates rather than merges. Merging an external schedule into an
    existing one needs a matching strategy and a conflict policy, which is a
    separate decision; silently overwriting would be worse than not offering it.
    """
    problems = schedule.validate()
    if problems:
        raise ImportError_("; ".join(problems[:5]))

    real_activities = [a for a in schedule.activities if a.kind is not ActivityKind.WBS_SUMMARY]
    if not real_activities:
        raise ImportError_("The file contains no activities")

    calendar = schedule.default_calendar
    start = schedule.start_date or min(
        (a.early_start for a in real_activities if a.early_start), default=date.today()
    )
    finish = schedule.finish_date or max(
        (a.early_finish for a in real_activities if a.early_finish), default=start
    )

    project = Project(
        name=(project_name or schedule.name)[:200],
        description=f"Imported from {schedule.source_format.upper()}",
        # Importing the same schedule twice is normal — successive revisions of
        # one plan carry the same project code — so the code is suffixed rather
        # than allowed to collide.
        project_number=_unique_project_number(schedule.code, company_id),
        company_id=company_id,
        created_by=user_id,
        start_date=start,
        end_date=finish,
        status="active",
        schedule_type=ScheduleType.GANTT,
        data_date=schedule.data_date,
    )
    db.session.add(project)
    db.session.flush()

    work_calendar = WorkCalendar(
        start,
        work_days=calendar.working_weekdays if calendar else WorkCalendar.STANDARD_5_DAY,
    )

    tasks: dict[str, Task] = {}
    for activity in real_activities:
        task_start = activity.early_start or start
        duration_days = max(0, round(activity.duration))
        task_finish = activity.early_finish or work_calendar.finish_date_for(
            work_calendar.work_days_between(start, task_start) - 1, duration_days
        )

        if activity.actual_finish:
            status = TaskStatus.COMPLETED
        elif activity.actual_start:
            status = TaskStatus.IN_PROGRESS
        else:
            status = TaskStatus.NOT_STARTED

        constraints = None
        if activity.constraint_type is not ConstraintType.NONE and activity.constraint_date:
            constraints = {
                "type": activity.constraint_type.value,
                "must_start_on": activity.constraint_date.isoformat(),
            }

        task = Task(
            name=activity.name[:200],
            description=activity.notes or None,
            project_id=project.id,
            wbs_code=(activity.code or activity.id)[:50],
            start_date=task_start,
            end_date=task_finish if task_finish >= task_start else task_start,
            duration=duration_days,
            progress=activity.percent_complete,
            status=status,
            baseline_start=activity.baseline_start,
            baseline_finish=activity.baseline_finish,
            baseline_duration=duration_days if activity.baseline_start else None,
            actual_start=activity.actual_start,
            actual_finish=activity.actual_finish,
            constraints=constraints,
        )
        db.session.add(task)
        tasks[activity.id] = task

    db.session.flush()

    seen: set[tuple[int, int]] = set()
    for link in schedule.relationships:
        predecessor = tasks.get(link.predecessor_id)
        successor = tasks.get(link.successor_id)
        if not predecessor or not successor:
            continue
        # The schema enforces one link per pair; a file may carry duplicates.
        pair = (successor.id, predecessor.id)
        if pair in seen:
            continue
        seen.add(pair)
        db.session.add(
            TaskDependency(
                task_id=successor.id,
                predecessor_task_id=predecessor.id,
                dependency_type=link.type.value,
                lag_days=round(link.lag),
            )
        )

    resources: dict[str, Resource] = {}
    for entry in schedule.resources:
        resource = Resource(
            name=entry.name[:100],
            type=entry.kind[:20],
            project_id=project.id,
            unit=(entry.unit or "")[:20] or None,
            unit_cost=entry.standard_rate,
            total_quantity=entry.max_units_per_day,
            available_quantity=entry.max_units_per_day,
        )
        db.session.add(resource)
        resources[entry.id] = resource
    db.session.flush()

    for assignment in schedule.assignments:
        task = tasks.get(assignment.activity_id)
        resource = resources.get(assignment.resource_id)
        if task and resource:
            db.session.add(
                ResourceAssignment(
                    task_id=task.id,
                    resource_id=resource.id,
                    quantity=assignment.units or 1.0,
                    assignment_date=task.start_date,
                )
            )

    db.session.commit()
    return project


# ── database to exchange model ───────────────────────────────────────────


def export_project(project_id: int) -> ExchangeSchedule:
    """Read a stored project out as an :class:`ExchangeSchedule`."""
    project = Project.query.get(project_id)
    if project is None:
        raise LookupError(f"Project {project_id} not found")

    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.start_date, Task.id).all()
    task_ids = {task.id for task in tasks}

    calendar = Calendar(id="1", name="Standard 5-day", hours_per_day=8.0, is_default=True)
    schedule = ExchangeSchedule(
        name=project.name,
        code=project.project_number or "",
        start_date=project.start_date,
        finish_date=project.end_date,
        data_date=project.effective_data_date,
        default_calendar_id=calendar.id,
        calendars=[calendar],
        source_format="bbschedule",
        exported_at=datetime.now(),
    )

    for task in tasks:
        duration = task.duration or 0
        is_milestone = duration == 0
        constraints = task.constraints if isinstance(task.constraints, dict) else {}
        constraint_date = None
        constraint_type = ConstraintType.NONE
        if constraints.get("must_start_on"):
            try:
                constraint_date = date.fromisoformat(constraints["must_start_on"])
                constraint_type = ConstraintType.START_ON_OR_AFTER
            except (TypeError, ValueError):
                constraint_date = None

        schedule.activities.append(
            ExchangeActivity(
                id=str(task.id),
                name=task.name,
                code=task.wbs_code or str(task.id),
                duration=0.0 if is_milestone else float(duration),
                kind=ActivityKind.FINISH_MILESTONE if is_milestone else ActivityKind.TASK,
                calendar_id=calendar.id,
                notes=task.description or "",
                early_start=task.start_date,
                early_finish=task.end_date,
                baseline_start=task.baseline_start,
                baseline_finish=task.baseline_finish,
                actual_start=task.actual_start,
                actual_finish=task.actual_finish,
                percent_complete=task.progress or 0.0,
                constraint_type=constraint_type,
                constraint_date=constraint_date,
            )
        )

    dependencies = (
        TaskDependency.query.filter(TaskDependency.task_id.in_(task_ids)).all() if task_ids else []
    )
    for dependency in dependencies:
        if dependency.predecessor_task_id not in task_ids:
            continue
        try:
            relation = RelationType((dependency.dependency_type or "FS").upper())
        except ValueError:
            relation = RelationType.FS
        schedule.relationships.append(
            ExchangeRelationship(
                predecessor_id=str(dependency.predecessor_task_id),
                successor_id=str(dependency.task_id),
                type=relation,
                lag=float(dependency.lag_days or 0),
            )
        )

    for resource in Resource.query.filter_by(project_id=project_id).all():
        schedule.resources.append(
            ExchangeResource(
                id=str(resource.id),
                name=resource.name,
                kind=resource.type or "labor",
                unit=resource.unit or "",
                standard_rate=resource.unit_cost,
                max_units_per_day=resource.total_quantity,
            )
        )

    assignments = (
        ResourceAssignment.query.filter(ResourceAssignment.task_id.in_(task_ids)).all()
        if task_ids
        else []
    )
    for assignment in assignments:
        schedule.assignments.append(
            ExchangeAssignment(
                activity_id=str(assignment.task_id),
                resource_id=str(assignment.resource_id),
                units=assignment.quantity or 1.0,
            )
        )

    return schedule


def serialise(schedule: ExchangeSchedule, export_format: str) -> tuple[str, str, str]:
    """Render a schedule to text. Returns ``(content, filename, mimetype)``."""
    if export_format not in EXPORT_FORMATS:
        valid = ", ".join(EXPORT_FORMATS)
        raise ValueError(f"Unsupported export format {export_format!r}. Valid: {valid}")

    safe_name = (
        "".join(
            c if c.isalnum() or c in "-_" else "-" for c in (schedule.code or schedule.name)
        ).strip("-")
        or "schedule"
    )

    if export_format == "xer":
        return write_xer(schedule), f"{safe_name}.xer", "text/plain"
    return write_mspdi(schedule), f"{safe_name}.xml", "application/xml"


def mpp_available() -> bool:
    """Whether binary ``.mpp`` reading is usable in this environment."""
    try:
        require("mpxj", feature="MS Project .mpp reading")
        require("jpype", feature="MS Project .mpp reading")
    except IntegrationUnavailable:
        return False
    return True


def capabilities() -> dict[str, Any]:
    """What this deployment can actually do, for the UI to show honestly."""
    return {
        "read": {
            "xer": True,
            "mspdi": True,
            "mpp": mpp_available(),
        },
        "write": {
            "xer": True,
            "mspdi": True,
            # Not a limitation of this project: the binary format is
            # proprietary and cannot be written by any available library.
            "mpp": False,
        },
        "notes": {
            "mpp_write": (
                "Microsoft Project's binary .mpp format cannot be written by any "
                "available library. Export MSPDI XML and open it in Project, which "
                "can then save a .mpp."
            ),
            "mpp_read": (
                "Reading .mpp requires the optional mpxj package and a Java runtime."
                if not mpp_available()
                else "Reading .mpp is available via MPXJ."
            ),
        },
    }
