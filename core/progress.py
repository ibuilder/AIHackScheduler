"""Measuring a schedule against its baseline.

CPM says where the plan goes. This module says whether the plan is being
followed — which needs three things the network alone does not carry: an
approved baseline, recorded actuals, and a data date to measure from.

Everything here is working-day offsets, consistent with :mod:`core.cpm`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActivityProgress:
    """One activity's standing against its baseline."""

    id: str
    name: str
    baseline_finish: int | None = None
    actual_start: int | None = None
    actual_finish: int | None = None
    forecast_finish: int | None = None

    @property
    def is_complete(self) -> bool:
        return self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        return self.actual_start is not None

    @property
    def finish_variance(self) -> int | None:
        """Working days late finishing. Negative is early."""
        if self.actual_finish is None or self.baseline_finish is None:
            return None
        return self.actual_finish - self.baseline_finish

    @property
    def forecast_variance(self) -> int | None:
        """Working days the forecast has slipped against baseline."""
        if self.forecast_finish is None or self.baseline_finish is None:
            return None
        return self.forecast_finish - self.baseline_finish

    def was_due_by(self, data_date: int) -> bool:
        return self.baseline_finish is not None and self.baseline_finish <= data_date

    def is_behind(self, data_date: int) -> bool:
        """Due by the data date and either finished late or not finished.

        Deliberately broader than DCMA check 11, which counts only *completed*
        activities that finished after baseline. An activity that was due and
        simply never started is invisible to that check but is the more urgent
        problem, so it is counted here.
        """
        if not self.was_due_by(data_date):
            return False
        if self.actual_finish is None:
            return True
        return self.actual_finish > self.baseline_finish


@dataclass
class ProgressReport:
    """Baseline Execution Index and the variance behind it."""

    data_date: int
    activities: list[ActivityProgress] = field(default_factory=list)

    @property
    def has_baseline(self) -> bool:
        return any(a.baseline_finish is not None for a in self.activities)

    @property
    def has_actuals(self) -> bool:
        return any(
            a.actual_start is not None or a.actual_finish is not None for a in self.activities
        )

    @property
    def due_by_data_date(self) -> list[ActivityProgress]:
        return [a for a in self.activities if a.was_due_by(self.data_date)]

    @property
    def completed(self) -> list[ActivityProgress]:
        return [a for a in self.activities if a.is_complete]

    @property
    def behind(self) -> list[ActivityProgress]:
        return [a for a in self.activities if a.is_behind(self.data_date)]

    @property
    def not_started_but_due(self) -> list[ActivityProgress]:
        """Due by the data date with no recorded start at all."""
        return [a for a in self.activities if a.was_due_by(self.data_date) and not a.is_started]

    @property
    def invalid_actuals(self) -> list[ActivityProgress]:
        """Actuals recorded in the future. Work cannot be done after today."""
        return [
            a
            for a in self.activities
            if (a.actual_finish is not None and a.actual_finish > self.data_date)
            or (a.actual_start is not None and a.actual_start > self.data_date)
        ]

    @property
    def baseline_execution_index(self) -> float | None:
        """BEI — activities actually complete ÷ activities that should be.

        Below 1.0 means the project is completing work more slowly than
        planned. Returns ``None`` when nothing was due yet, because a ratio
        over an empty denominator is not 1.0, it is unknown.
        """
        due = self.due_by_data_date
        if not due:
            return None
        done = sum(1 for a in due if a.is_complete)
        return done / len(due)

    @property
    def average_finish_variance(self) -> float | None:
        """Mean working days late across completed activities."""
        variances = [a.finish_variance for a in self.completed if a.finish_variance is not None]
        if not variances:
            return None
        return sum(variances) / len(variances)

    @property
    def worst_slippage(self) -> list[ActivityProgress]:
        """Activities whose forecast has slipped furthest, worst first."""
        slipped = [
            a
            for a in self.activities
            if a.forecast_variance is not None and a.forecast_variance > 0
        ]
        return sorted(slipped, key=lambda a: -a.forecast_variance)

    def to_dict(self) -> dict:
        bei = self.baseline_execution_index
        avg = self.average_finish_variance
        return {
            "data_date_offset": self.data_date,
            "has_baseline": self.has_baseline,
            "has_actuals": self.has_actuals,
            "activities_due": len(self.due_by_data_date),
            "activities_complete": len(self.completed),
            "activities_behind": len(self.behind),
            "activities_not_started_but_due": len(self.not_started_but_due),
            "baseline_execution_index": None if bei is None else round(bei, 3),
            "average_finish_variance_days": None if avg is None else round(avg, 1),
            "worst_slippage": [
                {
                    "id": a.id,
                    "name": a.name,
                    "forecast_variance_days": a.forecast_variance,
                }
                for a in self.worst_slippage[:10]
            ],
            "behind_activities": [
                {
                    "id": a.id,
                    "name": a.name,
                    "started": a.is_started,
                    "finish_variance_days": a.finish_variance,
                }
                for a in self.behind[:20]
            ],
        }


def build_report(activities: list[ActivityProgress], data_date: int) -> ProgressReport:
    return ProgressReport(data_date=data_date, activities=list(activities))
