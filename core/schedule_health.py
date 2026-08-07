"""DCMA 14-Point schedule quality assessment.

The Defense Contract Management Agency's 14-point check is the closest thing
the industry has to a shared definition of "is this schedule trustworthy?".
It is used well beyond defence work — infrastructure, energy, and commercial
construction all lean on it to tell a genuine planning instrument apart from a
document produced to satisfy a contract clause.

Optimising a schedule that fails these checks produces confident nonsense, so
this module runs *before* any optimisation and gates it.

Checks 1-8 and 13 are computable from the logic network alone. Checks 9-12 and
14 need baseline dates and progress actuals; they are reported as ``skipped``
with a reason when that data is not supplied, rather than silently passing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from core.cpm import (
    Activity,
    Relationship,
    RelationType,
    ScheduleResult,
    calculate_cpm,
)

# DCMA thresholds. Expressed as fractions where the check is a percentage.
MAX_MISSING_LOGIC = 0.05
MAX_LEADS = 0.0
MAX_LAGS = 0.05
MIN_FS_RELATIONSHIPS = 0.90
MAX_HARD_CONSTRAINTS = 0.05
MAX_HIGH_FLOAT = 0.05
MAX_NEGATIVE_FLOAT = 0.0
MAX_HIGH_DURATION = 0.05
MAX_INVALID_DATES = 0.0
MAX_MISSING_RESOURCES = 0.0
MAX_MISSED_TASKS = 0.05
MIN_CPLI = 0.95
MIN_BEI = 0.95

HIGH_FLOAT_DAYS = 44
HIGH_DURATION_DAYS = 44


@dataclass
class CheckResult:
    """One of the fourteen checks."""

    number: int
    name: str
    passed: bool | None  # None when the check could not be run
    value: float | None
    threshold: str
    detail: str
    offenders: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.passed is None:
            return "skipped"
        return "pass" if self.passed else "fail"


@dataclass
class HealthReport:
    """The full assessment plus a headline grade."""

    checks: list[CheckResult] = field(default_factory=list)
    schedule: ScheduleResult | None = None

    @property
    def assessed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.passed is not None]

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if c.passed is False]

    @property
    def score(self) -> float:
        """Percentage of runnable checks that passed."""
        runnable = self.assessed
        if not runnable:
            return 0.0
        return 100.0 * sum(1 for c in runnable if c.passed) / len(runnable)

    @property
    def grade(self) -> str:
        score = self.score
        if score >= 90:
            return "A"
        if score >= 80:
            return "B"
        if score >= 70:
            return "C"
        if score >= 60:
            return "D"
        return "F"

    @property
    def is_optimisable(self) -> bool:
        """Whether the schedule's logic is sound enough to optimise against.

        Missing logic, circular-looking float, and negative float all corrupt
        the critical path, which every optimisation decision depends on.
        """
        blocking = {1, 7, 13}
        return not any(c.number in blocking and c.passed is False for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "grade": self.grade,
            "score": round(self.score, 1),
            "optimisable": self.is_optimisable,
            "checks": [
                {
                    "number": c.number,
                    "name": c.name,
                    "status": c.status,
                    "value": c.value,
                    "threshold": c.threshold,
                    "detail": c.detail,
                    "offenders": c.offenders[:20],
                }
                for c in self.checks
            ],
        }


def _pct(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def assess_schedule(
    activities: Sequence[Activity],
    relationships: Sequence[Relationship] = (),
    *,
    result: ScheduleResult | None = None,
    baseline_finish: dict[str, int] | None = None,
    actual_finish: dict[str, int] | None = None,
    resourced_activity_ids: Sequence[str] | None = None,
    data_date_offset: int = 0,
) -> HealthReport:
    """Run the DCMA 14-point assessment.

    ``baseline_finish``/``actual_finish`` map activity id to a working-day
    offset. Supply them to enable checks 9, 11, 12 and 14.
    """
    if result is None:
        result = calculate_cpm(activities, relationships)

    relationships = list(relationships)
    activities = list(activities)
    n_act = len(activities)
    n_rel = len(relationships)
    report = HealthReport(schedule=result)
    add = report.checks.append

    ids = [a.id for a in activities]
    has_pred = {rel.successor for rel in relationships}
    has_succ = {rel.predecessor for rel in relationships}

    # --- 1. Logic -----------------------------------------------------------
    # Exactly one activity may legitimately open the schedule with no
    # predecessor, and one may close it with no successor. Those are the
    # project start and the project finish. Every other open end is a gap in
    # the logic, and it is identified by position in the *network* — not by
    # position in the input list, which says nothing about the plan.
    open_starts = [aid for aid in ids if aid not in has_pred]
    open_finishes = [aid for aid in ids if aid not in has_succ]

    exempt = set()
    if open_starts:
        exempt.add(min(open_starts, key=lambda aid: (result.activities[aid].early_start, aid)))
    if open_finishes:
        exempt.add(max(open_finishes, key=lambda aid: (result.activities[aid].early_finish, aid)))

    dangling = sorted(
        {aid for aid in open_starts + open_finishes if aid not in exempt}
        # An activity with neither a predecessor nor a successor is detached
        # from the plan entirely, regardless of where it sits in time.
        | {aid for aid in ids if aid not in has_pred and aid not in has_succ}
    )
    value = _pct(len(dangling), n_act)
    add(
        CheckResult(
            1,
            "Logic",
            value <= MAX_MISSING_LOGIC,
            round(value * 100, 1),
            "≤ 5% missing predecessor or successor",
            f"{len(dangling)} of {n_act} activities are dangling",
            dangling,
        )
    )

    # --- 2. Leads (negative lag) --------------------------------------------
    leads = [f"{r.predecessor}→{r.successor}" for r in relationships if r.lag < 0]
    value = _pct(len(leads), n_rel)
    add(
        CheckResult(
            2,
            "Leads",
            len(leads) == 0,
            round(value * 100, 1),
            "0% negative lag",
            f"{len(leads)} relationships use a lead; leads hide true logic",
            leads,
        )
    )

    # --- 3. Lags ------------------------------------------------------------
    lags = [f"{r.predecessor}→{r.successor}" for r in relationships if r.lag > 0]
    value = _pct(len(lags), n_rel)
    add(
        CheckResult(
            3,
            "Lags",
            value <= MAX_LAGS,
            round(value * 100, 1),
            "≤ 5% of relationships",
            f"{len(lags)} of {n_rel} relationships carry a lag",
            lags,
        )
    )

    # --- 4. Relationship types ----------------------------------------------
    fs = [r for r in relationships if r.type is RelationType.FS]
    value = _pct(len(fs), n_rel)
    add(
        CheckResult(
            4,
            "Relationship Types",
            value >= MIN_FS_RELATIONSHIPS if n_rel else True,
            round(value * 100, 1),
            "≥ 90% Finish-to-Start",
            f"{len(fs)} of {n_rel} relationships are FS",
            [
                f"{r.predecessor}→{r.successor} ({r.type.value})"
                for r in relationships
                if r.type is not RelationType.FS
            ],
        )
    )

    # --- 5. Hard constraints -------------------------------------------------
    constrained = [a.id for a in activities if a.constraint_start is not None]
    value = _pct(len(constrained), n_act)
    add(
        CheckResult(
            5,
            "Hard Constraints",
            value <= MAX_HARD_CONSTRAINTS,
            round(value * 100, 1),
            "≤ 5% of activities",
            f"{len(constrained)} activities are pinned by a date constraint",
            constrained,
        )
    )

    # --- 6. High float -------------------------------------------------------
    high_float = [a.id for a in result.activities.values() if a.total_float > HIGH_FLOAT_DAYS]
    value = _pct(len(high_float), n_act)
    add(
        CheckResult(
            6,
            "High Float",
            value <= MAX_HIGH_FLOAT,
            round(value * 100, 1),
            f"≤ 5% above {HIGH_FLOAT_DAYS} days total float",
            f"{len(high_float)} activities have more than {HIGH_FLOAT_DAYS} days of float, "
            "which usually means missing logic rather than genuine slack",
            high_float,
        )
    )

    # --- 7. Negative float ---------------------------------------------------
    negative_float = [a.id for a in result.activities.values() if a.total_float < 0]
    value = _pct(len(negative_float), n_act)
    add(
        CheckResult(
            7,
            "Negative Float",
            len(negative_float) == 0,
            round(value * 100, 1),
            "0% below zero total float",
            f"{len(negative_float)} activities cannot meet their required dates",
            negative_float,
        )
    )

    # --- 8. High duration ----------------------------------------------------
    long_tasks = [a.id for a in activities if a.duration > HIGH_DURATION_DAYS]
    value = _pct(len(long_tasks), n_act)
    add(
        CheckResult(
            8,
            "High Duration",
            value <= MAX_HIGH_DURATION,
            round(value * 100, 1),
            f"≤ 5% longer than {HIGH_DURATION_DAYS} days",
            f"{len(long_tasks)} activities run longer than one reporting quarter "
            "and cannot be progressed meaningfully",
            long_tasks,
        )
    )

    # --- 9. Invalid dates ----------------------------------------------------
    if actual_finish is None:
        add(
            CheckResult(
                9,
                "Invalid Dates",
                None,
                None,
                "0% actuals in the future",
                "Skipped: no actual finish dates supplied",
            )
        )
    else:
        invalid = sorted(aid for aid, fin in actual_finish.items() if fin > data_date_offset)
        add(
            CheckResult(
                9,
                "Invalid Dates",
                len(invalid) == 0,
                round(_pct(len(invalid), n_act) * 100, 1),
                "0% actuals in the future",
                f"{len(invalid)} activities record work completed after the data date",
                invalid,
            )
        )

    # --- 10. Resources -------------------------------------------------------
    if resourced_activity_ids is None:
        add(
            CheckResult(
                10,
                "Resources",
                None,
                None,
                "100% of working activities resourced",
                "Skipped: no resource assignments supplied",
            )
        )
    else:
        resourced = set(resourced_activity_ids)
        unresourced = sorted(a.id for a in activities if a.duration > 0 and a.id not in resourced)
        working = sum(1 for a in activities if a.duration > 0)
        add(
            CheckResult(
                10,
                "Resources",
                len(unresourced) == 0,
                round(_pct(len(unresourced), working) * 100, 1),
                "100% of working activities resourced",
                f"{len(unresourced)} of {working} working activities carry no cost or resource",
                unresourced,
            )
        )

    # --- 11. Missed tasks ----------------------------------------------------
    if baseline_finish is None or actual_finish is None:
        add(
            CheckResult(
                11,
                "Missed Tasks",
                None,
                None,
                "≤ 5% finished late against baseline",
                "Skipped: needs both baseline and actual finish dates",
            )
        )
    else:
        missed = sorted(
            aid
            for aid, actual in actual_finish.items()
            if aid in baseline_finish and actual > baseline_finish[aid]
        )
        value = _pct(len(missed), len(actual_finish))
        add(
            CheckResult(
                11,
                "Missed Tasks",
                value <= MAX_MISSED_TASKS,
                round(value * 100, 1),
                "≤ 5% finished late against baseline",
                f"{len(missed)} of {len(actual_finish)} completed activities slipped past baseline",
                missed,
            )
        )

    # --- 12. Critical path test ---------------------------------------------
    # Inject a 600-day delay into the first critical activity. A sound network
    # pushes the project finish by the same amount; if it does not, the logic
    # is broken somewhere downstream.
    if result.critical_path:
        probe_id = result.critical_path[0]
        probed = [
            Activity(a.id, a.name, a.duration + 600, a.constraint_start) if a.id == probe_id else a
            for a in activities
        ]
        probed_result = calculate_cpm(probed, relationships)
        moved = probed_result.project_duration - result.project_duration
        add(
            CheckResult(
                12,
                "Critical Path Test",
                moved == 600,
                float(moved),
                "Project finish moves by the injected delay",
                f"A 600-day delay on {probe_id!r} moved the finish by {moved} days",
                [] if moved == 600 else [probe_id],
            )
        )
    else:
        add(
            CheckResult(
                12,
                "Critical Path Test",
                None,
                None,
                "Project finish moves by the injected delay",
                "Skipped: no critical path to probe",
            )
        )

    # --- 13. Critical Path Length Index --------------------------------------
    # CPLI = (critical path length + total float to the contract finish) /
    #        critical path length. Below 1.0 means the plan has no room left.
    cp_length = result.project_duration
    if cp_length > 0:
        finish_float = min(
            (a.total_float for a in result.activities.values() if a.early_finish == cp_length),
            default=0,
        )
        cpli = (cp_length + finish_float) / cp_length
        add(
            CheckResult(
                13,
                "Critical Path Length Index",
                cpli >= MIN_CPLI,
                round(cpli, 3),
                "≥ 0.95",
                f"CPLI of {cpli:.3f} on a {cp_length}-day critical path",
            )
        )
    else:
        add(
            CheckResult(
                13,
                "Critical Path Length Index",
                None,
                None,
                "≥ 0.95",
                "Skipped: zero-length critical path",
            )
        )

    # --- 14. Baseline Execution Index ----------------------------------------
    if baseline_finish is None or actual_finish is None:
        add(
            CheckResult(
                14,
                "Baseline Execution Index",
                None,
                None,
                "≥ 0.95",
                "Skipped: needs both baseline and actual finish dates",
            )
        )
    else:
        should_have_finished = [
            aid for aid, fin in baseline_finish.items() if fin <= data_date_offset
        ]
        completed = [aid for aid in should_have_finished if aid in actual_finish]
        bei = _pct(len(completed), len(should_have_finished)) if should_have_finished else 1.0
        add(
            CheckResult(
                14,
                "Baseline Execution Index",
                bei >= MIN_BEI,
                round(bei, 3),
                "≥ 0.95",
                f"{len(completed)} of {len(should_have_finished)} activities due by the data date "
                "are actually complete",
                sorted(set(should_have_finished) - set(completed)),
            )
        )

    return report
