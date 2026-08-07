"""Critical Path Method scheduling.

This is a full CPM implementation: topologically ordered forward and backward
passes, all four relationship types (FS/SS/FF/SF) with positive or negative
lag, total and free float, and cycle detection that names the offending loop.

Durations and lags are expressed in *working days*. Mapping working days onto
calendar dates is the job of :class:`core.calendar.WorkCalendar`, which keeps
the algorithm independent of holidays and shift patterns.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum


class RelationType(str, Enum):
    """Logic tie between a predecessor and a successor."""

    FS = "FS"  # Finish-to-Start: successor starts after predecessor finishes
    SS = "SS"  # Start-to-Start
    FF = "FF"  # Finish-to-Finish
    SF = "SF"  # Start-to-Finish


class ScheduleCycleError(ValueError):
    """Raised when the logic network contains a circular dependency."""

    def __init__(self, cycle: Sequence[str]):
        self.cycle = list(cycle)
        joined = " -> ".join(str(node) for node in cycle)
        super().__init__(f"Circular dependency in schedule logic: {joined}")


@dataclass(frozen=True)
class Activity:
    """A single schedule activity."""

    id: str
    name: str
    duration: int
    # A hard constraint pinning the earliest the activity may start, expressed
    # as a working-day offset from the data date. Mirrors P6's "Start On or
    # After" constraint, the only one common enough to be worth modelling here.
    constraint_start: int | None = None

    def __post_init__(self) -> None:
        if self.duration < 0:
            raise ValueError(f"Activity {self.id!r} has negative duration {self.duration}")


@dataclass(frozen=True)
class Relationship:
    """A logic tie. ``lag`` may be negative, which models a lead."""

    predecessor: str
    successor: str
    type: RelationType = RelationType.FS
    lag: int = 0


@dataclass
class ActivityResult:
    """Computed dates and float for one activity, in working-day offsets."""

    id: str
    name: str
    duration: int
    early_start: int
    early_finish: int
    late_start: int
    late_finish: int
    total_float: int
    free_float: int

    @property
    def is_critical(self) -> bool:
        return self.total_float <= 0


@dataclass
class ScheduleResult:
    """The outcome of a CPM run."""

    activities: dict[str, ActivityResult] = field(default_factory=dict)
    project_duration: int = 0
    critical_path: list[str] = field(default_factory=list)

    def ordered(self) -> list[ActivityResult]:
        """Activities sorted by early start, then by id for stable output."""
        return sorted(self.activities.values(), key=lambda a: (a.early_start, a.id))


def _topological_order(
    activity_ids: Sequence[str], relationships: Iterable[Relationship]
) -> list[str]:
    """Kahn's algorithm. Raises :class:`ScheduleCycleError` naming the cycle."""
    successors: dict[str, list[str]] = {aid: [] for aid in activity_ids}
    in_degree: dict[str, int] = dict.fromkeys(activity_ids, 0)

    for rel in relationships:
        successors[rel.predecessor].append(rel.successor)
        in_degree[rel.successor] += 1

    # Seed with open-start activities in declaration order so that a schedule
    # with no logic at all comes back in the order the caller supplied.
    ready = [aid for aid in activity_ids if in_degree[aid] == 0]
    order: list[str] = []

    while ready:
        current = ready.pop(0)
        order.append(current)
        for succ in successors[current]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)

    if len(order) != len(activity_ids):
        remaining = {aid for aid in activity_ids if aid not in set(order)}
        raise ScheduleCycleError(_find_cycle(remaining, successors))

    return order


def _find_cycle(candidates: set, successors: dict[str, list[str]]) -> list[str]:
    """Walk the un-orderable remainder to recover one concrete cycle."""
    start = next(iter(candidates))
    path: list[str] = []
    seen_on_path = set()
    node = start

    while node not in seen_on_path:
        path.append(node)
        seen_on_path.add(node)
        onward = [s for s in successors[node] if s in candidates]
        if not onward:
            return path
        node = onward[0]

    # Trim the tail that leads into the loop so we report the loop itself.
    loop_start = path.index(node)
    return path[loop_start:] + [node]


def _validate(activities: Sequence[Activity], relationships: Sequence[Relationship]) -> None:
    ids = [a.id for a in activities]
    duplicates = {aid for aid in ids if ids.count(aid) > 1}
    if duplicates:
        raise ValueError(f"Duplicate activity ids: {sorted(duplicates)}")

    known = set(ids)
    for rel in relationships:
        if rel.predecessor not in known:
            raise ValueError(f"Relationship references unknown predecessor {rel.predecessor!r}")
        if rel.successor not in known:
            raise ValueError(f"Relationship references unknown successor {rel.successor!r}")
        if rel.predecessor == rel.successor:
            raise ValueError(f"Activity {rel.predecessor!r} depends on itself")


