"""Sleep schedule."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from enum import IntEnum

from .utils import utcnow


def _minutes_to_time(minutes: int) -> time:
    return time(hour=(minutes // 60) % 24, minute=minutes % 60)


class DayOfWeek(IntEnum):
    """Day of week enum."""

    SUNDAY = 0
    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6

    @classmethod
    def from_name(cls, name: str) -> DayOfWeek:
        """Return DayOfWeek from name."""
        return cls[name.upper()]

    @classmethod
    def from_date(cls, dt: datetime) -> DayOfWeek:
        """Convert from Python's weekday() (Mon=0) to DayOfWeek (Sun=0)."""
        return cls((dt.weekday() + 1) % 7)


@dataclass
class SleepScheduleDay:
    """Sleep schedule day."""

    day: DayOfWeek
    sleep_time: time
    wake_time: time
    is_enabled: bool

    @classmethod
    def from_named_dict(cls, name: str, data: dict) -> SleepScheduleDay:
        """Return SleepScheduleDay from named dict."""
        return cls(
            day=DayOfWeek.from_name(name),
            sleep_time=_minutes_to_time(data["sleepTime"]),
            wake_time=_minutes_to_time(data["wakeTime"]),
            is_enabled=data["isEnabled"],
        )

    @classmethod
    def from_indexed_dict(cls, data: dict) -> SleepScheduleDay:
        """Return SleepScheduleDay from indexed dict."""
        return cls(
            day=DayOfWeek(data["dayOfWeek"]),
            sleep_time=_minutes_to_time(data["sleepTime"]),
            wake_time=_minutes_to_time(data["wakeTime"]),
            is_enabled=data["isEnabled"],
        )


@dataclass
class SleepSchedule:
    """Sleep schedule."""

    days: list[SleepScheduleDay]
    _cached_window: tuple[datetime, datetime] | None = field(
        default=None, init=False, repr=False
    )

    @property
    def is_enabled(self) -> bool:
        """Return `True` if any day has sleep mode enabled."""
        return any(day.is_enabled for day in self.days)

    @staticmethod
    def parse(raw: dict | list) -> SleepSchedule:
        """Parse a raw dict or list to a SleepSchedule."""
        if isinstance(raw, dict):
            days = [
                SleepScheduleDay.from_named_dict(name, data)
                for name, data in raw.items()
            ]
        elif isinstance(raw, list):
            days = [SleepScheduleDay.from_indexed_dict(day) for day in raw]
        else:
            raise TypeError(f"Unsupported schedule format: {type(raw)}")
        return SleepSchedule(days=sorted(days, key=lambda e: e.day))

    @classmethod
    def from_timestamp(
        cls, sleep_mode_time: int, duration: timedelta, is_enabled: bool = True
    ) -> SleepSchedule | None:
        """Parse a sleep schedule from timestamp."""
        if not sleep_mode_time:
            return None

        sleep_start = datetime.fromtimestamp(sleep_mode_time, timezone.utc)
        sleep_minutes = sleep_start.hour * 60 + sleep_start.minute
        wake_minutes = (sleep_minutes + int(duration.total_seconds() // 60)) % 1440

        days = [
            SleepScheduleDay(
                day=DayOfWeek(i),
                sleep_time=_minutes_to_time(sleep_minutes),
                wake_time=_minutes_to_time(wake_minutes),
                is_enabled=is_enabled,
            )
            for i in range(7)
        ]

        return cls(days=days)

    def get_day(self, day: DayOfWeek) -> SleepScheduleDay | None:
        """Get day."""
        return next((e for e in self.days if e.day == day), None)

    def current_window(
        self, now: datetime | None = None
    ) -> tuple[datetime, datetime] | None:
        """Return the current or next sleep window."""
        if not self.is_enabled:
            return None

        if now is None:
            now = utcnow()

        if (window := self._cached_window) and max(window) > now:
            return window

        start = end = None

        for offset in range(-7, 8):
            day = now + timedelta(days=offset)
            entry = self.get_day(DayOfWeek.from_date(day))
            if entry is None or not entry.is_enabled:
                continue

            sleep_minutes = entry.sleep_time.hour * 60 + entry.sleep_time.minute
            wake_minutes = entry.wake_time.hour * 60 + entry.wake_time.minute

            start_of_day = datetime.combine(day.date(), time(), now.tzinfo)

            if wake_minutes < sleep_minutes:  # crosses midnight
                start = start_of_day - timedelta(minutes=1440 - sleep_minutes)
            else:
                start = start_of_day + timedelta(minutes=sleep_minutes)

            if now >= start or end is None:
                end = start_of_day + timedelta(minutes=wake_minutes)

            if now > max(start, end):
                continue
            break

        if start is None or end is None:
            self._cached_window = None
            return None

        self._cached_window = (start, end)
        return self._cached_window

    def is_active(self, now: datetime | None = None) -> bool:
        """Return `True` if the window is active (sleeping)."""
        if not (window := self.current_window()):
            return False
        if now is None:
            now = utcnow()
        return window[0] <= now < window[1]
