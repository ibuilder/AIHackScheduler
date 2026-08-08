"""Seed a realistic demo project so the platform can be evaluated in a minute.

Run with::

    flask --app app seed-demo

The schedule models a four-storey commercial fit-out. It is deliberately
*imperfect*: it contains a dangling activity, a lead, a couple of over-long
tasks and a date constraint, so the DCMA assessment has something real to
report rather than a synthetic clean bill of health.
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from core.calendar import WorkCalendar
from core.cpm import Activity, Relationship, RelationType, calculate_cpm
from extensions import db
from models import (
    Company,
    Project,
    Resource,
    ResourceAssignment,
    ScheduleBaseline,
    ScheduleType,
    Task,
    TaskDependency,
    TaskStatus,
    User,
    UserRole,
)

DEMO_COMPANY = "Northgate Construction (Demo)"
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo1234"
PROJECT_START = date(2026, 9, 7)  # a Monday

# (id, name, duration in working days, constraint offset or None)
ACTIVITIES = [
    ("A100", "Mobilisation & site setup", 5, None),
    ("A110", "Demolition & strip-out", 15, None),
    ("A120", "Asbestos survey clearance", 3, None),
    ("A200", "Structural steel remediation", 20, None),
    ("A210", "Level 1 slab repairs", 10, None),
    ("A220", "Level 2 slab repairs", 10, None),
    ("A230", "Level 3 slab repairs", 10, None),
    ("A240", "Level 4 slab repairs", 10, None),
    ("A300", "Roof membrane replacement", 12, None),
    ("A310", "Facade glazing — north", 18, None),
    ("A320", "Facade glazing — south", 18, None),
    # Deliberately over-long: a single 70-day activity cannot be progressed
    # meaningfully and will trip DCMA check 8.
    ("A400", "MEP rough-in, all levels", 70, None),
    ("A410", "Fire protection rough-in", 25, None),
    ("A420", "Electrical distribution", 30, None),
    # Deliberately constrained: the utility connection is fixed by the network
    # operator, which trips DCMA check 5.
    ("A430", "Utility connection", 4, 95),
    ("A500", "Drywall & partitions", 28, None),
    ("A510", "Ceilings & grid", 20, None),
    ("A520", "Flooring", 18, None),
    ("A530", "Painting & finishes", 22, None),
    ("A600", "MEP commissioning", 15, None),
    ("A610", "Life safety testing", 8, None),
    ("A620", "Building control inspection", 5, None),
    ("A700", "Snagging & handover", 10, None),
    ("A710", "Practical completion", 0, None),
    # Deliberately dangling: real schedules always have one of these hiding in
    # them, and it trips DCMA check 1.
    ("A900", "Landscaping (scope TBC)", 12, None),
]

RELATIONSHIPS = [
    ("A100", "A110", RelationType.FS, 0),
    ("A100", "A120", RelationType.FS, 0),
    ("A110", "A200", RelationType.FS, 0),
    ("A120", "A200", RelationType.FS, 0),
    ("A200", "A210", RelationType.FS, 0),
    ("A210", "A220", RelationType.FS, 0),
    ("A220", "A230", RelationType.FS, 0),
    ("A230", "A240", RelationType.FS, 0),
    ("A200", "A300", RelationType.FS, 0),
    ("A300", "A310", RelationType.FS, 0),
    ("A310", "A320", RelationType.SS, 5),
    ("A240", "A400", RelationType.FS, 0),
    ("A400", "A410", RelationType.SS, 10),
    ("A400", "A420", RelationType.SS, 15),
    ("A420", "A430", RelationType.FS, 0),
    # Deliberately a lead: overlapping drywall with MEP rough-in by 5 days is
    # how planners fake compression, and it trips DCMA check 2.
    ("A400", "A500", RelationType.FS, -5),
    ("A320", "A500", RelationType.FS, 0),
    ("A500", "A510", RelationType.FS, 0),
    ("A510", "A520", RelationType.FS, 0),
    ("A520", "A530", RelationType.FS, 0),
    ("A410", "A600", RelationType.FS, 0),
    ("A430", "A600", RelationType.FS, 0),
    ("A530", "A600", RelationType.FS, 0),
    ("A600", "A610", RelationType.FS, 0),
    ("A610", "A620", RelationType.FS, 0),
    ("A620", "A700", RelationType.FS, 0),
    ("A700", "A710", RelationType.FS, 0),
]

RESOURCES = [
    ("Site management", "labor", "crew", 1800.0, 1.0),
    ("Steel erectors", "labor", "crew", 4200.0, 2.0),
    ("MEP crew", "labor", "crew", 3800.0, 4.0),
    ("Drywall crew", "labor", "crew", 2600.0, 3.0),
    ("Finishing crew", "labor", "crew", 2400.0, 3.0),
    ("Tower crane", "equipment", "day", 1200.0, 1.0),
    ("Mobile elevating platform", "equipment", "day", 340.0, 6.0),
]

# activity id -> resource name. A few activities are left unresourced on
# purpose so DCMA check 10 has something to report.
RESOURCE_PLAN = {
    "A100": "Site management",
    "A110": "Site management",
    "A200": "Steel erectors",
    "A210": "Steel erectors",
    "A220": "Steel erectors",
    "A230": "Steel erectors",
    "A240": "Steel erectors",
    "A300": "Mobile elevating platform",
    "A310": "Mobile elevating platform",
    "A320": "Mobile elevating platform",
    "A400": "MEP crew",
    "A410": "MEP crew",
    "A420": "MEP crew",
    "A500": "Drywall crew",
    "A510": "Drywall crew",
    "A520": "Finishing crew",
    "A530": "Finishing crew",
    "A600": "MEP crew",
    "A700": "Site management",
}

# Where the project is reporting from, as a working-day offset from the start.
# Roughly eleven weeks in — far enough for a baseline to have been tested by
# reality, early enough that most of the job is ahead.
DATA_DATE_OFFSET = 55

# What actually happened, as working-day slip against the baseline finish.
# A value of 0 means the activity finished exactly on its baseline date.
# Activities absent from this map are neither started nor finished.
ACTUAL_FINISH_SLIP = {
    "A100": 0,  # mobilisation went to plan
    "A120": 0,  # asbestos clearance came back on time
    "A110": 4,  # demolition hit unrecorded services and ran four days over
    "A200": 2,  # steel remediation absorbed part of that slip
}

# Started but not finished at the data date.
IN_PROGRESS = {"A210": 25.0}


def seed(reset: bool = True) -> Project:
    """Create the demo company, user, project and schedule. Returns the project."""
    company = Company.query.filter_by(name=DEMO_COMPANY).first()
    if company and reset:
        for project in list(company.projects):
            db.session.delete(project)
        db.session.flush()
    elif not company:
        company = Company(
            name=DEMO_COMPANY,
            email="hello@northgate.example",
            phone="+1 555 0100",
            address="1 Northgate Way, Springfield",
        )
        db.session.add(company)
        db.session.flush()

    user = User.query.filter_by(username=DEMO_USERNAME).first()
    if user is None:
        user = User(
            username=DEMO_USERNAME,
            email="demo@northgate.example",
            password_hash=generate_password_hash(DEMO_PASSWORD),
            first_name="Dana",
            last_name="Okonkwo",
            role=UserRole.PROJECT_MANAGER,
            company_id=company.id,
        )
        db.session.add(user)
        db.session.flush()

    calendar = WorkCalendar(PROJECT_START)

    # Run CPM first so the stored dates are internally consistent — seeding
    # arbitrary dates would make the demo's own health report meaningless.
    activities = [
        Activity(aid, name, duration, constraint) for aid, name, duration, constraint in ACTIVITIES
    ]
    relationships = [
        Relationship(pred, succ, rel_type, lag) for pred, succ, rel_type, lag in RELATIONSHIPS
    ]
    result = calculate_cpm(activities, relationships)

    project = Project(
        name="Northgate Tower — Commercial Fit-Out",
        description=(
            "Four-storey commercial refurbishment: structural remediation, facade "
            "replacement, full MEP rough-in and Cat-A fit-out."
        ),
        project_number="NGT-2026-014",
        company_id=company.id,
        created_by=user.id,
        start_date=calendar.start_date,
        end_date=calendar.finish_date_for(0, result.project_duration),
        budget=18_400_000.0,
        location="Springfield Business District",
        status="active",
        schedule_type=ScheduleType.GANTT,
        data_date=calendar.date_for_offset(DATA_DATE_OFFSET),
    )
    db.session.add(project)
    db.session.flush()

    resources = {}
    for name, kind, unit, unit_cost, quantity in RESOURCES:
        resource = Resource(
            name=name,
            type=kind,
            project_id=project.id,
            unit=unit,
            unit_cost=unit_cost,
            total_quantity=quantity,
            available_quantity=quantity,
        )
        db.session.add(resource)
        resources[name] = resource
    db.session.flush()

    tasks = {}
    for index, (aid, name, duration, constraint) in enumerate(ACTIVITIES):
        computed = result.activities[aid]
        start = calendar.date_for_offset(computed.early_start)
        finish = calendar.finish_date_for(computed.early_start, duration)

        # Baseline is the plan as first approved; the stored plan matches it
        # here because nothing has been re-scheduled yet. Actuals are what
        # reality did to it.
        actual_start = actual_finish = None
        if aid in ACTUAL_FINISH_SLIP:
            status, progress = TaskStatus.COMPLETED, 100.0
            actual_start = start
            actual_finish = calendar.date_for_offset(
                computed.early_start + max(duration - 1, 0) + ACTUAL_FINISH_SLIP[aid]
            )
        elif aid in IN_PROGRESS:
            status, progress = TaskStatus.IN_PROGRESS, IN_PROGRESS[aid]
            actual_start = start
        else:
            status, progress = TaskStatus.NOT_STARTED, 0.0

        task = Task(
            name=name,
            description=f"{name} — demo schedule activity {aid}",
            project_id=project.id,
            wbs_code=aid,
            start_date=start,
            end_date=finish,
            duration=duration,
            progress=progress,
            status=status,
            baseline_start=start,
            baseline_finish=finish,
            baseline_duration=duration,
            actual_start=actual_start,
            actual_finish=actual_finish,
            priority="high" if computed.is_critical else "medium",
            constraints=(
                {"must_start_on": calendar.date_for_offset(constraint).isoformat()}
                if constraint is not None
                else None
            ),
            # Linear-schedule stationing for the facade and slab activities, so
            # the time-distance view has something to draw.
            station_start=float(index * 40) if aid.startswith(("A2", "A3")) else None,
            station_end=float(index * 40 + 120) if aid.startswith(("A2", "A3")) else None,
            pull_plan_week=1 + computed.early_start // 5,
        )
        db.session.add(task)
        tasks[aid] = task
    db.session.flush()

    for pred, succ, rel_type, lag in RELATIONSHIPS:
        db.session.add(
            TaskDependency(
                task_id=tasks[succ].id,
                predecessor_task_id=tasks[pred].id,
                dependency_type=rel_type.value,
                lag_days=lag,
            )
        )

    for aid, resource_name in RESOURCE_PLAN.items():
        db.session.add(
            ResourceAssignment(
                task_id=tasks[aid].id,
                resource_id=resources[resource_name].id,
                quantity=1.0,
                assignment_date=tasks[aid].start_date,
            )
        )

    # The baseline history record. Task.baseline_* is already populated above;
    # this is the snapshot that makes revision comparison possible later.
    db.session.add(
        ScheduleBaseline(
            project_id=project.id,
            name="Contract baseline — rev A",
            notes="Approved at contract award, before the demolition slip.",
            snapshot={
                str(task.id): {
                    "start": task.baseline_start.isoformat(),
                    "finish": task.baseline_finish.isoformat(),
                    "duration": task.baseline_duration,
                }
                for task in tasks.values()
            },
            is_current=True,
            set_by_id=user.id,
        )
    )

    db.session.commit()

    complete = sum(1 for t in tasks.values() if t.actual_finish)
    print(f"Seeded '{project.name}' ({len(tasks)} activities, {len(RELATIONSHIPS)} links)")
    print(f"  Calculated duration : {result.project_duration} working days")
    print(f"  Planned finish      : {project.end_date}")
    print(f"  Data date           : {project.data_date} ({complete} activities complete)")
    print(f"  Sign in as          : {DEMO_USERNAME} / {DEMO_PASSWORD}")
    return project


if __name__ == "__main__":
    from app import app

    with app.app_context():
        db.create_all()
        seed()
