"""Utilities module."""
from __future__ import annotations

import json
import logging
from base64 import b64decode, b64encode
from datetime import datetime, time, timezone
from urllib.parse import urljoin as _urljoin
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
    """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp."""
    if not timestamp:
        return None
    if "Z" in timestamp:
        timestamp = timestamp.replace("Z", "")
    if (utc_offset := "+00:00") not in timestamp:
        timestamp += utc_offset
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
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)
