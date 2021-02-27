from datetime import datetime, time
from typing import Optional

import pytz


def from_litter_robot_timestamp(
    timestamp: Optional[str],
) -> Optional[datetime]:
    """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp.

    Litter-Robot timestamps are in the format `YYYY-MM-DDTHH:MM:SS.ffffff`,
    so to get the UTC offset-aware datetime, we just append `+00:00` and
    call the `datetime.fromisoformat` method.
    """
    if timestamp:
        return datetime.fromisoformat(f"{timestamp}+00:00")


def utcnow() -> datetime:
    """Return the current UTC offset-aware datetime."""
    return datetime.now(pytz.UTC)


def today_at_time(tm: time) -> datetime:
    """Return a datetime representing today at the passed in time."""
    return datetime.combine(utcnow().astimezone(tm.tzinfo), tm)


def round_time(dt: Optional[datetime] = None, round_to: int = 60) -> datetime:
    """Round a datetime to the specified seconds or 1 minute if not specified."""
    if not dt:
        dt = utcnow()

    return datetime.fromtimestamp(
        (dt.timestamp() + round_to / 2) // round_to * round_to, dt.tzinfo
    )
