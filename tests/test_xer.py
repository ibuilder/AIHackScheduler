"""Tests for the Primavera XER reader and writer.

Four of these exist specifically because a previous importer in this project
got them wrong, silently: relationship types, hours-per-day, milestones, and
which table costs live in. Each is worth a named test.
"""

from datetime import date

import pytest

from core.cpm import RelationType, calculate_cpm
from core.exchange import ActivityKind, ConstraintType
from core.xer import XERError, parse_tables, read_xer, write_xer

# A hand-built XER exercising every relationship type, a 10-hour calendar,
# a milestone, a constraint, costs on TASKRSRC and a note on TASKMEMO.
SAMPLE_XER = "\n".join(
    [
        "ERMHDR\t19.12\t2026-08-08\tProject\tadmin\tadmin\t\tProject Management\tUSD",
        "%T\tCALENDAR",
        "%F\tclndr_id\tclndr_name\tday_hr_cnt\tweek_hr_cnt\tdefault_flag\tclndr_data",
        # Ten-hour days, not eight. An importer assuming 8 rescales everything.
        "%R\tC1\tShift 10h\t10\t50\tY\t(0||CalendarData()(DaysOfWeek()(1())(2()(s|08:00|f|18:00))"
        "(3()(s|08:00|f|18:00))(4()(s|08:00|f|18:00))(5()(s|08:00|f|18:00))"
        "(6()(s|08:00|f|18:00))(7())))",
        "%T\tPROJECT",
        "%F\tproj_id\tproj_short_name\tplan_start_date\tplan_end_date\tlast_recalc_date\tclndr_id",
        "%R\t1\tNGT-2026\t2026-09-07 00:00\t2027-09-20 00:00\t2026-11-23 00:00\tC1",
        "%T\tPROJWBS",
        "%F\twbs_id\tproj_id\tparent_wbs_id\twbs_short_name\twbs_name\tseq_num\tproj_node_flag",
        "%R\tW1\t1\t\tNGT\tNorthgate Tower Fit-Out\t0\tY",
        "%R\tW2\t1\tW1\tSTRUCT\tStructure\t1\tN",
        "%T\tTASK",
        "%F\ttask_id\tproj_id\twbs_id\tclndr_id\ttask_code\ttask_name\ttask_type"
        "\ttarget_drtn_hr_cnt\tremain_drtn_hr_cnt\tearly_start_date\tearly_end_date"
        "\tact_start_date\tact_end_date\tphys_complete_pct\tcstr_type\tcstr_date",
        # 50 hours on a 10-hour calendar is 5 days, not 6.25.
        "%R\tT1\t1\tW2\tC1\tA1000\tMobilise\tTT_Task\t50\t0\t2026-09-07 00:00"
        "\t2026-09-11 00:00\t2026-09-07 00:00\t2026-09-11 00:00\t100\t\t",
        "%R\tT2\t1\tW2\tC1\tA1010\tExcavate\tTT_Task\t100\t100\t2026-09-14 00:00"
        "\t2026-09-25 00:00\t\t\t0\tCS_MSOA\t2026-09-14 00:00",
        "%R\tT3\t1\tW2\tC1\tA1020\tPour slab\tTT_Task\t80\t80\t2026-09-28 00:00"
        "\t2026-10-07 00:00\t\t\t0\t\t",
        "%R\tT4\t1\tW2\tC1\tA1030\tCure\tTT_Task\t70\t70\t2026-10-08 00:00"
        "\t2026-10-16 00:00\t\t\t0\t\t",
        # A milestone: zero duration, and it must stay zero.
        "%R\tT5\t1\tW2\tC1\tA1040\tStructure complete\tTT_FinMile\t0\t0"
        "\t2026-10-16 00:00\t2026-10-16 00:00\t\t\t0\t\t",
        "%T\tTASKPRED",
        "%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type\tlag_hr_cnt",
        "%R\t1\tT2\tT1\t1\t1\tPR_FS\t0",
        # Start-to-start with a 20-hour (2-day) lag.
        "%R\t2\tT3\tT2\t1\t1\tPR_SS\t20",
        "%R\t3\tT4\tT3\t1\t1\tPR_FF\t10",
        "%R\t4\tT5\tT4\t1\t1\tPR_SF\t0",
        "%T\tRSRC",
        "%F\trsrc_id\trsrc_name\trsrc_short_name\trsrc_type\tunit_of_measure\tclndr_id",
        "%R\tR1\tGroundworks crew\tGWC\tRT_Labor\tcrew\tC1",
        "%T\tTASKRSRC",
        "%F\ttaskrsrc_id\ttask_id\trsrc_id\tproj_id\ttarget_qty\ttarget_cost\tact_reg_cost",
        # Costs live here, not on TASK.
        "%R\t1\tT2\tR1\t1\t80\t42000\t0",
        "%T\tTASKMEMO",
        "%F\tmemo_id\ttask_id\tproj_id\tmemo_type_id\ttask_memo",
        "%R\t1\tT2\t1\t1\tWatch for unrecorded services",
        "%E",
    ]
)


