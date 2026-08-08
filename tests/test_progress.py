"""Tests for baseline measurement: BEI, variance, and what counts as behind."""

from core.progress import ActivityProgress, build_report


def _activity(aid, baseline=None, start=None, finish=None, forecast=None):
    return ActivityProgress(
        id=aid,
        name=f"Activity {aid}",
        baseline_finish=baseline,
        actual_start=start,
        actual_finish=finish,
        forecast_finish=forecast,
    )


def test_no_baseline_means_nothing_can_be_measured():
    report = build_report([_activity("A"), _activity("B")], data_date=10)

    assert report.has_baseline is False
    assert report.baseline_execution_index is None


def test_bei_is_none_when_nothing_was_due_yet():
    """An empty denominator is unknown, not a perfect score."""
    report = build_report([_activity("A", baseline=50)], data_date=10)

    assert report.due_by_data_date == []
    assert report.baseline_execution_index is None


def test_bei_counts_completed_against_due():
    activities = [
        _activity("A", baseline=5, start=0, finish=5),
        _activity("B", baseline=8, start=5, finish=9),
        _activity("C", baseline=10, start=9),  # started, not finished
        _activity("D", baseline=12),  # due, never started
        _activity("E", baseline=40),  # not due yet
    ]
    report = build_report(activities, data_date=20)

    assert len(report.due_by_data_date) == 4
    assert len(report.completed) == 2
    assert report.baseline_execution_index == 0.5


def test_finish_variance_is_signed():
    late = _activity("A", baseline=10, finish=14)
    early = _activity("B", baseline=10, finish=7)
    on_time = _activity("C", baseline=10, finish=10)

    assert late.finish_variance == 4
    assert early.finish_variance == -3
    assert on_time.finish_variance == 0


def test_variance_is_unknown_without_both_dates():
    assert _activity("A", finish=14).finish_variance is None
    assert _activity("B", baseline=10).finish_variance is None


def test_behind_includes_due_work_that_never_started():
    """DCMA check 11 counts only completed-but-late activities. An activity
    that was due and never started is the more urgent problem, so the progress
    report counts it too."""
    activities = [
        _activity("LATE", baseline=5, start=0, finish=9),
        _activity("NEVER_STARTED", baseline=5),
        _activity("ON_TIME", baseline=5, start=0, finish=5),
    ]
    report = build_report(activities, data_date=20)

    behind = {a.id for a in report.behind}
    assert behind == {"LATE", "NEVER_STARTED"}
    assert [a.id for a in report.not_started_but_due] == ["NEVER_STARTED"]


def test_future_actuals_are_flagged_as_invalid():
    """Work cannot have been completed after the data date."""
    activities = [
        _activity("A", baseline=5, start=0, finish=5),
        _activity("B", baseline=8, start=6, finish=30),  # finished in the future
    ]
    report = build_report(activities, data_date=20)

    assert [a.id for a in report.invalid_actuals] == ["B"]


def test_average_finish_variance_only_counts_completed_work():
    activities = [
        _activity("A", baseline=10, finish=12),  # +2
        _activity("B", baseline=10, finish=14),  # +4
        _activity("C", baseline=10),  # not finished, excluded
    ]
    report = build_report(activities, data_date=20)

    assert report.average_finish_variance == 3.0


def test_worst_slippage_ranks_forecast_variance():
    activities = [
        _activity("SMALL", baseline=10, forecast=12),
        _activity("BIG", baseline=10, forecast=40),
        _activity("EARLY", baseline=10, forecast=8),  # ahead, excluded
    ]
    report = build_report(activities, data_date=5)

    assert [a.id for a in report.worst_slippage] == ["BIG", "SMALL"]


def test_forecast_variance_moves_before_an_activity_is_late():
    """The early-warning number: the plan has slipped though nothing is late
    yet, because the activity is not due for another 30 days."""
    activity = _activity("A", baseline=50, forecast=58)

    assert activity.forecast_variance == 8
    assert activity.finish_variance is None
    assert activity.is_behind(data_date=10) is False


def test_report_serialises_to_json_safe_dict():
    activities = [
        _activity("A", baseline=5, start=0, finish=5),
        _activity("B", baseline=8, start=5, finish=12, forecast=12),
    ]
    payload = build_report(activities, data_date=20).to_dict()

    assert payload["activities_due"] == 2
    assert payload["activities_complete"] == 2
    assert payload["baseline_execution_index"] == 1.0
    assert {"id", "name", "started", "finish_variance_days"} <= set(payload["behind_activities"][0])
