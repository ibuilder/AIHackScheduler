"""Tests for the CPM engine.

The worked examples use small networks whose answers can be checked by hand,
which is the only way to be confident a scheduling engine is right.
"""

import pytest

from core.cpm import (
    Activity,
    Relationship,
    RelationType,
    ScheduleCycleError,
    calculate_cpm,
    longest_path,
)


def test_empty_schedule():
    result = calculate_cpm([])
    assert result.project_duration == 0
    assert result.critical_path == []


def test_single_activity():
    result = calculate_cpm([Activity("A", "Mobilise", 5)])
    a = result.activities["A"]
    assert (a.early_start, a.early_finish) == (0, 5)
    assert (a.late_start, a.late_finish) == (0, 5)
    assert a.total_float == 0
    assert result.project_duration == 5
    assert result.critical_path == ["A"]


def test_simple_chain():
    activities = [Activity("A", "Excavate", 3), Activity("B", "Pour", 4), Activity("C", "Cure", 7)]
    rels = [Relationship("A", "B"), Relationship("B", "C")]
    result = calculate_cpm(activities, rels)

    assert result.project_duration == 14
    assert result.critical_path == ["A", "B", "C"]
    assert result.activities["B"].early_start == 3
    assert result.activities["C"].early_start == 7
    assert all(a.total_float == 0 for a in result.activities.values())


def test_declaration_order_does_not_change_the_answer():
    """The original implementation broke here: it walked activities in list
    order, so a predecessor declared after its successor was read before it
    had been computed."""
    activities = [Activity("C", "Cure", 7), Activity("A", "Excavate", 3), Activity("B", "Pour", 4)]
    rels = [Relationship("A", "B"), Relationship("B", "C")]
    result = calculate_cpm(activities, rels)

    assert result.project_duration == 14
    assert result.activities["C"].early_start == 7
    assert result.activities["A"].early_start == 0


def test_parallel_paths_and_float():
    #        ┌── B (2) ──┐
    #  A (3) ┤            ├── D (1)
    #        └── C (6) ──┘
    activities = [
        Activity("A", "Site prep", 3),
        Activity("B", "Short branch", 2),
        Activity("C", "Long branch", 6),
        Activity("D", "Tie-in", 1),
    ]
    rels = [
        Relationship("A", "B"),
        Relationship("A", "C"),
        Relationship("B", "D"),
        Relationship("C", "D"),
    ]
    result = calculate_cpm(activities, rels)

    assert result.project_duration == 10  # 3 + 6 + 1
    assert result.activities["B"].total_float == 4  # 6 - 2
    assert result.activities["C"].total_float == 0
    assert result.critical_path == ["A", "C", "D"]
    assert longest_path(result, rels) == ["A", "C", "D"]


def test_free_float_differs_from_total_float():
    #  A (2) ── B (2) ──┐
    #                    ├── D (1)
    #  C (10) ───────────┘
    activities = [
        Activity("A", "A", 2),
        Activity("B", "B", 2),
        Activity("C", "C", 10),
        Activity("D", "D", 1),
    ]
    rels = [Relationship("A", "B"), Relationship("B", "D"), Relationship("C", "D")]
    result = calculate_cpm(activities, rels)

    # A can slip 6 days before D moves, but not without eating B's slack, so
    # A's free float is 0 while its total float is 6.
    assert result.activities["A"].total_float == 6
    assert result.activities["A"].free_float == 0
    assert result.activities["B"].free_float == 6


def test_finish_to_start_lag():
    activities = [Activity("A", "Pour slab", 2), Activity("B", "Strip forms", 1)]
    rels = [Relationship("A", "B", RelationType.FS, lag=7)]  # 7-day cure
    result = calculate_cpm(activities, rels)

    assert result.activities["B"].early_start == 9
    assert result.project_duration == 10


def test_start_to_start_relationship():
    activities = [Activity("A", "Trench", 10), Activity("B", "Lay pipe", 10)]
    rels = [Relationship("A", "B", RelationType.SS, lag=2)]
    result = calculate_cpm(activities, rels)

    assert result.activities["B"].early_start == 2
    assert result.project_duration == 12


def test_finish_to_finish_relationship():
    activities = [Activity("A", "Rough-in", 10), Activity("B", "Inspect", 3)]
    rels = [Relationship("A", "B", RelationType.FF, lag=1)]
    result = calculate_cpm(activities, rels)

    # B must finish 1 day after A finishes, so B finishes at 11 and starts at 8.
    assert result.activities["B"].early_finish == 11
    assert result.activities["B"].early_start == 8


def test_start_to_finish_relationship():
    activities = [Activity("A", "New system live", 4), Activity("B", "Old system runs", 6)]
    rels = [Relationship("A", "B", RelationType.SF, lag=0)]
    result = calculate_cpm(activities, rels)

    # B cannot finish before A starts.
    assert result.activities["B"].early_finish >= result.activities["A"].early_start


def test_negative_lag_pulls_successor_forward():
    activities = [Activity("A", "A", 10), Activity("B", "B", 5)]
    rels = [Relationship("A", "B", RelationType.FS, lag=-3)]
    result = calculate_cpm(activities, rels)

    assert result.activities["B"].early_start == 7
    assert result.project_duration == 12


def test_start_constraint_is_honoured():
    activities = [Activity("A", "A", 2), Activity("B", "Permit-gated", 3, constraint_start=10)]
    rels = [Relationship("A", "B")]
    result = calculate_cpm(activities, rels)

    assert result.activities["B"].early_start == 10
    assert result.project_duration == 13


def test_cycle_is_detected_and_named():
    activities = [Activity("A", "A", 1), Activity("B", "B", 1), Activity("C", "C", 1)]
    rels = [Relationship("A", "B"), Relationship("B", "C"), Relationship("C", "A")]

    with pytest.raises(ScheduleCycleError) as exc:
        calculate_cpm(activities, rels)

    assert set(exc.value.cycle) >= {"A", "B", "C"}


def test_self_dependency_rejected():
    with pytest.raises(ValueError, match="depends on itself"):
        calculate_cpm([Activity("A", "A", 1)], [Relationship("A", "A")])


def test_unknown_activity_in_relationship_rejected():
    with pytest.raises(ValueError, match="unknown predecessor"):
        calculate_cpm([Activity("A", "A", 1)], [Relationship("Z", "A")])


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError, match="Duplicate activity ids"):
        calculate_cpm([Activity("A", "A", 1), Activity("A", "Also A", 2)])


def test_negative_duration_rejected():
    with pytest.raises(ValueError, match="negative duration"):
        Activity("A", "A", -1)


def test_milestone_has_zero_duration():
    activities = [Activity("A", "Work", 5), Activity("M", "Substantial completion", 0)]
    rels = [Relationship("A", "M")]
    result = calculate_cpm(activities, rels)

    assert result.activities["M"].early_start == 5
    assert result.activities["M"].early_finish == 5
    assert result.project_duration == 5


def test_disconnected_activities_still_schedule():
    activities = [Activity("A", "A", 4), Activity("B", "B", 9)]
    result = calculate_cpm(activities, [])

    assert result.project_duration == 9
    assert result.activities["A"].total_float == 5
    assert result.critical_path == ["B"]


def test_large_network_completes():
    """A 500-activity chain of parallel pairs — guards against the quadratic
    dependency scans in the original implementation."""
    activities = [Activity(f"T{i}", f"Task {i}", 2) for i in range(500)]
    rels = [Relationship(f"T{i}", f"T{i + 1}") for i in range(499)]
    result = calculate_cpm(activities, rels)

    assert result.project_duration == 1000
    assert len(result.critical_path) == 500
