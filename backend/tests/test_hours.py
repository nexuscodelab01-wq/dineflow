"""Opening hours logic (backend/app/core/hours.py): pure, no database — the rule lives in one place."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.hours import (
    InvalidHours,
    describe_hours,
    status_at,
    valid_timezone,
    validate_closures,
    validate_opening_hours,
)

WEEKLY = {
    "monday": "11:00-22:00", "tuesday": "11:00-22:00", "wednesday": "11:00-22:00", "thursday": "11:00-22:00",
    "friday": "11:00-23:00", "saturday": "10:00-23:00", "sunday": "closed",
}


def restaurant(hours=None, tz="America/Los_Angeles", closures=None, name="Test Kitchen"):
    return SimpleNamespace(name=name, opening_hours=hours, timezone=tz, closures=closures or [])


def at(y, m, d, h, mi, tz="America/Los_Angeles"):
    from zoneinfo import ZoneInfo
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo(tz))


# ------------------------------------------------------------------ validation

def test_valid_timezones_are_accepted_and_junk_is_not():
    assert valid_timezone("America/Los_Angeles") and valid_timezone("UTC") and valid_timezone("Europe/London")
    assert not valid_timezone("Mars/Olympus_Mons") and not valid_timezone("") and not valid_timezone("not a tz")


def test_opening_hours_validation():
    validate_opening_hours(WEEKLY)          # no error
    validate_opening_hours({})              # empty = every day closed, still valid shape
    with pytest.raises(InvalidHours, match="Unknown day"):
        validate_opening_hours({"someday": "09:00-17:00"})
    with pytest.raises(InvalidHours, match="not a time"):
        validate_opening_hours({"monday": "9am-5pm"})
    with pytest.raises(InvalidHours, match="range"):
        validate_opening_hours({"monday": "09:00-17:00-20:00"})
    with pytest.raises(InvalidHours, match="not a time"):
        validate_opening_hours({"monday": "9:xx-17:00"})
    with pytest.raises(InvalidHours, match="same"):
        validate_opening_hours({"monday": "09:00-09:00"})
    with pytest.raises(InvalidHours):
        validate_opening_hours("monday: 9-5")   # not even a dict


def test_closures_validation():
    validate_closures([])
    validate_closures([{"date": "2026-12-25", "label": "Christmas"}])
    validate_closures([{"date": "2026-01-01"}])   # label optional
    with pytest.raises(InvalidHours, match="date"):
        validate_closures([{"label": "no date"}])
    with pytest.raises(InvalidHours, match="not a date"):
        validate_closures([{"date": "25 Dec 2026"}])
    with pytest.raises(InvalidHours, match="list"):
        validate_closures({"date": "2026-12-25"})


# ------------------------------------------------------------------ is it open

def test_no_opening_hours_set_means_always_open():
    r = restaurant(hours=None)
    assert status_at(r, at(2026, 1, 5, 3, 0)).open is True     # 3am, whatever day
    assert describe_hours(r) == "open every day"


def test_open_and_closed_within_the_weekly_hours():
    r = restaurant(hours=WEEKLY)
    assert status_at(r, at(2026, 3, 2, 12, 0)).open is True     # Monday noon
    assert status_at(r, at(2026, 3, 2, 10, 59)).open is False   # just before opening
    before = status_at(r, at(2026, 3, 2, 10, 59))
    assert before.reason and "closed" in before.reason
    assert status_at(r, at(2026, 3, 2, 22, 0)).open is False    # exactly closing time: closed
    assert status_at(r, at(2026, 3, 8, 15, 0)).open is False    # Sunday: closed all day


def test_a_window_crossing_midnight_is_read_correctly():
    r = restaurant(hours={**WEEKLY, "friday": "18:00-01:00"})
    assert status_at(r, at(2026, 3, 6, 23, 30)).open is True    # Friday 23:30, still within the window
    assert status_at(r, at(2026, 3, 7, 0, 30)).open is True     # Saturday 00:30, carried over from Friday
    assert status_at(r, at(2026, 3, 7, 1, 30)).open is False    # Saturday 01:30, the window ended
    assert status_at(r, at(2026, 3, 6, 17, 59)).open is False   # Friday, before it opens


def test_a_closure_overrides_the_weekly_hours():
    r = restaurant(hours=WEEKLY, closures=[{"date": "2026-03-02", "label": "Private event"}])
    result = status_at(r, at(2026, 3, 2, 12, 0))                # a Monday that would otherwise be open
    assert result.open is False and result.reason == "Private event"
    assert status_at(r, at(2026, 3, 3, 12, 0)).open is True     # the next day is unaffected


def test_status_is_computed_in_the_restaurants_own_timezone():
    # 2026-03-02 is a Monday. In March, Los Angeles is 8 hours behind UTC (before DST starts).
    r = restaurant(hours=WEEKLY, tz="America/Los_Angeles")
    monday_03_00_utc = at(2026, 3, 2, 3, 0, tz="UTC")     # = Sunday 19:00 in Los Angeles: closed all day
    assert status_at(r, monday_03_00_utc).open is False
    monday_20_00_utc = at(2026, 3, 2, 20, 0, tz="UTC")    # = Monday 12:00 in Los Angeles: within 11:00-22:00
    assert status_at(r, monday_20_00_utc).open is True


def test_closed_now_reports_when_it_next_opens():
    r = restaurant(hours=WEEKLY)
    result = status_at(r, at(2026, 3, 8, 15, 0))                # Sunday, closed all day
    assert result.opens_at == at(2026, 3, 9, 11, 0)              # Monday 11:00


def test_describe_hours_names_todays_window():
    r = restaurant(hours=WEEKLY)
    assert "11:00" in describe_hours(r) and "22:00" in describe_hours(r)
