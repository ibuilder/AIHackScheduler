"""Seed a realistic demo project so the platform can be evaluated in a minute.

Run with::

    flask --app app seed-demo

The schedule models a four-storey commercial fit-out. It is deliberately
*imperfect*: it contains a dangling activity, a lead, a couple of over-long
tasks and a date constraint, so the DCMA assessment has something real to
report rather than a synthetic clean bill of health.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from werkzeug.security import generate_password_hash

from core.calendar import WorkCalendar
from core.cpm import Activity, Relationship, RelationType, calculate_cpm
from extensions import db
from models import (
    Company,
    Equipment,
    EquipmentStatus,
    EquipmentType,
    EquipmentUsageLog,
    ExpenseCategory,
    Invoice,
    InvoiceItem,
    InvoiceStatus,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceType,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Project,
    Resource,
    ResourceAssignment,
    ScheduleBaseline,
    ScheduleType,
    Task,
    TaskDependency,
    TaskStatus,
    Transaction,
    TransactionType,
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

# (number, name, type, manufacturer, model, purchase cost, daily hours worked)
# The hours figure drives how much usage is logged, so utilisation comes out
# genuinely different per machine rather than a uniform placeholder.
EQUIPMENT = [
    (
        "EQ-001",
        "Tower crane — Potain MDT 219",
        EquipmentType.HEAVY_MACHINERY,
        "Potain",
        "MDT 219",
        480_000.0,
        6.5,
    ),
    (
        "EQ-002",
        "Telehandler — JCB 540-170",
        EquipmentType.HEAVY_MACHINERY,
        "JCB",
        "540-170",
        96_000.0,
        5.0,
    ),
    ("EQ-003", "Scissor lift 26ft", EquipmentType.SPECIALIZED, "Genie", "GS-2632", 18_500.0, 3.0),
    ("EQ-004", "Site generator 60kVA", EquipmentType.GENERATORS, "Aggreko", "60kVA", 22_000.0, 8.0),
    ("EQ-005", "Crew van", EquipmentType.VEHICLES, "Ford", "Transit 350", 38_000.0, 2.0),
    ("EQ-006", "Concrete saw", EquipmentType.TOOLS, "Husqvarna", "K 770", 1_400.0, 0.5),
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
        # Equipment, invoices, payments and transactions all hang off the
        # company rather than the project, so none of them go with the project
        # cascade. Without clearing them explicitly a second seed collides on
        # the per-company unique numbers. Payments are removed before the
        # invoices they reference so no row is left orphaned mid-delete.
        for payment in list(company.payments):
            db.session.delete(payment)
        for invoice in list(company.invoices):
            db.session.delete(invoice)
        for transaction in list(company.transactions):
            db.session.delete(transaction)
        for item in list(company.equipment):
            db.session.delete(item)
        db.session.flush()

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

    # ── Equipment, with usage logged so utilisation is measured ──────────
    today = date.today()
    fleet = {}
    for number, name, kind, manufacturer, model, cost, daily_hours in EQUIPMENT:
        item = Equipment(
            equipment_number=number,
            name=name,
            equipment_type=kind,
            manufacturer=manufacturer,
            model=model,
            purchase_cost=cost,
            current_value=cost * 0.72,
            status=EquipmentStatus.IN_USE,
            location="Springfield Business District",
            current_project_id=project.id,
            company_id=company.id,
            maintenance_interval_hours=250,
            next_maintenance_date=today + timedelta(days=21),
        )
        db.session.add(item)
        fleet[number] = (item, daily_hours)
    db.session.flush()

    # Sixty days of usage. Weekends are skipped and the concrete saw is used
    # only occasionally, so the fleet shows a realistic spread rather than one
    # figure repeated across every machine.
    for index, (item, daily_hours) in enumerate(fleet.values()):
        total = 0.0
        for offset in range(60):
            usage_date = today - timedelta(days=offset)
            if usage_date.weekday() >= 5:
                continue
            # A deterministic wobble: no randomness, so the demo is reproducible.
            wobble = ((offset * 7 + index * 13) % 5 - 2) * 0.4
            hours = max(0.0, round(daily_hours + wobble, 1))
            if hours == 0:
                continue
            db.session.add(
                EquipmentUsageLog(
                    equipment_id=item.id,
                    usage_date=usage_date,
                    hours_used=hours,
                    project_id=project.id,
                    operator_id=user.id,
                    company_id=company.id,
                )
            )
            total += hours
        item.operating_hours = round(total, 1)

    # Maintenance: one completed, one scheduled, one deliberately overdue so
    # the schedule page has each state to show.
    crane = fleet["EQ-001"][0]
    generator = fleet["EQ-004"][0]
    telehandler = fleet["EQ-002"][0]
    db.session.add_all(
        [
            MaintenanceRecord(
                equipment_id=crane.id,
                maintenance_type=MaintenanceType.INSPECTION,
                status=MaintenanceStatus.COMPLETED,
                scheduled_date=today - timedelta(days=45),
                completed_date=today - timedelta(days=44),
                description="Statutory thorough examination — LOLER",
                work_performed="Examined, certificate issued, no defects found.",
                labour_cost=1450.00,
                parts_cost=0,
                downtime_hours=6.0,
                operating_hours_at_service=crane.operating_hours,
                technician_id=user.id,
                company_id=company.id,
            ),
            MaintenanceRecord(
                equipment_id=generator.id,
                maintenance_type=MaintenanceType.PREVENTIVE,
                status=MaintenanceStatus.SCHEDULED,
                scheduled_date=today + timedelta(days=14),
                description="250-hour service: oil, filters, coolant check",
                labour_cost=380.00,
                parts_cost=220.00,
                company_id=company.id,
            ),
            MaintenanceRecord(
                equipment_id=telehandler.id,
                maintenance_type=MaintenanceType.CORRECTIVE,
                status=MaintenanceStatus.SCHEDULED,
                scheduled_date=today - timedelta(days=9),
                description="Hydraulic hose weep on boom extension — reported by operator",
                labour_cost=260.00,
                parts_cost=140.00,
                company_id=company.id,
            ),
        ]
    )

    # ── Ledger, so budget utilisation is measured rather than zero ───────
    # Roughly 14% of an 18.4M budget spent against ~16% of the work complete,
    # which reads as slightly ahead on cost. Deliberately not round numbers.
    spend_plan = [
        (ExpenseCategory.LABOR, "Site management — Sep to Nov", 486_400.00, 70),
        (ExpenseCategory.SUBCONTRACTOR, "Demolition & strip-out — final account", 812_750.00, 58),
        (ExpenseCategory.SUBCONTRACTOR, "Asbestos survey and clearance", 96_200.00, 62),
        (ExpenseCategory.MATERIALS, "Structural steel — first delivery", 640_000.00, 34),
        (ExpenseCategory.EQUIPMENT, "Tower crane erection and hire", 218_500.00, 66),
        (ExpenseCategory.PERMITS, "Building control and hoarding licence", 41_300.00, 74),
        (ExpenseCategory.INSURANCE, "Contract works insurance — annual", 128_900.00, 76),
        (ExpenseCategory.UTILITIES, "Temporary power and water", 33_450.00, 20),
        (ExpenseCategory.FUEL, "Plant fuel — October", 18_720.00, 25),
        (ExpenseCategory.OVERHEAD, "Site accommodation and welfare", 74_600.00, 44),
    ]
    for index, (category, description, amount, days_ago) in enumerate(spend_plan, start=1):
        db.session.add(
            Transaction(
                transaction_number=f"TXN-2026-{index:04d}",
                transaction_type=TransactionType.EXPENSE,
                amount=Decimal(str(amount)),
                description=description,
                transaction_date=project.data_date - timedelta(days=days_ago),
                expense_category=category,
                project_id=project.id,
                payment_method=PaymentMethod.BANK_TRANSFER,
                vendor_customer_name="Various",
                company_id=company.id,
                created_by_id=user.id,
            )
        )

    # One part-paid application for payment, so the invoice and payment flow
    # has something real to show.
    # Anchored to the real current date, not the project data date: billing
    # measures "overdue" against today, so dates set in the project's future
    # would never exercise the overdue path.
    application = Invoice(
        invoice_number="INV-2026-0001",
        client_name="Northgate Estates LLP",
        client_email="ap@northgate-estates.example",
        client_address="4 Exchange Square, Springfield",
        issue_date=today - timedelta(days=38),
        due_date=today - timedelta(days=8),
        subtotal=Decimal("2450000.00"),
        tax_rate=Decimal("0.0000"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("2450000.00"),
        status=InvoiceStatus.SENT,
        project_id=project.id,
        payment_terms="Net 30",
        notes="Application for payment 03 — works to 31 October.",
        company_id=company.id,
        created_by_id=user.id,
    )
    db.session.add(application)
    db.session.flush()

    db.session.add(
        InvoiceItem(
            invoice_id=application.id,
            description="Works executed to 31 October, per valuation 03",
            quantity=Decimal("1.00"),
            unit_price=Decimal("2450000.00"),
            line_total=Decimal("2450000.00"),
        )
    )

    part_payment = Payment(
        payment_number="PAY-2026-0001",
        amount=Decimal("1800000.00"),
        payment_date=today - timedelta(days=4),
        payment_method=PaymentMethod.BANK_TRANSFER,
        status=PaymentStatus.COMPLETED,
        reference_number="FT-2026-11-0043",
        payer_name="Northgate Estates LLP",
        description="Part payment against application 03",
        company_id=company.id,
        processed_by_id=user.id,
    )
    part_payment.invoice = application
    db.session.add(part_payment)
    db.session.flush()
    application.recalculate_payments()

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
