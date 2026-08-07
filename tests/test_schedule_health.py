"""Tests for the DCMA 14-point assessment."""

from core.cpm import Activity, Relationship, RelationType
from core.schedule_health import assess_schedule


def _check(report, number):
    return next(c for c in report.checks if c.number == number)


def _clean_network(size=25):
    """A tidy chain: full logic, all FS, no lags, no constraints."""
    activities = [Activity(f"T{i}", f"Task {i}", 5) for i in range(size)]
    rels = [Relationship(f"T{i}", f"T{i + 1}") for i in range(size - 1)]
    return activities, rels


def test_all_fourteen_checks_are_reported():
    activities, rels = _clean_network()
    report = assess_schedule(activities, rels)
    assert [c.number for c in report.checks] == list(range(1, 15))


def test_clean_schedule_passes_every_runnable_check():
    activities, rels = _clean_network()
    report = assess_schedule(activities, rels)

    assert report.failures == []
    assert report.grade == "A"
    assert report.is_optimisable


def test_checks_needing_actuals_are_skipped_not_passed():
    activities, rels = _clean_network()
    report = assess_schedule(activities, rels)

    for number in (9, 11, 14):
        assert _check(report, number).status == "skipped"
    # Skipped checks must not inflate the score.
    assert all(c.passed is not None for c in report.assessed)


def test_dangling_activity_fails_the_logic_check():
    activities, rels = _clean_network(10)
    activities.append(Activity("ORPHAN", "Forgotten scope", 5))
    report = assess_schedule(activities, rels)

    logic = _check(report, 1)
    assert logic.status == "fail"
    assert "ORPHAN" in logic.offenders
    assert not report.is_optimisable  # check 1 blocks optimisation


def test_leads_are_flagged():
    activities, rels = _clean_network(10)
    rels[0] = Relationship("T0", "T1", RelationType.FS, lag=-2)
    report = assess_schedule(activities, rels)

    assert _check(report, 2).status == "fail"


def test_excessive_lags_are_flagged():
    activities, rels = _clean_network(10)
    for i in range(4):
        rels[i] = Relationship(f"T{i}", f"T{i + 1}", RelationType.FS, lag=3)
    report = assess_schedule(activities, rels)

    lags = _check(report, 3)
    assert lags.status == "fail"
    assert lags.value > 5.0


def test_non_fs_relationships_are_flagged():
    activities, rels = _clean_network(10)
    for i in range(5):
        rels[i] = Relationship(f"T{i}", f"T{i + 1}", RelationType.SS)
    report = assess_schedule(activities, rels)

    assert _check(report, 4).status == "fail"


def test_hard_constraints_are_flagged():
    activities, rels = _clean_network(10)
    activities[3] = Activity("T3", "Task 3", 5, constraint_start=40)
    activities[4] = Activity("T4", "Task 4", 5, constraint_start=60)
    report = assess_schedule(activities, rels)

    constraints = _check(report, 5)
    assert constraints.status == "fail"
    assert set(constraints.offenders) == {"T3", "T4"}


def test_high_float_is_flagged():
    # One long spine plus several tiny disconnected tasks with huge float.
    activities = [Activity("SPINE", "Long spine", 200)]
    activities += [Activity(f"F{i}", f"Floater {i}", 1) for i in range(5)]
    report = assess_schedule(activities, [])

    high_float = _check(report, 6)
    assert high_float.status == "fail"
    assert "F0" in high_float.offenders


def test_high_duration_is_flagged():
    activities, rels = _clean_network(10)
    activities[2] = Activity("T2", "Task 2", 90)
    activities[6] = Activity("T6", "Task 6", 120)
    report = assess_schedule(activities, rels)

    assert _check(report, 8).status == "fail"


def test_critical_path_test_passes_on_sound_logic():
    activities, rels = _clean_network()
    cpt = _check(assess_schedule(activities, rels), 12)

    assert cpt.status == "pass"
    assert cpt.value == 600.0


def test_cpli_is_computed():
    activities, rels = _clean_network()
    cpli = _check(assess_schedule(activities, rels), 13)

    assert cpli.status == "pass"
    assert cpli.value == 1.0


def test_baseline_and_actuals_enable_the_remaining_checks():
    activities, rels = _clean_network(10)
    baseline = {f"T{i}": (i + 1) * 5 for i in range(10)}
    actual = {f"T{i}": (i + 1) * 5 for i in range(4)}

    report = assess_schedule(
        activities,
        rels,
        baseline_finish=baseline,
        actual_finish=actual,
        resourced_activity_ids=[a.id for a in activities],
        data_date_offset=20,
    )

    for number in (9, 10, 11, 14):
        assert _check(report, number).status != "skipped"
    assert _check(report, 14).value == 1.0  # all four due activities are done


def test_missed_tasks_detected_against_baseline():
    activities, rels = _clean_network(10)
    baseline = {f"T{i}": (i + 1) * 5 for i in range(10)}
    actual = {f"T{i}": (i + 1) * 5 + 10 for i in range(4)}  # every one slipped

    report = assess_schedule(
        activities, rels, baseline_finish=baseline, actual_finish=actual, data_date_offset=60
    )
    assert _check(report, 11).status == "fail"


def test_unresourced_activities_flagged():
    activities, rels = _clean_network(10)
    report = assess_schedule(activities, rels, resourced_activity_ids=["T0", "T1"])

    resources = _check(report, 10)
    assert resources.status == "fail"
    assert "T5" in resources.offenders


def test_report_serialises_to_json_safe_dict():
    activities, rels = _clean_network()
    payload = assess_schedule(activities, rels).to_dict()

    assert payload["grade"] == "A"
    assert payload["optimisable"] is True
    assert len(payload["checks"]) == 14
    assert {"number", "name", "status", "value", "threshold", "detail", "offenders"} <= set(
        payload["checks"][0]
    )


def test_score_ignores_skipped_checks():
    activities, rels = _clean_network()
    report = assess_schedule(activities, rels)

    runnable = len(report.assessed)
    assert runnable < 14  # some were skipped
    assert report.score == 100.0
