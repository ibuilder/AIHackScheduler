"""Tests for Monte Carlo schedule risk analysis."""

import pytest

from core.cpm import Activity, Relationship
from core.risk import (
    Distribution,
    DurationEstimate,
    default_estimates,
    simulate,
)


def _chain(length=5, duration=10):
    activities = [Activity(f"T{i}", f"Task {i}", duration) for i in range(length)]
    links = [Relationship(f"T{i}", f"T{i + 1}") for i in range(length - 1)]
    return activities, links


def test_empty_schedule_returns_an_empty_result():
    result = simulate([])
    assert result.iterations == 0
    assert result.durations == []


def test_same_seed_gives_identical_results():
    """A forecast that changes when nobody changed the plan is not actionable."""
    activities, links = _chain()
    first = simulate(activities, links, iterations=300)
    second = simulate(activities, links, iterations=300)

    assert first.to_dict() == second.to_dict()


def test_different_seeds_give_different_results():
    activities, links = _chain()
    a = simulate(activities, links, iterations=300, seed=1)
    b = simulate(activities, links, iterations=300, seed=2)

    assert a.durations != b.durations


def test_percentiles_are_ordered():
    activities, links = _chain()
    result = simulate(activities, links, iterations=1000)

    assert (
        result.percentile(10)
        <= result.percentile(50)
        <= result.percentile(80)
        <= result.percentile(90)
    )


def test_p50_exceeds_the_deterministic_duration_for_a_right_skewed_estimate():
    """The headline finding: a single-number schedule is optimistic, because
    the default spread allows more overrun than underrun."""
    activities, links = _chain(length=8)
    result = simulate(activities, links, iterations=1500)

    assert result.percentile(50) > result.deterministic_duration
    assert result.confidence_in_deterministic < 0.5


def test_p80_is_a_later_commitment_than_p50():
    activities, links = _chain(length=8)
    result = simulate(activities, links, iterations=1500)

    assert result.percentile(80) > result.percentile(50)


def test_invalid_percentile_rejected():
    activities, links = _chain()
    result = simulate(activities, links, iterations=50)

    with pytest.raises(ValueError, match="between 0 and 100"):
        result.percentile(120)


def test_a_single_chain_makes_every_activity_always_critical():
    activities, links = _chain(length=6)
    result = simulate(activities, links, iterations=400)

    assert all(a.criticality_index == 1.0 for a in result.activities)


def test_a_dominant_path_beats_a_slack_branch():
    #  A ──┬── LONG (40) ──┬── D
    #      └── SHORT (2) ──┘
    activities = [
        Activity("A", "Start", 5),
        Activity("LONG", "Long branch", 40),
        Activity("SHORT", "Short branch", 2),
        Activity("D", "Finish", 5),
    ]
    links = [
        Relationship("A", "LONG"),
        Relationship("A", "SHORT"),
        Relationship("LONG", "D"),
        Relationship("SHORT", "D"),
    ]
    result = simulate(activities, links, iterations=800)
    index = {a.id: a.criticality_index for a in result.activities}

    assert index["LONG"] == 1.0
    assert index["SHORT"] == 0.0
    assert index["A"] == 1.0


def test_near_parallel_paths_share_criticality():
    """Two branches of similar length are each critical some of the time —
    exactly the case a single deterministic pass hides."""
    activities = [
        Activity("A", "Start", 5),
        Activity("P1", "Path one", 20),
        Activity("P2", "Path two", 20),
        Activity("D", "Finish", 5),
    ]
    links = [
        Relationship("A", "P1"),
        Relationship("A", "P2"),
        Relationship("P1", "D"),
        Relationship("P2", "D"),
    ]
    result = simulate(activities, links, iterations=1200)
    index = {a.id: a.criticality_index for a in result.activities}

    assert 0.2 < index["P1"] < 0.8
    assert 0.2 < index["P2"] < 0.8


def test_duration_sensitivity_is_positive_on_the_driving_path():
    activities, links = _chain(length=5)
    result = simulate(activities, links, iterations=1000)

    assert all(a.duration_sensitivity > 0 for a in result.activities)


def test_slack_branch_has_near_zero_sensitivity():
    activities = [
        Activity("A", "Start", 5),
        Activity("LONG", "Long branch", 40),
        Activity("SHORT", "Short branch", 2),
        Activity("D", "Finish", 5),
    ]
    links = [
        Relationship("A", "LONG"),
        Relationship("A", "SHORT"),
        Relationship("LONG", "D"),
        Relationship("SHORT", "D"),
    ]
    result = simulate(activities, links, iterations=800)
    sensitivity = {a.id: a.duration_sensitivity for a in result.activities}

    assert abs(sensitivity["SHORT"]) < 0.1
    assert sensitivity["LONG"] > 0.5


def test_both_distributions_run():
    activities, links = _chain()
    for distribution in (Distribution.PERT, Distribution.TRIANGULAR):
        result = simulate(activities, links, iterations=300, distribution=distribution)
        assert result.percentile(50) > 0


def test_pert_concentrates_more_tightly_than_triangular():
    """PERT weights the most likely value, so its spread is narrower."""
    activities, links = _chain(length=10)
    pert = simulate(activities, links, iterations=2000, distribution=Distribution.PERT)
    tri = simulate(activities, links, iterations=2000, distribution=Distribution.TRIANGULAR)

    assert pert.standard_deviation < tri.standard_deviation


def test_zero_spread_estimate_is_deterministic():
    activities = [Activity("A", "Fixed", 10)]
    estimates = [DurationEstimate("A", 10, 10, 10)]
    result = simulate(activities, estimates=estimates, iterations=200)

    assert set(result.durations) == {10}
    assert result.standard_deviation == 0.0


def test_unordered_estimate_rejected():
    with pytest.raises(ValueError, match="not ordered"):
        DurationEstimate("A", optimistic=10, most_likely=5, pessimistic=20)


def test_negative_estimate_rejected():
    with pytest.raises(ValueError, match="negative bound"):
        DurationEstimate("A", optimistic=-1, most_likely=5, pessimistic=20)


def test_missing_estimate_is_an_error_not_a_silent_default():
    activities, links = _chain(length=3)
    partial = [DurationEstimate("T0", 8, 10, 14)]

    with pytest.raises(ValueError, match="No duration estimate for"):
        simulate(activities, links, estimates=partial, iterations=10)


def test_default_estimates_bracket_the_planned_duration():
    activities, _ = _chain(length=3, duration=20)
    estimates = default_estimates(activities)

    for estimate in estimates:
        assert estimate.optimistic <= 20 <= estimate.pessimistic
        # Right-skewed: more room to overrun than to come in early.
        assert estimate.pessimistic - 20 > 20 - estimate.optimistic


def test_default_estimate_factors_validated():
    activities, _ = _chain(length=2)
    with pytest.raises(ValueError, match="optimistic_factor"):
        default_estimates(activities, optimistic_factor=1.5)


def test_iterations_must_be_positive():
    activities, links = _chain()
    with pytest.raises(ValueError, match="at least 1"):
        simulate(activities, links, iterations=0)


def test_result_serialises_to_json_safe_dict():
    activities, links = _chain()
    payload = simulate(activities, links, iterations=200).to_dict()

    assert set(payload["percentiles"]) == {"p10", "p50", "p80", "p90"}
    assert {"id", "name", "criticality_index", "duration_sensitivity"} <= set(
        payload["activities"][0]
    )
    # Sorted by criticality, most critical first.
    indices = [a["criticality_index"] for a in payload["activities"]]
    assert indices == sorted(indices, reverse=True)
