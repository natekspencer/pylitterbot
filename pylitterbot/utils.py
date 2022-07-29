"""Utilities module."""
from __future__ import annotations

import json
import logging
from base64 import b64decode, b64encode
from datetime import datetime, time, timezone
from typing import Any
from warnings import warn

_LOGGER = logging.getLogger(__name__)

ENCODING = "utf-8"


def decode(value: str) -> str:
    """Decode a value."""
    return b64decode(value).decode(ENCODING)


def encode(value: str | dict) -> str:
    """Encode a value."""
    if isinstance(value, dict):
        value = json.dumps(value)
    return b64encode(value.encode(ENCODING)).decode(ENCODING)


def from_litter_robot_timestamp(
    timestamp: str | None,
) -> datetime | None:
    """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp.

    Litter-Robot timestamps are in the format `YYYY-MM-DDTHH:MM:SS.ffffff`,
    so to get the UTC offset-aware datetime, we just append `+00:00` and
    call the `datetime.fromisoformat` method.
    """
    if not timestamp:
        return None
    return datetime.fromisoformat(f"{timestamp.replace('Z','')}+00:00")


def utcnow() -> datetime:
    """Return the current UTC offset-aware datetime."""
    return datetime.now(timezone.utc)


def today_at_time(_time: time) -> datetime:
    """Return a datetime representing today at the passed in time."""
    return datetime.combine(utcnow().astimezone(_time.tzinfo), _time)


def round_time(_datetime: datetime | None = None, round_to: int = 60) -> datetime:
    """Round a datetime to the specified seconds or 1 minute if not specified."""
    if not _datetime:
        _datetime = utcnow()

    return datetime.fromtimestamp(
        (_datetime.timestamp() + round_to / 2) // round_to * round_to, _datetime.tzinfo
    )


def pluralize(word: str, count: int):
    """Pluralize a word."""
    return f"{count} {word}{'s' if count != 1 else ''}"


class DeprecatedClassMeta(type):  # pragma: no cover
    """Deprecated class meta."""

    def __new__(
        cls, name, bases, classdict, *args, **kwargs
    ):  # pylint: disable=unused-argument
        alias = classdict.get("_DeprecatedClassMeta__alias")
        classdict["_DeprecatedClassMeta__alias"] = alias
        fixed_bases = tuple([])
        return super().__new__(cls, name, fixed_bases, classdict, *args, **kwargs)

    def __getattr__(cls, name: str) -> Any:
        send_deprecation_warning(
            f"{cls.__module__}.{cls.__qualname__}",
            f"{cls._DeprecatedClassMeta__alias.__module__}.{cls._DeprecatedClassMeta__alias.__qualname__}",
        )
        return getattr(cls._DeprecatedClassMeta__alias, name)


def send_deprecation_warning(
    old_name: str, new_name: str | None = None
):  # pragma: no cover
    """Log a deprecation warning message."""
    message = f"{old_name} has been deprecated{'' if new_name is None else f' in favor of {new_name}'} and will be removed in a future release"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)
