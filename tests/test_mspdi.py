"""Tests for the Microsoft Project XML (MSPDI) reader and writer.

MSPDI is the writable Microsoft format — the binary .mpp cannot be produced by
anyone, MPXJ included. These tests pin the three details that decide whether
Project accepts a file: ISO 8601 durations, the non-alphabetical link type
codes, and keeping UID distinct from ID.
"""

from datetime import date

import pytest

from core.cpm import RelationType, calculate_cpm
from core.exchange import ConstraintType
from core.mspdi import (
    MSPDIError,
    format_duration_hours,
    parse_duration_hours,
    read_mspdi,
    write_mspdi,
)
from core.xer import read_xer
from tests.test_xer import SAMPLE_XER

SAMPLE_MSPDI = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Project xmlns="http://schemas.microsoft.com/project">
  <Name>Northgate Tower</Name>
  <StartDate>2026-09-07T08:00:00</StartDate>
  <FinishDate>2026-10-16T17:00:00</FinishDate>
  <StatusDate>2026-09-30T08:00:00</StatusDate>
  <CalendarUID>1</CalendarUID>
  <MinutesPerDay>480</MinutesPerDay>
  <MinutesPerWeek>2400</MinutesPerWeek>
  <Calendars>
    <Calendar>
      <UID>1</UID>
      <Name>Standard</Name>
      <WeekDays>
        <WeekDay><DayType>1</DayType><DayWorking>0</DayWorking></WeekDay>
        <WeekDay><DayType>2</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>3</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>4</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>5</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>6</DayType><DayWorking>1</DayWorking></WeekDay>
        <WeekDay><DayType>7</DayType><DayWorking>0</DayWorking></WeekDay>
      </WeekDays>
    </Calendar>
  </Calendars>
  <Tasks>
    <Task>
      <UID>0</UID><ID>0</ID><Name>Project Summary</Name><Summary>1</Summary>
      <Duration>PT320H0M0S</Duration>
    </Task>
    <Task>
      <UID>1</UID><ID>1</ID><Name>Mobilise</Name>
      <Duration>PT40H0M0S</Duration>
      <Start>2026-09-07T08:00:00</Start><Finish>2026-09-11T17:00:00</Finish>
      <ActualStart>2026-09-07T08:00:00</ActualStart>
      <ActualFinish>2026-09-11T17:00:00</ActualFinish>
      <PercentComplete>100</PercentComplete>
      <Milestone>0</Milestone><Summary>0</Summary>
    </Task>
    <Task>
      <UID>2</UID><ID>2</ID><Name>Excavate</Name>
      <Duration>PT80H0M0S</Duration>
      <Start>2026-09-14T08:00:00</Start><Finish>2026-09-25T17:00:00</Finish>
      <ConstraintType>2</ConstraintType>
      <ConstraintDate>2026-09-14T08:00:00</ConstraintDate>
      <Milestone>0</Milestone><Summary>0</Summary>
      <PredecessorLink>
        <PredecessorUID>1</PredecessorUID><Type>1</Type><LinkLag>0</LinkLag>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>3</UID><ID>3</ID><Name>Pour slab</Name>
      <Duration>PT64H0M0S</Duration>
      <Milestone>0</Milestone><Summary>0</Summary>
      <PredecessorLink>
        <PredecessorUID>2</PredecessorUID><Type>3</Type><LinkLag>9600</LinkLag>
      </PredecessorLink>
    </Task>
    <Task>
      <UID>4</UID><ID>4</ID><Name>Structure complete</Name>
      <Duration>PT0H0M0S</Duration>
      <Milestone>1</Milestone><Summary>0</Summary>
      <PredecessorLink>
        <PredecessorUID>3</PredecessorUID><Type>0</Type><LinkLag>0</LinkLag>
      </PredecessorLink>
    </Task>
  </Tasks>
  <Resources>
    <Resource><UID>1</UID><Name>Groundworks crew</Name><Type>1</Type></Resource>
  </Resources>
  <Assignments>
    <Assignment>
      <UID>1</UID><TaskUID>2</TaskUID><ResourceUID>1</ResourceUID>
      <Units>1</Units><Cost>42000</Cost>
    </Assignment>
  </Assignments>
