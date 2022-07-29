"""Litter-Robot base"""
from __future__ import annotations

import logging
from abc import abstractmethod
from datetime import datetime, time

from ..activity import Activity, Insight
from ..enums import LitterBoxCommand, LitterBoxStatus
from ..utils import from_litter_robot_timestamp, send_deprecation_warning
from . import Robot

_LOGGER = logging.getLogger(__name__)


MINIMUM_CYCLES_LEFT_DEFAULT = 3


# Deprecated, please use Robot.VALID_WAIT_TIMES
VALID_WAIT_TIMES = [3, 7, 15]


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

    def __str__(self) -> str:
        return f"Name: {self.name}, Serial: {self.serial}, id: {self.id}"

    @property
    def auto_offline_disabled(self) -> bool:
        """Returns `True` if the Litter-Robot's automatic offline status is disabled."""
        send_deprecation_warning("auto_offline_disabled")
        return self._data.get("autoOfflineDisabled", True)

    @property
    @abstractmethod
    def clean_cycle_wait_time_minutes(self) -> int:
        """Returns the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""

    @property
    def cycle_capacity(self) -> int:
        """Returns the cycle capacity of the Litter-Robot."""
        return int(
            self._data.get(self._data_cycle_capacity, self._data_cycle_capacity_default)
        )

    @property
    def cycle_count(self) -> int:
        """Returns the cycle count since the last time the waste drawer was reset."""
        return int(self._data.get(self._data_cycle_count, 0))

    @property
    def cycles_after_drawer_full(self) -> int:
        """Returns the cycles after the drawer is full."""
        return int(self._data.get(self._data_drawer_full_cycles, 0))

    @property
    def device_type(self) -> str | None:
        """Returns the device type of the Litter-Robot."""
        send_deprecation_warning("device_type")
        return self._data.get("deviceType")

    @property
    def did_notify_offline(self) -> bool:
        """Returns `True` if a notification was sent about the Litter-Robot going offline."""
        send_deprecation_warning("did_notify_offline")
        return self._data.get("didNotifyOffline", False)

    @property
    def drawer_full_indicator_cycle_count(self) -> int:
        """Returns the cycle count since the drawer full indicator was triggered."""
        send_deprecation_warning("drawer_full_indicator_cycle_count")
        return int(self._data.get("DFICycleCount", 0))

    @property
    @abstractmethod
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Returns `True` if the drawer full indicator has been triggered."""

    @property
    def is_onboarded(self) -> bool:
        """Returns `True` if the Litter-Robot is onboarded."""
        return self._data.get("isOnboarded", False)

    @property
    @abstractmethod
    def is_sleeping(self) -> bool:
        """Returns `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""

    @property
    @abstractmethod
    def is_waste_drawer_full(self) -> bool:
        """Returns `True` if the Litter-Robot is reporting that the waste drawer is full."""

    @property
    def last_seen(self) -> datetime | None:
        """Returns the datetime the Litter-Robot last reported, if any."""
        return from_litter_robot_timestamp(self._data.get("lastSeen"))

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the Litter-Robot model."""

    @property
    @abstractmethod
    def night_light_mode_enabled(self) -> bool:
        """Returns `True` if night light mode is enabled."""

    @property
    @abstractmethod
    def panel_lock_enabled(self) -> bool:
        """Returns `True` if the front panel buttons are locked on the Litter-Robot."""

    @property
    def power_status(self) -> str | None:
        """Returns the power status of the Litter-Robot.

        `AC` = normal,
        `DC` = battery backup,
        `NC` = not connected or off
        """
        return self._data.get(self._data_power_status)

    @property
    def setup_date(self) -> datetime | None:
        """Returns the datetime the Litter-Robot was onboarded, if any."""
        return from_litter_robot_timestamp(self._data.get(self._data_setup_date))

    @property
    @abstractmethod
    def sleep_mode_enabled(self) -> bool:
        """Returns `True` if sleep mode is enabled."""

    @property
    def sleep_mode_start_time(self) -> datetime | None:
        """Returns the sleep mode start time, if any."""
        return self._sleep_mode_start_time

    @property
    def sleep_mode_end_time(self) -> datetime | None:
        """Returns the sleep mode end time, if any."""
        return self._sleep_mode_end_time

    @property
    @abstractmethod
    def status(self) -> LitterBoxStatus:
        """Returns the status of the Litter-Robot."""

    @property
    @abstractmethod
    def status_code(self) -> str | None:
        """Returns the status code of the Litter-Robot."""

    @property
    def status_text(self) -> str | None:
        """Returns the status text of the Litter-Robot."""
        return self.status.text

    @property
    @abstractmethod
    def waste_drawer_level(self) -> float:
        """Returns the approximate waste drawer level."""

    def _update_data(self, data: dict) -> None:
        """Saves the Litter-Robot info from a data dictionary."""
        super()._update_data(data)
        self._parse_sleep_info()
        self._update_minimum_cycles_left()

    @abstractmethod
    def _parse_sleep_info(self) -> None:
        """Parses the sleep info of a Litter-Robot."""

    def _update_minimum_cycles_left(self) -> None:
        """Updates the minimum cycles left."""
        if (
            self.status == LitterBoxStatus.READY
            or self._minimum_cycles_left > self.status.minimum_cycles_left
        ):
            self._minimum_cycles_left = self.status.minimum_cycles_left

    async def _get(self, subpath: str = "", **kwargs) -> dict | list[dict]:
        """Sends a GET request to the Litter-Robot API."""
        assert self._session and self._path
        return await self._session.get(self._path + subpath, **kwargs)

    async def _patch(self, subpath: str = "", json=None, **kwargs) -> dict | list[dict]:
        """Sends a PATCH request to the Litter-Robot API."""
        assert self._session and self._path
        return await self._session.patch(self._path + subpath, json=json, **kwargs)

    async def _post(self, subpath: str = "", json=None, **kwargs) -> dict | list[dict]:
        """Sends a POST request to the Litter-Robot API."""
        assert self._session and self._path
        return await self._session.post(self._path + subpath, json=json, **kwargs)

    @abstractmethod
    async def _dispatch_command(self, command: str, **kwargs) -> bool:
        """Sends a command to the Litter-Robot."""

    async def start_cleaning(self) -> bool:
        """Starts a cleaning cycle."""
        return await self._dispatch_command(self._command_clean)

    async def reset_settings(self) -> bool:  # pragma: no cover
        """Sets the Litter-Robot back to default settings."""
        raise NotImplementedError()

    async def set_night_light(self, value: bool) -> bool:
        """Turns the night light mode on or off."""
        return await self._dispatch_command(
            self._command_night_light_on if value else self._command_night_light_off
        )

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turns the panel lock on or off."""
        return await self._dispatch_command(
            self._command_panel_lock_on if value else self._command_panel_lock_off
        )

    async def set_power_status(self, value: bool) -> bool:
        """Turns the Litter-Robot on or off."""
        return await self._dispatch_command(
            self._command_power_on if value else self._command_power_off
        )

    async def set_sleep_mode(
        self, value: bool, sleep_time: time | None = None
    ) -> bool:  # pragma: no cover
        """Sets the sleep mode on the Litter-Robot."""
        raise NotImplementedError()

    @abstractmethod
    async def set_wait_time(self, wait_time: int) -> bool:
        """Sets the wait time on the Litter-Robot."""

    async def set_name(self, name: str) -> bool:  # pragma: no cover
        """Sets the Litter-Robot's name."""
        raise NotImplementedError()

    async def reset_waste_drawer(self) -> bool:  # pragma: no cover
        """Resets the Litter-Robot's cycle counts and capacity."""
        raise NotImplementedError()

    @abstractmethod
    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Returns the activity history."""

    @abstractmethod
    async def get_insight(self, days: int = 30, timezone_offset: int = None) -> Insight:
        """Returns the insight data."""
