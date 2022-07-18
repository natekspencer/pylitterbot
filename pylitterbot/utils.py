"""Utilities module."""
from __future__ import annotations

import logging
from base64 import b64decode
from datetime import datetime, time, timezone
from typing import Any
from warnings import warn

_LOGGER = logging.getLogger(__name__)


def decode(value: str) -> str:
    """Decode a value."""
    return b64decode(value).decode("utf-8")


def from_litter_robot_timestamp(
    timestamp: str | None,
) -> datetime | None:
    """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp.

    Litter-Robot timestamps are in the format `YYYY-MM-DDTHH:MM:SS.ffffff`,
    so to get the UTC offset-aware datetime, we just append `+00:00` and
    call the `datetime.fromisoformat` method.
    """
    if timestamp:
        return datetime.fromisoformat(f"{timestamp.replace('Z','')}+00:00")


def utcnow() -> datetime:
    """Return the current UTC offset-aware datetime."""
    return datetime.now(timezone.utc)


def today_at_time(tm: time) -> datetime:
    """Return a datetime representing today at the passed in time."""
    return datetime.combine(utcnow().astimezone(tm.tzinfo), tm)


def round_time(dt: datetime | None = None, round_to: int = 60) -> datetime:
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


# Hacky, but works?
class DeprecatedList(list):  # pragma: no cover
    """Deprecated List"""

    def __init__(self, *args, old_name: str, new_name: str) -> None:
        self._sent_warning = False
        self._old_name = old_name
        self._new_name = new_name
        return super().__init__(*args)

    def __send_deprecation_warning(self) -> None:
        if not self._sent_warning:
            self._sent_warning = True
            send_deprecation_warning(self._old_name, self._new_name)

    def __getitem__(self, i: int):
        self.__send_deprecation_warning()
        return super().__getitem__(i)

    def __str__(self):
        self.__send_deprecation_warning()
        return super().__str__()

    def __repr__(self):
        self.__send_deprecation_warning()
        return super().__repr__()

    def __iter__(self):
        self.__send_deprecation_warning()
        return super().__iter__()

    def __mul__(self, n: int):
        self.__send_deprecation_warning()
        return super().__mul__(n)

    def __contains__(self, o: object):
        self.__send_deprecation_warning()
        return super().__contains__(o)


def send_deprecation_warning(
    old_name: str, new_name: str | None = None
):  # pragma: no cover
    message = f"{old_name} has been deprecated{'' if new_name is None else f' in favor of {new_name}'} and will be removed in a future release"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)
