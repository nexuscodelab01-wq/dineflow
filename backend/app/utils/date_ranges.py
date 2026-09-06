"""Date range helpers for analytics filters."""

from datetime import UTC, datetime, timedelta
from enum import Enum


class DateRangePreset(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    CUSTOM = "custom"


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def resolve_date_range(
    preset: DateRangePreset,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    today = _start_of_day(now)

    if preset == DateRangePreset.TODAY:
        return today, _end_of_day(now)

    if preset == DateRangePreset.YESTERDAY:
        y = today - timedelta(days=1)
        return y, _end_of_day(y)

    if preset == DateRangePreset.LAST_7_DAYS:
        start = today - timedelta(days=6)
        return start, _end_of_day(now)

    if preset == DateRangePreset.LAST_30_DAYS:
        start = today - timedelta(days=29)
        return start, _end_of_day(now)

    if preset == DateRangePreset.THIS_MONTH:
        start = today.replace(day=1)
        return start, _end_of_day(now)

    if preset == DateRangePreset.LAST_MONTH:
        first_this_month = today.replace(day=1)
        last_month_end = first_this_month - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return last_month_start, _end_of_day(last_month_end)

    if preset == DateRangePreset.CUSTOM:
        if start_date is None or end_date is None:
            raise ValueError("Custom range requires start_date and end_date")
        start = start_date if start_date.tzinfo else start_date.replace(tzinfo=UTC)
        end = end_date if end_date.tzinfo else end_date.replace(tzinfo=UTC)
        if start > end:
            raise ValueError("start_date must be before end_date")
        return _start_of_day(start), _end_of_day(end)

    raise ValueError(f"Unknown preset: {preset}")
