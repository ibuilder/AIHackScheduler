"""Tests for equipment utilisation and maintenance.

Utilisation used to be the constant 75.5 for every machine on every dashboard.
These tests exist to make sure it is a measurement again.
"""

from datetime import date, timedelta

import pytest

from extensions import db
from models import (
    Company,
    Equipment,
    EquipmentStatus,
    EquipmentType,
    EquipmentUsageLog,
    MaintenanceRecord,
    MaintenanceStatus,
    MaintenanceType,
)


@pytest.fixture
def fleet(app_context):
    company = Company(name="Plant Hire Co")
    db.session.add(company)
    db.session.flush()

    machine = Equipment(
        equipment_number="EQ-100",
        name="Excavator",
        equipment_type=EquipmentType.HEAVY_MACHINERY,
        status=EquipmentStatus.AVAILABLE,
        company_id=company.id,
    )
    db.session.add(machine)
    db.session.commit()
    return company, machine


def _log(machine, company, day, hours):
    db.session.add(
        EquipmentUsageLog(
            equipment_id=machine.id,
            usage_date=day,
            hours_used=hours,
            company_id=company.id,
        )
    )


def test_no_usage_logged_means_zero_not_an_average(fleet):
    """Silence is not 75.5% utilisation."""
    _, machine = fleet
    assert machine.utilization_rate(30) == 0.0
    assert machine.total_hours_logged == 0


def test_full_working_days_read_as_full_utilisation(fleet):
    company, machine = fleet
    as_of = date(2026, 6, 30)  # a Tuesday

    day = as_of
    while day > as_of - timedelta(days=30):
        if day.weekday() < 5:
            _log(machine, company, day, 8)
        day -= timedelta(days=1)
    db.session.commit()

    assert machine.utilization_rate(30, as_of=as_of) == 100.0


def test_half_days_read_as_half_utilisation(fleet):
    company, machine = fleet
    as_of = date(2026, 6, 30)

    day = as_of
    while day > as_of - timedelta(days=30):
        if day.weekday() < 5:
            _log(machine, company, day, 4)
        day -= timedelta(days=1)
    db.session.commit()

    assert machine.utilization_rate(30, as_of=as_of) == 50.0


def test_utilisation_is_capped_at_one_hundred(fleet):
    """Overtime should not report 150% utilised."""
    company, machine = fleet
    as_of = date(2026, 6, 30)

    day = as_of
    while day > as_of - timedelta(days=30):
        if day.weekday() < 5:
            _log(machine, company, day, 14)
        day -= timedelta(days=1)
    db.session.commit()

    assert machine.utilization_rate(30, as_of=as_of) == 100.0


def test_usage_outside_the_window_is_excluded(fleet):
    company, machine = fleet
    as_of = date(2026, 6, 30)

    _log(machine, company, as_of - timedelta(days=200), 8)
    db.session.commit()

    assert machine.utilization_rate(30, as_of=as_of) == 0.0
    # ...but it still counts toward the lifetime total.
    assert machine.total_hours_logged == 8


def test_one_usage_row_per_machine_per_day(fleet):
    """Two rows for the same day would double-count and inflate utilisation."""
    from sqlalchemy.exc import IntegrityError

    company, machine = fleet
    _log(machine, company, date(2026, 6, 1), 8)
    db.session.commit()

    _log(machine, company, date(2026, 6, 1), 6)
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleting_equipment_removes_its_usage_and_maintenance(fleet):
    company, machine = fleet
    _log(machine, company, date(2026, 6, 1), 8)
    db.session.add(
        MaintenanceRecord(
            equipment_id=machine.id,
            maintenance_type=MaintenanceType.PREVENTIVE,
            scheduled_date=date(2026, 7, 1),
            description="Service",
            company_id=company.id,
        )
    )
    db.session.commit()

    db.session.delete(machine)
    db.session.commit()

    assert EquipmentUsageLog.query.count() == 0
    assert MaintenanceRecord.query.count() == 0


def test_maintenance_total_cost_sums_labour_and_parts(fleet):
    company, machine = fleet
    record = MaintenanceRecord(
        equipment_id=machine.id,
        maintenance_type=MaintenanceType.CORRECTIVE,
        scheduled_date=date(2026, 7, 1),
        description="Hydraulic hose",
        labour_cost=260,
        parts_cost=140,
        company_id=company.id,
    )
    db.session.add(record)
    db.session.commit()

    assert record.total_cost == 400


def test_overdue_maintenance_is_detected(fleet):
    company, machine = fleet
    overdue = MaintenanceRecord(
        equipment_id=machine.id,
        maintenance_type=MaintenanceType.PREVENTIVE,
        status=MaintenanceStatus.SCHEDULED,
        scheduled_date=date.today() - timedelta(days=5),
        description="Late service",
        company_id=company.id,
    )
    upcoming = MaintenanceRecord(
        equipment_id=machine.id,
        maintenance_type=MaintenanceType.PREVENTIVE,
        status=MaintenanceStatus.SCHEDULED,
        scheduled_date=date.today() + timedelta(days=5),
        description="Future service",
        company_id=company.id,
    )
    db.session.add_all([overdue, upcoming])
    db.session.commit()

    assert overdue.is_overdue is True
    assert upcoming.is_overdue is False


def test_completed_maintenance_is_never_overdue(fleet):
    company, machine = fleet
    record = MaintenanceRecord(
        equipment_id=machine.id,
        maintenance_type=MaintenanceType.INSPECTION,
        status=MaintenanceStatus.COMPLETED,
        scheduled_date=date.today() - timedelta(days=30),
        completed_date=date.today() - timedelta(days=29),
        description="Done late, but done",
        company_id=company.id,
    )
    db.session.add(record)
    db.session.commit()

    assert record.is_overdue is False


# ── seeded demo fleet ─────────────────────────────────────────────────────


def test_demo_fleet_has_varied_utilisation(seeded):
    """A uniform figure across machines is the signature of a placeholder."""
    fleet = Equipment.query.all()
    assert len(fleet) >= 5

    rates = [item.utilization_rate(30) for item in fleet]
    assert len(set(rates)) > 1
    assert all(0 <= rate <= 100 for rate in rates)


def test_demo_maintenance_covers_each_state(seeded):
    records = MaintenanceRecord.query.all()
    statuses = {r.status for r in records}

    assert MaintenanceStatus.COMPLETED in statuses
    assert MaintenanceStatus.SCHEDULED in statuses
    assert any(r.is_overdue for r in records)


def test_reseeding_does_not_duplicate_the_fleet(app_context):
    """Equipment is company-scoped, so it does not go with the project cascade."""
    from seed_demo import seed

    seed()
    first = Equipment.query.count()
    seed()

    assert Equipment.query.count() == first


def test_utilisation_window_must_be_positive(fleet):
    _, machine = fleet
    with pytest.raises(ValueError, match="at least one day"):
        machine.utilization_rate(0)


def test_window_boundaries_are_inclusive(fleet):
    """The hours numerator and the working-day denominator must cover the
    same span, or a machine working half days reads as 52.4% utilised."""
    company, machine = fleet
    as_of = date(2026, 6, 30)  # Tuesday

    # Exactly one working day in a one-day window.
    _log(machine, company, as_of, 8)
    db.session.commit()

    assert machine.utilization_rate(1, as_of=as_of) == 100.0
