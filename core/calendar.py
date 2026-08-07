"""Mapping working-day offsets onto calendar dates.

CPM math is cleanest in working days. Construction schedules are read in
calendar dates. This module is the bridge, and it is where weekends, holidays,
and non-standard shift patterns live.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


class WorkCalendar:
    """A working-day calendar.

    ``work_days`` uses Python's weekday numbering (Monday=0 ... Sunday=6) and
    defaults to a standard five-day week.
    """

    STANDARD_5_DAY = frozenset({0, 1, 2, 3, 4})
    SIX_DAY = frozenset({0, 1, 2, 3, 4, 5})
    SEVEN_DAY = frozenset({0, 1, 2, 3, 4, 5, 6})

    def __init__(
        self,
        start_date: date,
        work_days: Iterable[int] = STANDARD_5_DAY,
        holidays: Iterable[date] = (),
    ):
        self.work_days: set[int] = set(work_days)
        if not self.work_days:
            raise ValueError("A calendar needs at least one working weekday")
        self.holidays: set[date] = set(holidays)
        self.start_date = self.next_work_day(start_date)

    def is_work_day(self, day: date) -> bool:
        return day.weekday() in self.work_days and day not in self.holidays

    def next_work_day(self, day: date) -> date:
        """The first working day on or after ``day``."""
        cursor = day
        for _ in range(3650):  # ten years is a generous ceiling for a gap
            if self.is_work_day(cursor):
                return cursor
            cursor += timedelta(days=1)
        raise ValueError("No working day found within ten years of the start date")

    def date_for_offset(self, offset: int) -> date:
        """Convert a working-day offset into a calendar date.

        Offset 0 is the project start date. Negative offsets are not supported
        because CPM results are always anchored at or after the data date.
        """
        if offset < 0:
            raise ValueError(f"Negative working-day offset: {offset}")

        cursor = self.start_date
        remaining = offset
        while remaining > 0:
            cursor += timedelta(days=1)
            if self.is_work_day(cursor):
                remaining -= 1
        return cursor

    def finish_date_for(self, early_start: int, duration: int) -> date:
        """The last working day of an activity, inclusive.

        A one-day activity starting on offset 0 finishes on offset 0, not
        offset 1 — planners read finish dates as the last day worked. A
        zero-duration activity (a milestone) reports the start date.
        """
        if duration <= 0:
            return self.date_for_offset(early_start)
        return self.date_for_offset(early_start + duration - 1)

    def work_days_between(self, first: date, last: date) -> int:
        """Count working days in the inclusive range ``[first, last]``."""
        if last < first:
            return 0
        count = 0
        cursor = first
        while cursor <= last:
            if self.is_work_day(cursor):
                count += 1
            cursor += timedelta(days=1)
        return count
