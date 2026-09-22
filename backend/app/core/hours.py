"""Opening hours, holidays and "is this restaurant open right now" — one place so the rule is the same
everywhere it matters (ordering, booking, the site header).

`opening_hours` on a restaurant is a dict keyed by weekday name (lowercase English, "monday".."sunday`).
Each value is either "HH:MM-HH:MM" (24h, local time) or "closed"; a missing day means closed. A range
that ends before it starts (e.g. "18:00-01:00") is read as crossing midnight. A restaurant with no
`opening_hours` set at all is always open — this is what every restaurant had before this feature, and
staying open is the safer default than locking customers out because nobody has set hours yet.

`closures` is a list of `{"date": "YYYY-MM-DD", "label": "..."}`: whole extra days the restaurant is
shut (holidays, a private event) regardless of the weekly hours.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DEFAULT_TIMEZONE = "UTC"


class InvalidHours(ValueError):
    pass


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def _zone(restaurant) -> ZoneInfo:
    name = getattr(restaurant, "timezone", None) or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo(DEFAULT_TIMEZONE)  # a bad value already in the database must never crash a request


def _parse_clock(value: str) -> time:
    try:
        hour, minute = value.strip().split(":")
        return time(int(hour), int(minute))
    except (ValueError, TypeError) as exc:
        raise InvalidHours(f"'{value}' is not a time like 09:30") from exc


def parse_day(value: object) -> tuple[time, time] | None:
    """One day's value from `opening_hours` -> (open, close), or None for closed. Raises InvalidHours."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidHours("Each day must be 'HH:MM-HH:MM' or 'closed'")
    text = value.strip().lower()
    if text in ("", "closed"):
        return None
    parts = text.split("-")
    if len(parts) != 2:
        raise InvalidHours(f"'{value}' is not a range like 09:00-22:00")
    opens, closes = _parse_clock(parts[0]), _parse_clock(parts[1])
    if opens == closes:
        raise InvalidHours("Opening and closing time cannot be the same — use 'closed' instead")
    return opens, closes


def validate_opening_hours(hours: dict) -> None:
    if not isinstance(hours, dict):
        raise InvalidHours("Opening hours must be an object keyed by day name")
    unknown = set(hours) - set(DAYS)
    if unknown:
        raise InvalidHours(f"Unknown day(s): {', '.join(sorted(unknown))}. Use: {', '.join(DAYS)}")
    for day, value in hours.items():
        parse_day(value)  # raises on anything bad


def validate_closures(closures: list) -> None:
    if not isinstance(closures, list):
        raise InvalidHours("Closures must be a list")
    for row in closures:
        if not isinstance(row, dict) or "date" not in row:
            raise InvalidHours('Each closure needs a date, e.g. {"date": "2026-12-25", "label": "Christmas"}')
        try:
            date.fromisoformat(str(row["date"]))
        except ValueError as exc:
            raise InvalidHours(f"'{row['date']}' is not a date like 2026-12-25") from exc
        if "label" in row and row["label"] is not None and not isinstance(row["label"], str):
            raise InvalidHours("A closure's label must be text")


def local_now(restaurant) -> datetime:
    return datetime.now(_zone(restaurant))


def to_local(restaurant, at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("to_local needs a timezone-aware datetime")
    return at.astimezone(_zone(restaurant))


def closure_label(restaurant, local_date: date) -> str | None:
    for row in getattr(restaurant, "closures", None) or []:
        if row.get("date") == local_date.isoformat():
            return row.get("label") or "closed for the day"
    return None


@dataclass
class OpenStatus:
    open: bool
    reason: str | None = None  # only set when closed; short and guest-facing
    opens_at: datetime | None = None  # the next time it opens, when known and closed now


def status_at(restaurant, at: datetime) -> OpenStatus:
    """Is the restaurant open at `at` (any aware datetime)? A restaurant with no opening_hours set is always open."""
    hours = getattr(restaurant, "opening_hours", None)
    if not hours:
        return OpenStatus(open=True)

    local = to_local(restaurant, at)
    label = closure_label(restaurant, local.date())
    if label:
        return OpenStatus(open=False, reason=label)

    # A window opened yesterday and crossing midnight can still cover "now".
    for offset in (0, -1):
        day = local.date() + timedelta(days=offset)
        window = parse_day(hours.get(DAYS[day.weekday()]))
        if window is None:
            continue
        opens, closes = window
        start = datetime.combine(day, opens, tzinfo=local.tzinfo)
        end = datetime.combine(day, closes, tzinfo=local.tzinfo)
        if closes <= opens:  # crosses midnight
            end += timedelta(days=1)
        if start <= local < end:
            return OpenStatus(open=True)

    return OpenStatus(open=False, reason="closed right now", opens_at=_next_open(restaurant, local))


def _next_open(restaurant, local: datetime) -> datetime | None:
    hours = getattr(restaurant, "opening_hours", None) or {}
    for offset in range(0, 14):  # look up to two weeks ahead rather than loop forever on all-closed data
        day = local.date() + timedelta(days=offset)
        if closure_label(restaurant, day):
            continue
        window = parse_day(hours.get(DAYS[day.weekday()]))
        if window is None:
            continue
        opens, _ = window
        candidate = datetime.combine(day, opens, tzinfo=local.tzinfo)
        if candidate > local:
            return candidate
    return None


def describe_hours(restaurant) -> str:
    """One line for an error message, e.g. 'Hours today: 11:00–22:00 (America/Los_Angeles)'."""
    hours = getattr(restaurant, "opening_hours", None)
    if not hours:
        return "open every day"
    local = local_now(restaurant)
    window = parse_day(hours.get(DAYS[local.weekday()]))
    tz = getattr(restaurant, "timezone", None) or DEFAULT_TIMEZONE
    if window is None:
        return f"closed today ({tz})"
    opens, closes = window
    return f"today's hours: {opens.strftime('%H:%M')}–{closes.strftime('%H:%M')} ({tz})"
