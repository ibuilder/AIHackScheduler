"""Tests for working-day to calendar-date mapping."""

from datetime import date

import pytest

from core.calendar import WorkCalendar


def test_offset_zero_is_the_start_date():
    cal = WorkCalendar(date(2026, 3, 2))  # a Monday
    assert cal.date_for_offset(0) == date(2026, 3, 2)


def test_start_date_rolls_forward_off_a_weekend():
    cal = WorkCalendar(date(2026, 3, 7))  # a Saturday
    assert cal.start_date == date(2026, 3, 9)  # the following Monday


def test_weekends_are_skipped():
    cal = WorkCalendar(date(2026, 3, 2))  # Monday
    assert cal.date_for_offset(4) == date(2026, 3, 6)  # Friday
    assert cal.date_for_offset(5) == date(2026, 3, 9)  # skips to Monday


def test_holidays_are_skipped():
    cal = WorkCalendar(date(2026, 3, 2), holidays=[date(2026, 3, 4)])
    assert cal.date_for_offset(2) == date(2026, 3, 5)  # Wednesday skipped


def test_six_day_week():
    cal = WorkCalendar(date(2026, 3, 2), work_days=WorkCalendar.SIX_DAY)
    assert cal.date_for_offset(5) == date(2026, 3, 7)  # Saturday now works


def test_seven_day_week_matches_plain_arithmetic():
    cal = WorkCalendar(date(2026, 3, 2), work_days=WorkCalendar.SEVEN_DAY)
    assert cal.date_for_offset(10) == date(2026, 3, 12)


def test_finish_date_is_the_last_day_worked():
    cal = WorkCalendar(date(2026, 3, 2))
    # A 5-day activity starting Monday finishes Friday, not the next Monday.
    assert cal.finish_date_for(0, 5) == date(2026, 3, 6)


def test_milestone_finish_equals_its_start():
    cal = WorkCalendar(date(2026, 3, 2))
    assert cal.finish_date_for(3, 0) == cal.date_for_offset(3)


def test_work_days_between_is_inclusive():
    cal = WorkCalendar(date(2026, 3, 2))
    assert cal.work_days_between(date(2026, 3, 2), date(2026, 3, 6)) == 5
    assert cal.work_days_between(date(2026, 3, 2), date(2026, 3, 8)) == 5  # weekend adds none


def test_reversed_range_counts_zero():
    cal = WorkCalendar(date(2026, 3, 2))
    assert cal.work_days_between(date(2026, 3, 6), date(2026, 3, 2)) == 0


def test_negative_offset_rejected():
    cal = WorkCalendar(date(2026, 3, 2))
    with pytest.raises(ValueError, match="Negative working-day offset"):
        cal.date_for_offset(-1)


def test_calendar_with_no_working_days_rejected():
    with pytest.raises(ValueError, match="at least one working weekday"):
        WorkCalendar(date(2026, 3, 2), work_days=[])