@pytest.fixture
def schedule():
    return read_xer(SAMPLE_XER)


# ── tokenizer ────────────────────────────────────────────────────────────


def test_tables_are_split_by_marker():
    tables = parse_tables(SAMPLE_XER)
    assert set(tables) >= {"CALENDAR", "PROJECT", "PROJWBS", "TASK", "TASKPRED"}
    assert len(tables["TASK"]) == 5


def test_a_file_without_table_markers_is_rejected():
    with pytest.raises(XERError, match="does not look like an XER file"):
        read_xer("this is not an xer file at all")


def test_crlf_line_endings_are_handled():
    """P6 on Windows writes CRLF; a stray \\r corrupts the last field of every row."""
    schedule = read_xer(SAMPLE_XER.replace("\n", "\r\n"))
    assert len(schedule.activities) == 5
    assert schedule.activity("T1").name == "Mobilise"


def test_rows_with_a_short_field_count_are_padded_not_dropped():
    trimmed = SAMPLE_XER.replace(
        "%R\tT3\t1\tW2\tC1\tA1020\tPour slab\tTT_Task\t80\t80\t2026-09-28 00:00"
        "\t2026-10-07 00:00\t\t\t0\t\t",
        "%R\tT3\t1\tW2\tC1\tA1020\tPour slab\tTT_Task\t80\t80",
    )
    schedule = read_xer(trimmed)
    assert schedule.activity("T3") is not None


# ── the four traps ───────────────────────────────────────────────────────


def test_relationship_types_are_mapped_from_their_prefixed_form(schedule):
    """P6 writes PR_FS/PR_SS/PR_FF/PR_SF. Storing the raw string and failing to
    parse it later turns every SS, FF and SF tie into FS silently."""
    by_pair = {(r.predecessor_id, r.successor_id): r.type for r in schedule.relationships}

    assert by_pair[("T1", "T2")] is RelationType.FS
    assert by_pair[("T2", "T3")] is RelationType.SS
    assert by_pair[("T3", "T4")] is RelationType.FF
    assert by_pair[("T4", "T5")] is RelationType.SF
    assert len(set(by_pair.values())) == 4


def test_durations_use_the_calendars_hours_per_day(schedule):
    """The sample calendar is 10 hours. Assuming 8 would read 50 hours as 6.25
    days instead of 5, rescaling the entire schedule."""
    assert schedule.default_calendar.hours_per_day == 10.0
    assert schedule.activity("T1").duration == 5.0  # 50h / 10
    assert schedule.activity("T2").duration == 10.0  # 100h / 10


def test_milestones_keep_zero_duration(schedule):
    """Clamping with max(1, ...) turns a milestone into a one-day task and
    moves every downstream date."""
    milestone = schedule.activity("T5")

    assert milestone.kind is ActivityKind.FINISH_MILESTONE
    assert milestone.kind.is_milestone
    assert milestone.duration == 0.0


def test_costs_come_from_taskrsrc_not_task(schedule):
    """TASK has no target_cost column; reading one yields zero forever."""
    assert schedule.activity("T2").budgeted_cost == 42000.0
    assert schedule.activity("T1").budgeted_cost is None


# ── the rest of the mapping ──────────────────────────────────────────────


def test_lag_is_converted_from_hours_to_days(schedule):
    ss_link = next(r for r in schedule.relationships if r.type is RelationType.SS)
    assert ss_link.lag == 2.0  # 20h on a 10-hour calendar


def test_project_long_name_comes_from_the_root_wbs_node(schedule):
    """PROJECT has no proj_name column; the long name is on the root PROJWBS."""
    assert schedule.name == "Northgate Tower Fit-Out"
    assert schedule.code == "NGT-2026"


def test_wbs_hierarchy_is_preserved(schedule):
    assert len(schedule.wbs) == 2
    child = next(n for n in schedule.wbs if n.id == "W2")
    assert child.parent_id == "W1"
    assert child.name == "Structure"


def test_notes_come_from_taskmemo(schedule):
    assert "unrecorded services" in schedule.activity("T2").notes
    assert schedule.activity("T1").notes == ""


def test_constraints_are_mapped(schedule):
    constrained = schedule.activity("T2")
    assert constrained.constraint_type is ConstraintType.START_ON_OR_AFTER
    assert constrained.constraint_date == date(2026, 9, 14)
    assert schedule.activity("T1").constraint_type is ConstraintType.NONE


def test_actuals_and_progress_are_read(schedule):
    done = schedule.activity("T1")
    assert done.actual_start == date(2026, 9, 7)
    assert done.actual_finish == date(2026, 9, 11)
    assert done.percent_complete == 100.0
    assert done.is_complete


def test_calendar_working_days_are_parsed(schedule):
    """The sample marks Monday to Friday as working, Saturday and Sunday not."""
    calendar = schedule.default_calendar
    assert calendar.working_weekdays == {0, 1, 2, 3, 4}
    assert calendar.is_working_day(date(2026, 9, 7)) is True  # Monday
    assert calendar.is_working_day(date(2026, 9, 12)) is False  # Saturday