def calculate_cpm(
    activities: Sequence[Activity], relationships: Sequence[Relationship] = ()
) -> ScheduleResult:
    """Run a forward and backward pass and return dates plus float.

    All values are working-day offsets from the data date, where 0 is the
    first working day of the project.
    """
    if not activities:
        return ScheduleResult()

    relationships = list(relationships)
    _validate(activities, relationships)

    by_id = {a.id: a for a in activities}
    order = _topological_order([a.id for a in activities], relationships)

    preds_of: dict[str, list[Relationship]] = {a.id: [] for a in activities}
    succs_of: dict[str, list[Relationship]] = {a.id: [] for a in activities}
    for rel in relationships:
        preds_of[rel.successor].append(rel)
        succs_of[rel.predecessor].append(rel)

    early_start: dict[str, int] = {}
    early_finish: dict[str, int] = {}

    # ---- Forward pass: earliest each activity can start and finish ----------
    for aid in order:
        activity = by_id[aid]
        earliest = 0
        for rel in preds_of[aid]:
            p_es, p_ef = early_start[rel.predecessor], early_finish[rel.predecessor]
            if rel.type is RelationType.FS:
                earliest = max(earliest, p_ef + rel.lag)
            elif rel.type is RelationType.SS:
                earliest = max(earliest, p_es + rel.lag)
            elif rel.type is RelationType.FF:
                # Successor must finish at/after predecessor finish + lag.
                earliest = max(earliest, p_ef + rel.lag - activity.duration)
            else:  # SF
                earliest = max(earliest, p_es + rel.lag - activity.duration)

        if activity.constraint_start is not None:
            earliest = max(earliest, activity.constraint_start)

        early_start[aid] = earliest
        early_finish[aid] = earliest + activity.duration

    project_duration = max(early_finish.values())

    late_start: dict[str, int] = {}
    late_finish: dict[str, int] = {}

    # ---- Backward pass: latest each activity can run without slipping -------
    for aid in reversed(order):
        activity = by_id[aid]
        latest_finish = project_duration
        for rel in succs_of[aid]:
            s_ls, s_lf = late_start[rel.successor], late_finish[rel.successor]
            if rel.type is RelationType.FS:
                latest_finish = min(latest_finish, s_ls - rel.lag)
            elif rel.type is RelationType.SS:
                latest_finish = min(latest_finish, s_ls - rel.lag + activity.duration)
            elif rel.type is RelationType.FF:
                latest_finish = min(latest_finish, s_lf - rel.lag)
            else:  # SF
                latest_finish = min(latest_finish, s_lf - rel.lag + activity.duration)

        late_finish[aid] = latest_finish
        late_start[aid] = latest_finish - activity.duration

    # ---- Float --------------------------------------------------------------
    results: dict[str, ActivityResult] = {}
    for aid in order:
        activity = by_id[aid]
        total_float = late_start[aid] - early_start[aid]

        # Free float: how far this activity can slip before it delays *any*
        # successor's early start. An activity with no successors can slip up
        # to the project finish.
        if succs_of[aid]:
            slacks = []
            for rel in succs_of[aid]:
                s_es = early_start[rel.successor]
                s_ef = early_finish[rel.successor]
                if rel.type is RelationType.FS:
                    slacks.append(s_es - rel.lag - early_finish[aid])
                elif rel.type is RelationType.SS:
                    slacks.append(s_es - rel.lag - early_start[aid])
                elif rel.type is RelationType.FF:
                    slacks.append(s_ef - rel.lag - early_finish[aid])
                else:  # SF
                    slacks.append(s_ef - rel.lag - early_start[aid])
            free_float = min(slacks)
        else:
            free_float = project_duration - early_finish[aid]

        results[aid] = ActivityResult(
            id=aid,
            name=activity.name,
            duration=activity.duration,
            early_start=early_start[aid],
            early_finish=early_finish[aid],
            late_start=late_start[aid],
            late_finish=late_finish[aid],
            total_float=total_float,
            free_float=free_float,
        )

    critical_path = [
        r.id for r in sorted(results.values(), key=lambda a: (a.early_start, a.id)) if r.is_critical
    ]

    return ScheduleResult(
        activities=results,
        project_duration=project_duration,
        critical_path=critical_path,
    )


def longest_path(result: ScheduleResult, relationships: Sequence[Relationship]) -> list[str]:
    """Return the driving path — the actual chain of critical activities.

    Zero-float filtering alone can return critical activities that are not
    linked to one another. This walks the logic to produce a single connected
    chain, which is what a planner means by "the critical path".
    """
    critical = set(result.critical_path)
    if not critical:
        return []

    succs: dict[str, list[str]] = {}
    for rel in relationships:
        if rel.predecessor in critical and rel.successor in critical:
            succs.setdefault(rel.predecessor, []).append(rel.successor)

    start = min(critical, key=lambda aid: (result.activities[aid].early_start, aid))
    chain = [start]
    while chain[-1] in succs:
        nxt = min(succs[chain[-1]], key=lambda aid: (result.activities[aid].early_start, aid))
        if nxt in chain:  # defensive; cycles are rejected earlier
            break
        chain.append(nxt)
    return chain
