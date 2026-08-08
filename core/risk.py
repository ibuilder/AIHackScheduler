"""Monte Carlo schedule risk analysis.

A CPM run gives one number: the duration if every activity takes exactly as
long as estimated. No activity ever does. This module samples durations from
three-point estimates, reruns the network thousands of times, and reports the
distribution of finish dates that results.

It is deterministic given a seed, needs no external service, and every figure
it produces can be traced back to the network in :mod:`core.cpm`. That is the
credible version of "predictive analytics" for a schedule — as opposed to
asking a language model to guess a completion date.

Two outputs matter most to a planner:

* **P80 duration** — the date you can commit to with 80% confidence. The
  deterministic CPM figure is typically nearer P30, which is why single-number
  schedules are optimistic so reliably.
* **Criticality index** — how often an activity landed on the critical path
  across all iterations. An activity critical in 60% of runs needs managing
  even though a single deterministic pass calls it non-critical.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field
from enum import Enum

from core.cpm import Activity, Relationship, ScheduleCycleError, calculate_cpm

# Default spread applied when an activity carries no explicit three-point
# estimate. Construction durations skew right: work overruns more often, and
# by more, than it comes in early.
DEFAULT_OPTIMISTIC_FACTOR = 0.90
DEFAULT_PESSIMISTIC_FACTOR = 1.45


class Distribution(str, Enum):
    """How a duration is sampled between its optimistic and pessimistic bounds."""

    TRIANGULAR = "triangular"
    # PERT (beta) concentrates probability around the most likely value rather
    # than spreading it linearly, which matches observed durations better.
    PERT = "pert"


@dataclass(frozen=True)
class DurationEstimate:
    """A three-point estimate for one activity, in working days."""

    activity_id: str
    optimistic: float
    most_likely: float
    pessimistic: float

    def __post_init__(self) -> None:
        if not self.optimistic <= self.most_likely <= self.pessimistic:
            raise ValueError(
                f"Estimate for {self.activity_id!r} is not ordered: "
                f"{self.optimistic} / {self.most_likely} / {self.pessimistic}"
            )
        if self.optimistic < 0:
            raise ValueError(f"Estimate for {self.activity_id!r} has a negative bound")

    @property
    def spread(self) -> float:
        return self.pessimistic - self.optimistic


@dataclass
class ActivityRisk:
    """Per-activity results across the whole simulation."""

    id: str
    name: str
    criticality_index: float
    mean_duration: float
    duration_sensitivity: float

    @property
    def is_persistently_critical(self) -> bool:
        return self.criticality_index >= 0.5


@dataclass
class RiskResult:
    """The outcome of a simulation."""

    iterations: int
    deterministic_duration: int
    durations: list[int] = field(default_factory=list)
    activities: list[ActivityRisk] = field(default_factory=list)

    def percentile(self, p: float) -> int:
        """The duration at percentile ``p`` (0-100), rounded up to whole days.

        Rounded up because a schedule commitment is met or missed on a whole
        day; a P80 of 271.2 days is not met on day 271.
        """
        if not self.durations:
            return 0
        if not 0 <= p <= 100:
            raise ValueError(f"Percentile must be between 0 and 100, got {p}")
        ordered = sorted(self.durations)
        if p == 100:
            return ordered[-1]
        index = (p / 100) * (len(ordered) - 1)
        low = math.floor(index)
        high = math.ceil(index)
        if low == high:
            return ordered[low]
        weight = index - low
        return math.ceil(ordered[low] * (1 - weight) + ordered[high] * weight)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.durations) if self.durations else 0.0

    @property
    def standard_deviation(self) -> float:
        return statistics.pstdev(self.durations) if len(self.durations) > 1 else 0.0

    @property
    def confidence_in_deterministic(self) -> float:
        """Probability of finishing by the deterministic CPM duration.

        Usually uncomfortably low, which is the point of running this at all.
        """
        if not self.durations:
            return 0.0
        met = sum(1 for d in self.durations if d <= self.deterministic_duration)
        return met / len(self.durations)

    def to_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "deterministic_duration_days": self.deterministic_duration,
            "confidence_in_deterministic": round(self.confidence_in_deterministic, 3),
            "mean_duration_days": round(self.mean, 1),
            "standard_deviation_days": round(self.standard_deviation, 1),
            "percentiles": {
                "p10": self.percentile(10),
                "p50": self.percentile(50),
                "p80": self.percentile(80),
                "p90": self.percentile(90),
            },
            "activities": [
                {
                    "id": a.id,
                    "name": a.name,
                    "criticality_index": round(a.criticality_index, 3),
                    "mean_duration_days": round(a.mean_duration, 1),
                    "duration_sensitivity": round(a.duration_sensitivity, 3),
                }
                for a in sorted(self.activities, key=lambda a: -a.criticality_index)
            ],
        }


def default_estimates(
    activities: list[Activity],
    optimistic_factor: float = DEFAULT_OPTIMISTIC_FACTOR,
    pessimistic_factor: float = DEFAULT_PESSIMISTIC_FACTOR,
) -> list[DurationEstimate]:
    """Derive three-point estimates from planned durations.

    A fallback for schedules that carry only a single duration per activity,
    which is most of them. Real estimates from the team are better and should
    replace these wherever they exist.
    """
    if optimistic_factor > 1 or pessimistic_factor < 1:
        raise ValueError("optimistic_factor must be <= 1 and pessimistic_factor >= 1")

    return [
        DurationEstimate(
            activity_id=a.id,
            optimistic=a.duration * optimistic_factor,
            most_likely=float(a.duration),
            pessimistic=a.duration * pessimistic_factor,
        )
        for a in activities
    ]


def _sample(estimate: DurationEstimate, rng: random.Random, distribution: Distribution) -> int:
    """Draw one duration, rounded to whole working days."""
    if estimate.spread == 0:
        return int(round(estimate.most_likely))

    if distribution is Distribution.TRIANGULAR:
        value = rng.triangular(estimate.optimistic, estimate.pessimistic, estimate.most_likely)
    else:
        # PERT: a beta distribution shaped by the three points. With the
        # conventional lambda of 4 the shape parameters reduce to a closed
        # form, and a symmetric estimate yields beta(3, 3) as expected.
        mean = (estimate.optimistic + 4 * estimate.most_likely + estimate.pessimistic) / 6
        alpha = 6 * (mean - estimate.optimistic) / estimate.spread
        beta = 6 * (estimate.pessimistic - mean) / estimate.spread
        value = estimate.optimistic + rng.betavariate(alpha, beta) * estimate.spread

    return max(0, int(round(value)))


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Correlation coefficient, returning 0.0 when either series is constant."""
    if len(xs) < 2:
        return 0.0
    mean_x, mean_y = statistics.fmean(xs), statistics.fmean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def simulate(
    activities: list[Activity],
    relationships: list[Relationship] = (),
    *,
    estimates: list[DurationEstimate] | None = None,
    iterations: int = 2000,
    distribution: Distribution = Distribution.PERT,
    seed: int | None = 12345,
) -> RiskResult:
    """Run the network ``iterations`` times with sampled durations.

    ``seed`` defaults to a fixed value so that the same schedule produces the
    same figures on every run. A forecast that changes when nobody changed the
    plan is not a forecast anyone can act on. Pass ``seed=None`` for genuinely
    random draws.
    """
    if not activities:
        return RiskResult(iterations=0, deterministic_duration=0)
    if iterations < 1:
        raise ValueError(f"iterations must be at least 1, got {iterations}")

    relationships = list(relationships)
    baseline = calculate_cpm(activities, relationships)  # raises on a bad network

    estimate_map = {
        e.activity_id: e
        for e in (estimates if estimates is not None else default_estimates(activities))
    }
    missing = [a.id for a in activities if a.id not in estimate_map]
    if missing:
        raise ValueError(f"No duration estimate for: {', '.join(sorted(missing))}")

    rng = random.Random(seed)
    durations: list[int] = []
    critical_counts = {a.id: 0 for a in activities}
    sampled_durations: dict[str, list[float]] = {a.id: [] for a in activities}

    for _ in range(iterations):
        sampled = [
            Activity(
                a.id, a.name, _sample(estimate_map[a.id], rng, distribution), a.constraint_start
            )
            for a in activities
        ]
        for a in sampled:
            sampled_durations[a.id].append(float(a.duration))

        try:
            run = calculate_cpm(sampled, relationships)
        except ScheduleCycleError:  # pragma: no cover - baseline already validated
            raise

        durations.append(run.project_duration)
        for aid in run.critical_path:
            critical_counts[aid] += 1

    project_durations = [float(d) for d in durations]
    activity_risks = [
        ActivityRisk(
            id=a.id,
            name=a.name,
            criticality_index=critical_counts[a.id] / iterations,
            mean_duration=statistics.fmean(sampled_durations[a.id]),
            # How strongly this activity's duration drove the project's.
            # High sensitivity with low criticality means an activity that
            # only sometimes matters — but matters a great deal when it does.
            duration_sensitivity=_pearson(sampled_durations[a.id], project_durations),
        )
        for a in activities
    ]

    return RiskResult(
        iterations=iterations,
        deterministic_duration=baseline.project_duration,
        durations=durations,
        activities=activity_risks,
    )
