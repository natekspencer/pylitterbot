"""Utilities module."""

from __future__ import annotations

import json
import logging
import re
from base64 import b64decode, b64encode
from collections.abc import Iterable, Mapping
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Type, TypeVar, cast, overload
from urllib.parse import urljoin as _urljoin
from warnings import warn

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")
_E = TypeVar("_E", bound=Enum)

ENCODING = "utf-8"
REDACTED = "**REDACTED**"
REDACT_FIELDS = [
    "token",
    "access_token",
    "id_token",
    "idToken",
    "refresh_token",
    "refreshToken",
    "userId",
    "userEmail",
    "sessionId",
    "oneSignalPlayerId",
    "deviceId",
    "id",
    "litterRobotId",
    "unitId",
    "litterRobotSerial",
    "serial",
    "s3ImageURL",
]


def decode(value: str) -> str:
    """Decode a value."""
    return b64decode(value).decode(ENCODING)


def encode(value: str | dict) -> str:
    """Encode a value."""
    if isinstance(value, dict):
        value = json.dumps(value)
    return b64encode(value.encode(ENCODING)).decode(ENCODING)


def to_timestamp(timestamp: str | None) -> datetime | None:
    """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp."""
    if not timestamp:
        return None
    if "Z" in timestamp:
        timestamp = timestamp.replace("Z", "")
    if (utc_offset := "+00:00") not in timestamp:
        timestamp += utc_offset
    timestamp = re.sub(r"(\.\d+)", lambda m: m.group().ljust(7, "0")[:7], timestamp)
    return datetime.fromisoformat(timestamp)


def pluralize(word: str, count: int) -> str:
    """Pluralize a word."""
    return f"{count} {word}{'s' if count != 1 else ''}"


def round_time(_datetime: datetime | None = None, round_to: int = 60) -> datetime:
    """Round a datetime to the specified seconds or 1 minute if not specified."""
    if not _datetime:
        _datetime = utcnow()

    return datetime.fromtimestamp(
        (_datetime.timestamp() + round_to / 2) // round_to * round_to, _datetime.tzinfo
    )


def today_at_time(_time: time) -> datetime:
    """Return a datetime representing today at the passed in time."""
    return datetime.combine(utcnow().astimezone(_time.tzinfo), _time)


def urljoin(base: str, subpath_or_url: str | None) -> str:
    """Join a base URL and subpath or URL to form an absolute interpretation of the latter."""
    if not subpath_or_url:
        return base
    if not base.endswith("/"):
        base += "/"
    return _urljoin(base, subpath_or_url)


def utcnow() -> datetime:
    """Return the current UTC offset-aware datetime."""
    return datetime.now(timezone.utc)


def send_deprecation_warning(
    old_name: str, new_name: str | None = None
) -> None:  # pragma: no cover
    """Log a deprecation warning message."""
    message = f"{old_name} has been deprecated{'' if new_name is None else f' in favor of {new_name}'} and will be removed in a future release"
    warn(message, DeprecationWarning, stacklevel=2)
    _LOGGER.warning(message)


@overload
def redact(data: Mapping) -> dict: ...


@overload
def redact(data: _T) -> _T: ...


def redact(data: _T) -> _T:
    """Redact sensitive data in a dict."""
    if not isinstance(data, (Mapping, list)):
        return data

    if isinstance(data, list):
        return cast(_T, [redact(val) for val in data])

    redacted = {**data}

    for key, value in redacted.items():
        if value is None:
            continue
        if isinstance(value, str) and not value:
            continue
        if key in REDACT_FIELDS:
            redacted[key] = REDACTED
        elif isinstance(value, Mapping):
            redacted[key] = redact(value)
        elif isinstance(value, list):
            redacted[key] = [redact(item) for item in value]

    return cast(_T, redacted)


def first_value(
    data: dict | None,
    keys: Iterable,
    default: Any | None = None,
    return_none: bool = False,
) -> Any | None:
    """Return the first valid key's value."""
    if not data:
        return default
    for key in keys:
        if key in data and ((value := data[key]) is not None or return_none):
            return value
    return default


def to_enum(value: Any, typ: Type[_E], log_warning: bool = True) -> _E | None:
    """Get the corresponding enum member from a value."""
    if value is None:
        return None
    try:
        return typ(value)
    except ValueError:
        if log_warning:
            logging.warning("Value '%s' not found in enum %s", value, typ.__name__)
    except (AttributeError, TypeError):
        logging.error("Provided class %s is not a valid Enum", typ)
    return None