def test_resources_and_assignments_are_read(schedule):
    assert len(schedule.resources) == 1
    assert schedule.resources[0].name == "Groundworks crew"
    assert schedule.resources[0].kind == "labor"
    assert len(schedule.assignments) == 1
    assert schedule.assignments[0].activity_id == "T2"


def test_the_schedule_validates(schedule):
    assert schedule.validate() == []


def test_a_missing_calendar_is_warned_about_not_assumed_silently():
    without = SAMPLE_XER.replace("%R\tC1\tShift 10h\t10\t50\tY", "%R\tC1\tShift\t\t\tY")
    schedule = read_xer(without)

    assert schedule.default_calendar.hours_per_day == 8.0
    assert any("day_hr_cnt" in w for w in schedule.warnings)


def test_unknown_relationship_type_warns_rather_than_passing_silently():
    mangled = SAMPLE_XER.replace("PR_SS", "PR_XX")
    schedule = read_xer(mangled)

    assert any("PR_XX" in w for w in schedule.warnings)


# ── feeding the scheduling engine ────────────────────────────────────────


def test_an_imported_schedule_can_be_scheduled(schedule):
    activities, relationships = schedule.to_cpm()
    result = calculate_cpm(activities, relationships)

    assert result.project_duration > 0
    assert "T1" in result.critical_path


def test_relationship_types_survive_into_the_engine(schedule):
    """The point of getting PR_SS right: the engine must see a real SS tie,
    because SS and FS produce different dates."""
    _, relationships = schedule.to_cpm()
    types = {r.type for r in relationships}

    assert RelationType.SS in types
    assert RelationType.FF in types
    assert RelationType.SF in types


# ── round trip ───────────────────────────────────────────────────────────


def test_write_then_read_recovers_the_schedule(schedule):
    """A writer nobody reads back is a writer nobody can trust."""
    reread = read_xer(write_xer(schedule))

    assert reread.name == schedule.name
    assert reread.code == schedule.code
    assert len(reread.activities) == len(schedule.activities)
    assert len(reread.relationships) == len(schedule.relationships)
    assert len(reread.wbs) == len(schedule.wbs)


def test_round_trip_preserves_relationship_types(schedule):
    reread = read_xer(write_xer(schedule))
    original = {(r.predecessor_id, r.successor_id): r.type for r in schedule.relationships}
    recovered = {(r.predecessor_id, r.successor_id): r.type for r in reread.relationships}

    assert recovered == original


def test_round_trip_preserves_durations_and_milestones(schedule):
    reread = read_xer(write_xer(schedule))

    for original in schedule.activities:
        recovered = reread.activity(original.id)
        assert recovered.duration == original.duration, original.id
        assert recovered.kind is original.kind, original.id


def test_round_trip_preserves_lag(schedule):
    reread = read_xer(write_xer(schedule))
    original = {(r.predecessor_id, r.successor_id): r.lag for r in schedule.relationships}
    recovered = {(r.predecessor_id, r.successor_id): r.lag for r in reread.relationships}

    assert recovered == original


def test_round_trip_preserves_dates_and_actuals(schedule):
    reread = read_xer(write_xer(schedule))

    for original in schedule.activities:
        recovered = reread.activity(original.id)
        assert recovered.early_start == original.early_start, original.id
        assert recovered.actual_start == original.actual_start, original.id
        assert recovered.actual_finish == original.actual_finish, original.id


def test_round_trip_preserves_the_calendar(schedule):
    reread = read_xer(write_xer(schedule))
    assert reread.default_calendar.hours_per_day == 10.0
    assert reread.default_calendar.working_weekdays == {0, 1, 2, 3, 4}


def test_round_trip_preserves_costs_and_notes(schedule):
    reread = read_xer(write_xer(schedule))

    assert reread.activity("T2").budgeted_cost == 42000.0
    assert "unrecorded services" in reread.activity("T2").notes


def test_round_trip_preserves_constraints(schedule):
    reread = read_xer(write_xer(schedule))
    recovered = reread.activity("T2")

    assert recovered.constraint_type is ConstraintType.START_ON_OR_AFTER
    assert recovered.constraint_date == date(2026, 9, 14)


def test_the_written_file_has_the_expected_shape(schedule):
    text = write_xer(schedule)

    assert text.startswith("ERMHDR\t")
    assert text.rstrip().endswith("%E")
    assert "%T\tTASK" in text
    assert "PR_SS" in text  # not a bare "SS"


def test_scheduling_is_identical_before_and_after_a_round_trip(schedule):
    """The strongest check: the computed schedule must not move."""
    before = calculate_cpm(*schedule.to_cpm())
    after = calculate_cpm(*read_xer(write_xer(schedule)).to_cpm())

    assert after.project_duration == before.project_duration
    assert after.critical_path == before.critical_path
    for activity_id, original in before.activities.items():
        assert after.activities[activity_id].early_start == original.early_start
        assert after.activities[activity_id].total_float == original.total_float