</Project>
"""


@pytest.fixture
def schedule():
    return read_mspdi(SAMPLE_MSPDI)


# ── ISO 8601 durations ───────────────────────────────────────────────────


def test_duration_parsing():
    assert parse_duration_hours("PT40H0M0S") == 40.0
    assert parse_duration_hours("PT7H30M0S") == 7.5
    assert parse_duration_hours("PT0H0M0S") == 0.0
    assert parse_duration_hours("") == 0.0


def test_duration_formatting_round_trips():
    for hours in (0.0, 7.5, 40.0, 123.25):
        assert parse_duration_hours(format_duration_hours(hours)) == pytest.approx(hours)


def test_unparseable_duration_is_zero_not_a_crash():
    assert parse_duration_hours("nonsense") == 0.0


# ── the traps ────────────────────────────────────────────────────────────


def test_link_type_codes_are_not_alphabetical(schedule):
    """Microsoft numbers them 0=FF, 1=FS, 2=SF, 3=SS. Assuming alphabetical
    order silently rewires the logic."""
    by_pair = {(r.predecessor_id, r.successor_id): r.type for r in schedule.relationships}

    assert by_pair[("1", "2")] is RelationType.FS  # Type 1
    assert by_pair[("2", "3")] is RelationType.SS  # Type 3
    assert by_pair[("3", "4")] is RelationType.FF  # Type 0


def test_uid_is_the_key_not_id(schedule):
    """Links reference UID. Conflating it with ID breaks every relationship."""
    assert {a.id for a in schedule.activities} == {"1", "2", "3", "4"}
    assert all(link.predecessor_id in {"1", "2", "3"} for link in schedule.relationships)


def test_the_project_summary_row_is_not_an_activity(schedule):
    """UID 0 is Project's own summary row; importing it as work double-counts."""
    assert schedule.activity("0") is None
    assert len(schedule.activities) == 4


# ── the rest of the mapping ──────────────────────────────────────────────


def test_durations_convert_from_hours(schedule):
    assert schedule.activity("1").duration == 5.0  # 40h / 8
    assert schedule.activity("2").duration == 10.0  # 80h / 8


def test_milestones_are_recognised(schedule):
    milestone = schedule.activity("4")
    assert milestone.kind.is_milestone
    assert milestone.duration == 0.0


def test_lag_converts_from_tenths_of_a_minute(schedule):
    """9600 tenths = 16 hours = 2 days on an 8-hour calendar."""
    ss_link = next(r for r in schedule.relationships if r.type is RelationType.SS)
    assert ss_link.lag == 2.0


def test_constraints_are_mapped(schedule):
    constrained = schedule.activity("2")
    assert constrained.constraint_type is ConstraintType.START_ON_OR_AFTER
    assert constrained.constraint_date == date(2026, 9, 14)


def test_actuals_are_read(schedule):
    done = schedule.activity("1")
    assert done.actual_start == date(2026, 9, 7)
    assert done.actual_finish == date(2026, 9, 11)
    assert done.percent_complete == 100.0


def test_calendar_working_days(schedule):
    calendar = schedule.default_calendar
    assert calendar.working_weekdays == {0, 1, 2, 3, 4}
    assert calendar.hours_per_day == 8.0


def test_resources_and_assignments(schedule):
    assert len(schedule.resources) == 1
    assert schedule.resources[0].name == "Groundworks crew"
    assert schedule.assignments[0].budgeted_cost == 42000.0


def test_a_document_without_a_project_root_is_rejected():
    with pytest.raises(MSPDIError, match="not an MSPDI file"):
        read_mspdi("<Something><Else/></Something>")


def test_malformed_xml_is_rejected():
    with pytest.raises(MSPDIError, match="Not valid XML"):
        read_mspdi("<Project><unclosed>")


