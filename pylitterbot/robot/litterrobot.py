"""Litter-Robot base class."""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime, time
from typing import Any, cast

from ..activity import Activity, Insight
from ..enums import LitterBoxCommand, LitterBoxStatus
from ..utils import to_timestamp
from . import Robot

_LOGGER = logging.getLogger(__name__)


MINIMUM_CYCLES_LEFT_DEFAULT = 3


class LitterRobot(Robot):
    """Data and methods for interacting with a Litter-Robot self-cleaning litter box."""

    VALID_WAIT_TIMES = [3, 7, 15]

    _data_cycle_capacity = "cycleCapacity"
    _data_cycle_capacity_default = 30
    _data_cycle_count = "cycleCount"
    _data_drawer_full_cycles = "cyclesAfterDrawerFull"
    _data_id = "litterRobotId"
    _data_name = "litterRobotNickname"
    _data_power_status = "powerStatus"
    _data_serial = "litterRobotSerial"
    _data_setup_date = "setupDate"

    _command_clean = LitterBoxCommand.CLEAN
    _command_night_light_off = LitterBoxCommand.NIGHT_LIGHT_OFF
    _command_night_light_on = LitterBoxCommand.NIGHT_LIGHT_ON
    _command_panel_lock_off = LitterBoxCommand.LOCK_OFF
    _command_panel_lock_on = LitterBoxCommand.LOCK_ON
    _command_power_off = LitterBoxCommand.POWER_OFF
    _command_power_on = LitterBoxCommand.POWER_ON

    _minimum_cycles_left: int = MINIMUM_CYCLES_LEFT_DEFAULT
    _sleep_mode_start_time: datetime | None = None
    _sleep_mode_end_time: datetime | None = None

    @property
    @abstractmethod
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""

    @property
    def cycle_capacity(self) -> int:
        """Return the total anticpated number of clean cycles that can be performed before the waste drawer is full."""
        return int(
            self._data.get(self._data_cycle_capacity, self._data_cycle_capacity_default)
        )

    @property
    def cycle_count(self) -> int:
        """Return the cycle count since the last time the waste drawer was reset."""
        return int(self._data.get(self._data_cycle_count, 0))

    @property
    def cycles_after_drawer_full(self) -> int:
        """Return the cycles after the drawer is full."""
        return int(self._data.get(self._data_drawer_full_cycles, 0))

    @property
    @abstractmethod
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""

    @property
    def is_onboarded(self) -> bool:
        """Return `True` if the Litter-Robot is onboarded."""
        return self._data.get("isOnboarded") is True

    @property
    @abstractmethod
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""

    @property
    @abstractmethod
    def is_waste_drawer_full(self) -> bool:
        """Return `True` if the Litter-Robot is reporting that the waste drawer is full."""

    @property
    def last_seen(self) -> datetime | None:
        """Return the datetime the Litter-Robot last reported, if any."""
        return to_timestamp(self._data.get("lastSeen"))

    @property
    def power_status(self) -> str:
        """Return the power status.

        `AC` = normal/mains
        `DC` = battery backup
        `NC` = unknown, not connected or off
        """
        return cast(str, self._data.get(self._data_power_status, "NC"))

    @property
    @abstractmethod
    def sleep_mode_enabled(self) -> bool:
        """Return `True` if sleep mode is enabled."""

    @property
    def sleep_mode_start_time(self) -> datetime | None:
        """Return the sleep mode start time, if any."""
        return self._sleep_mode_start_time

    @property
    def sleep_mode_end_time(self) -> datetime | None:
        """Return the sleep mode end time, if any."""
        return self._sleep_mode_end_time

    @property
    @abstractmethod
    def status(self) -> LitterBoxStatus:
        """Return the status of the Litter-Robot."""

    @property
    @abstractmethod
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""

    @property
    def status_text(self) -> str | None:
        """Return the status text of the Litter-Robot."""
        return self.status.text

    @property
    @abstractmethod
    def waste_drawer_level(self) -> float:
        """Return the approximate waste drawer level."""

    def _update_data(
        self,
        data: dict,
        partial: bool = False,
        callback: Callable[[], Any] | None = None,
    ) -> None:
        """Save the Litter-Robot info from a data dictionary."""

        def _callback() -> None:
            self._parse_sleep_info()
            self._update_minimum_cycles_left()

        super()._update_data(data, partial, _callback)

    @abstractmethod
    def _parse_sleep_info(self) -> None:
        """Parse the sleep info of a Litter-Robot."""

    def _update_minimum_cycles_left(self) -> None:
        """Update the minimum cycles left."""
        if (
            self.status == LitterBoxStatus.READY
            or self._minimum_cycles_left > self.status.minimum_cycles_left
        ):
            self._minimum_cycles_left = self.status.minimum_cycles_left

    @abstractmethod
    async def _dispatch_command(self, command: str, **kwargs: Any) -> bool:
        """Send a command to the Litter-Robot."""

    async def start_cleaning(self) -> bool:
        """Start a cleaning cycle."""
        return await self._dispatch_command(self._command_clean)

    async def reset_settings(self) -> bool:  # pragma: no cover
        """Set the Litter-Robot back to default settings."""
        raise NotImplementedError()

    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light mode on or off."""
        return await self._dispatch_command(
            self._command_night_light_on if value else self._command_night_light_off
        )

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        return await self._dispatch_command(
            self._command_panel_lock_on if value else self._command_panel_lock_off
        )

    async def set_power_status(self, value: bool) -> bool:
        """Turn the Litter-Robot on or off."""
        return await self._dispatch_command(
            self._command_power_on if value else self._command_power_off
        )

    async def set_sleep_mode(
        self, value: bool, sleep_time: time | None = None
    ) -> bool:  # pragma: no cover
        """Set the sleep mode on the Litter-Robot."""
        raise NotImplementedError()

    @abstractmethod
    async def set_wait_time(self, wait_time: int) -> bool:
        """Set the wait time on the Litter-Robot."""

    @abstractmethod
    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Return the activity history."""

    @abstractmethod
    async def get_insight(
        self, days: int = 30, timezone_offset: int | None = None
    ) -> Insight:
        """Return the insight data."""
