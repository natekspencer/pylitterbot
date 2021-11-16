"""Utilities module."""
import logging
from datetime import datetime, time
from typing import Any, Optional
from warnings import warn

import pytz

_LOGGER = logging.getLogger(__name__)


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


def pluralize(word: str, count: int):
    return f"{count} {word}{'s' if count != 1 else ''}"


class DeprecatedClassMeta(type):  # pragma: no cover
    def __new__(cls, name, bases, classdict, *args, **kwargs):
        alias = classdict.get("_DeprecatedClassMeta__alias")
        classdict["_DeprecatedClassMeta__alias"] = alias
        fixed_bases = tuple([])
        return super().__new__(cls, name, fixed_bases, classdict, *args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        send_deprecation_warning(
            f"{self.__module__}.{self.__qualname__}",
            f"{self._DeprecatedClassMeta__alias.__module__}.{self._DeprecatedClassMeta__alias.__qualname__}",
        )
        return getattr(self._DeprecatedClassMeta__alias, name)


def send_deprecation_warning(old_name, new_name):  # pragma: no cover
    message = f"{old_name} has been deprecated in favor of {new_name}, the alias will be removed in the future"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)