def test_a_document_without_a_namespace_still_reads():
    """Some tools emit MSPDI without the namespace declaration."""
    bare = SAMPLE_MSPDI.replace(' xmlns="http://schemas.microsoft.com/project"', "")
    schedule = read_mspdi(bare)

    assert len(schedule.activities) == 4
    assert schedule.name == "Northgate Tower"


def test_the_schedule_validates(schedule):
    assert schedule.validate() == []


# ── round trip ───────────────────────────────────────────────────────────


def test_write_then_read_recovers_the_schedule(schedule):
    reread = read_mspdi(write_mspdi(schedule))

    assert reread.name == schedule.name
    assert len(reread.activities) == len(schedule.activities)
    assert len(reread.relationships) == len(schedule.relationships)


def test_round_trip_preserves_link_types(schedule):
    reread = read_mspdi(write_mspdi(schedule))
    original = {(r.predecessor_id, r.successor_id): r.type for r in schedule.relationships}
    recovered = {(r.predecessor_id, r.successor_id): r.type for r in reread.relationships}

    assert recovered == original


def test_round_trip_preserves_durations_lag_and_milestones(schedule):
    reread = read_mspdi(write_mspdi(schedule))

    for original in schedule.activities:
        recovered = reread.activity(original.id)
        assert recovered.duration == original.duration, original.id
        assert recovered.kind.is_milestone == original.kind.is_milestone, original.id

    original_lag = {(r.predecessor_id, r.successor_id): r.lag for r in schedule.relationships}
    recovered_lag = {(r.predecessor_id, r.successor_id): r.lag for r in reread.relationships}
    assert recovered_lag == original_lag


def test_the_written_xml_has_the_expected_shape(schedule):
    text = write_mspdi(schedule)

    assert text.startswith('<?xml version="1.0"')
    assert "http://schemas.microsoft.com/project" in text
    assert (
        "<Duration>PT40H0M0S</Duration>"
        in text.replace(f"{{{'http://schemas.microsoft.com/project'}}}", "")
        or "PT40H0M0S" in text
    )
    assert "PredecessorLink" in text


def test_scheduling_is_identical_after_a_round_trip(schedule):
    before = calculate_cpm(*schedule.to_cpm())
    after = calculate_cpm(*read_mspdi(write_mspdi(schedule)).to_cpm())

    assert after.project_duration == before.project_duration
    assert after.critical_path == before.critical_path


# ── crossing formats ─────────────────────────────────────────────────────


def test_an_xer_schedule_can_be_exported_as_mspdi():
    """The point of a neutral model: Primavera in, Microsoft out."""
    from_xer = read_xer(SAMPLE_XER)
    as_mspdi = read_mspdi(write_mspdi(from_xer))

    assert len(as_mspdi.activities) == len(from_xer.activities)

    original = {(r.predecessor_id, r.successor_id): r.type for r in from_xer.relationships}
    crossed = {(r.predecessor_id, r.successor_id): r.type for r in as_mspdi.relationships}
    assert crossed == original


def test_crossing_formats_preserves_the_computed_schedule():
    from_xer = read_xer(SAMPLE_XER)
    crossed = read_mspdi(write_mspdi(from_xer))

    before = calculate_cpm(*from_xer.to_cpm())
    after = calculate_cpm(*crossed.to_cpm())

    assert after.project_duration == before.project_duration
    assert after.critical_path == before.critical_path


def test_milestones_survive_crossing_formats():
    from_xer = read_xer(SAMPLE_XER)
    crossed = read_mspdi(write_mspdi(from_xer))

    milestone = crossed.activity("T5")
    assert milestone is not None
    assert milestone.kind.is_milestone
    assert milestone.duration == 0.0


def test_a_ten_hour_calendar_survives_crossing_formats():
    """XER carries hours-per-day on the calendar; MSPDI carries it on the
    project. The duration in days must come out the same either way."""
    from_xer = read_xer(SAMPLE_XER)
    crossed = read_mspdi(write_mspdi(from_xer))

    assert from_xer.default_calendar.hours_per_day == 10.0
    assert crossed.default_calendar.hours_per_day == 10.0
    assert crossed.activity("T1").duration == from_xer.activity("T1").duration == 5.0
