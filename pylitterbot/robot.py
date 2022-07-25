"""pylitterbot robots"""
from __future__ import annotations

import asyncio
import logging
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from json import dumps as json_dumps
from json import loads as json_loads
from uuid import uuid4

import aiohttp
from aiohttp import ClientWebSocketResponse

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .activity import Activity, Insight
from .enums import LitterBoxCommand, LitterBoxStatus, LitterRobot4Command
from .exceptions import InvalidCommandException, LitterRobotException
from .models import LITTER_ROBOT_4_MODEL
from .session import Session
from .utils import (
    encode,
    from_litter_robot_timestamp,
    round_time,
    send_deprecation_warning,
    today_at_time,
    utcnow,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://v2.api.whisker.iothings.site"
DEFAULT_ENDPOINT_KEY = "cDduZE1vajYxbnBSWlA1Q1Z6OXY0VWowYkc3Njl4eTY3NThRUkJQYg=="
LR4_ENDPOINT = "https://lr4.iothings.site/graphql"

MINIMUM_CYCLES_LEFT_DEFAULT = 3
SLEEP_MODE_ACTIVE = "sleepModeActive"
SLEEP_MODE_TIME = "sleepModeTime"
UNIT_STATUS = "unitStatus"

SLEEP_DURATION_HOURS = 8
SLEEP_DURATION = timedelta(hours=SLEEP_DURATION_HOURS)

EVENT_UPDATE = "update"

# Deprecated, please use Robot.VALID_WAIT_TIMES
VALID_WAIT_TIMES = [3, 7, 15]


class Robot:
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

    def __init__(
        self,
        id: str = None,  # pylint:disable=invalid-name,redefined-builtin
        serial: str = None,
        user_id: str = None,  # pylint:disable=unused-argument
        name: str = None,
        session: Session = None,
        data: dict = None,
    ) -> None:
        """Initialize an instance of a Litter-Robot with individual attributes or a data dictionary.

        :param id: Litter-Robot id (optional)
        :param serial: Litter-Robot serial (optional)
        :param user_id: user id that has access to this Litter-Robot (optional)
        :param name: Litter-Robot name (optional)
        :param session: user's session to interact with this Litter-Robot (optional)
        :param data: optional data to pre-populate Litter-Robot's attributes (optional)
        """
        if not id and not data:
            raise LitterRobotException(
                "An id or data dictionary is required to initilize a Litter-Robot."
            )

        self._data: dict = {}

        self._id = id
        self._name = name
        self._serial = serial
        self._session = session

        self._is_loaded = False
        self._path: str | None = None
        self._listeners: dict[str, list[Callable]] = {}

        if data:
            self._update_data(data)

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
    def id(self) -> str:  # pylint:disable=invalid-name
        """Returns the id of the Litter-Robot."""
        return self._id if self._id else self._data[self._data_id]

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
    def name(self) -> str | None:
        """Returns the name of the Litter-Robot, if any."""
        return self._name if self._name else self._data.get(self._data_name)

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
    def serial(self) -> str | None:
        """Returns the serial of the Litter-Robot, if any."""
        return self._serial if self._serial else self._data.get(self._data_serial)

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
        _LOGGER.debug("Robot data: %s", json_dumps(data))
        self._data.update(data)
        self._parse_sleep_info()
        self._update_minimum_cycles_left()

        self._is_loaded = True
        self.emit(EVENT_UPDATE)

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

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""

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

    def on(  # pylint:disable=invalid-name
        self, event_name: str, callback: Callable
    ) -> Callable:
        """Register an event callback."""
        listeners: list = self._listeners.setdefault(event_name, [])
        listeners.append(callback)

        def unsubscribe() -> None:
            """Unsubscribe listeners."""
            if callback in listeners:
                listeners.remove(callback)

        return unsubscribe

    def emit(self, event_name: str, *args, **kwargs) -> None:
        """Run all callbacks for an event."""
        for listener in self._listeners.get(event_name, []):
            try:
                listener(*args, **kwargs)
            except:  # pylint:disable=bare-except
                pass


class LitterRobot3(Robot):
    """Data and methods for interacting with a Litter-Robot 3 automatic, self-cleaning litter box."""

    VALID_WAIT_TIMES = [3, 7, 15]

    def __init__(
        self,
        id: str = None,  # pylint:disable=redefined-builtin
        serial: str = None,
        user_id: str = None,
        name: str = None,
        session: Session = None,
        data: dict = None,
    ) -> None:
        """Initialize an instance of a Litter-Robot with individual attributes or a data dictionary.

        :param id: Litter-Robot id (optional)
        :param serial: Litter-Robot serial (optional)
        :param user_id: user id that has access to this Litter-Robot (optional)
        :param name: Litter-Robot name (optional)
        :param session: user's session to interact with this Litter-Robot (optional)
        :param data: optional data to pre-populate Litter-Robot's attributes (optional)
        """
        super().__init__(id, serial, user_id, name, session, data)
        self._path = f"{DEFAULT_ENDPOINT}/users/{user_id}/robots/{self.id}"

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Returns the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return int(self._data.get("cleanCycleWaitTimeMinutes", "7"), 16)

    @property
    def cycle_capacity(self) -> int:
        """Returns the cycle capacity of the Litter-Robot."""
        minimum_capacity = self.cycle_count + self._minimum_cycles_left
        if self._minimum_cycles_left < MINIMUM_CYCLES_LEFT_DEFAULT:
            return minimum_capacity
        return max(super().cycle_capacity, minimum_capacity)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Returns `True` if the drawer full indicator has been triggered."""
        return self._data.get("isDFITriggered", "0") != "0"

    @property
    def is_sleeping(self) -> bool:
        """Returns `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return (
            self.sleep_mode_enabled
            and int(self._data[SLEEP_MODE_ACTIVE][1:3]) < SLEEP_DURATION_HOURS
        )

    @property
    def is_waste_drawer_full(self) -> bool:
        """Returns `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return (
            self.is_drawer_full_indicator_triggered and self.cycle_count > 9
        ) or self._minimum_cycles_left < MINIMUM_CYCLES_LEFT_DEFAULT

    @property
    def model(self) -> str:
        """Return the Litter-Robot model."""
        return "Litter-Robot 3"

    @property
    def night_light_mode_enabled(self) -> bool:
        """Returns `True` if night light mode is enabled."""
        return self._data.get("nightLightActive", "0") != "0"

    @property
    def panel_lock_enabled(self) -> bool:
        """Returns `True` if the front panel buttons are locked on the Litter-Robot."""
        return self._data.get("panelLockActive", "0") != "0"

    @property
    def sleep_mode_enabled(self) -> bool:
        """Returns `True` if sleep mode is enabled."""
        return self._data.get(SLEEP_MODE_ACTIVE, "0") != "0"

    @property
    def status(self) -> LitterBoxStatus:
        """Returns the status of the Litter-Robot."""
        return LitterBoxStatus(self.status_code)

    @property
    def status_code(self) -> str | None:
        """Returns the status code of the Litter-Robot."""
        return self._data.get(UNIT_STATUS)

    @property
    def waste_drawer_level(self) -> float:
        """Returns the approximate waste drawer level."""
        return (self.cycle_count / self.cycle_capacity * 1000 + 0.5) // 1 / 10

    def _parse_sleep_info(self) -> None:
        """Parses the sleep info of a Litter-Robot."""
        sleep_mode_active = self._data.get(SLEEP_MODE_ACTIVE)
        sleep_mode_time = self._data.get(SLEEP_MODE_TIME)

        start_time = end_time = None

        # The newer API uses `sleepModeTime` to avoid "drift" in the reported sleep start time
        if sleep_mode_time:
            start_time = today_at_time(
                datetime.fromtimestamp(sleep_mode_time, timezone.utc).timetz()
            )

        # Handle older API sleep start time
        if self.sleep_mode_enabled and not start_time:
            assert sleep_mode_active
            try:
                [hours, minutes, seconds] = list(
                    map(int, sleep_mode_active[1:].split(":"))
                )
                # Round to the nearest minute to reduce "drift"
                assert self.last_seen
                start_time = round_time(
                    today_at_time(self.last_seen.timetz())
                    + (
                        timedelta(hours=0 if self.is_sleeping else 24)
                        - timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    )
                )
            except ValueError:
                _LOGGER.error(
                    "Unable to parse sleep mode start time from value '%s'",
                    sleep_mode_active,
                )

        if start_time:
            now = utcnow()
            if start_time <= now - SLEEP_DURATION:
                start_time += timedelta(hours=24)
            end_time = start_time + (
                SLEEP_DURATION if start_time <= now else (SLEEP_DURATION * -2)
            )

        self._sleep_mode_start_time = start_time
        self._sleep_mode_end_time = end_time

    async def _dispatch_command(self, command: str, **kwargs) -> bool:
        """Sends a command to the Litter-Robot."""
        try:
            await self._post(
                LitterBoxCommand.ENDPOINT,
                {"command": f"{LitterBoxCommand.PREFIX}{command}"},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = await self._get()
        assert isinstance(data, dict)
        self._update_data(data)

    async def reset_settings(self) -> bool:
        """Sets the Litter-Robot back to default settings."""
        return await self._dispatch_command(LitterBoxCommand.DEFAULT_SETTINGS)

    async def set_sleep_mode(self, value: bool, sleep_time: time | None = None) -> bool:
        """Sets the sleep mode on the Litter-Robot."""
        if value and not isinstance(sleep_time, time):
            # Handle being able to set sleep mode by using previous start time or now.
            if not sleep_time:
                sleep_time = (self.sleep_mode_start_time or utcnow()).timetz()
            else:
                raise InvalidCommandException(  # pragma: no cover
                    "An attempt to turn on sleep mode was received with an invalid time. Check the time and try again."
                )

        data = await self._patch(
            json={
                "sleepModeEnable": value,
                **(
                    {
                        SLEEP_MODE_TIME: (
                            new_sleep_time := int(today_at_time(sleep_time).timestamp())
                        )
                    }
                    if sleep_time
                    else {}
                ),
            }
        )
        assert isinstance(data, dict)
        self._update_data(data)
        return sleep_time is None or self._data[SLEEP_MODE_TIME] == new_sleep_time

    async def set_wait_time(self, wait_time: int) -> bool:
        """Sets the wait time on the Litter-Robot."""
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        return await self._dispatch_command(
            f"{LitterBoxCommand.WAIT_TIME}{f'{wait_time:X}'}"
        )

    async def set_name(self, name: str) -> bool:
        """Sets the Litter-Robot's name."""
        data = await self._patch(json={self._data_name: name})
        assert isinstance(data, dict)
        self._update_data(data)
        return self.name == name

    async def reset_waste_drawer(self) -> bool:
        """Resets the Litter-Robot's cycle counts and capacity."""
        data = await self._patch(
            json={
                self._data_cycle_count: 0,
                self._data_cycle_capacity: self.cycle_capacity,
                self._data_drawer_full_cycles: 0,
            }
        )
        assert isinstance(data, dict)
        self._update_data(data)
        return self.waste_drawer_level == 0.0

    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Returns the activity history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )
        data = await self._get("/activity", params={"limit": limit})
        assert isinstance(data, dict)
        return [
            Activity(lr_timestamp, LitterBoxStatus(activity[UNIT_STATUS]))
            for activity in data["activities"]
            if (lr_timestamp := from_litter_robot_timestamp(activity["timestamp"]))
            is not None
        ]

    async def get_insight(self, days: int = 30, timezone_offset: int = None) -> Insight:
        """Returns the insight data."""
        insight = await self._get(
            "/insights",
            params={
                "days": days,
                **(
                    {}
                    if timezone_offset is None
                    else {"timezoneOffset": timezone_offset}
                ),
            },
        )
        assert isinstance(insight, dict)
        return Insight(
            insight["totalCycles"],
            insight["averageCycles"],
            [
                Activity(
                    datetime.strptime(cycle["date"], "%Y-%m-%d").date(),
                    count=cycle["cyclesCompleted"],
                )
                for cycle in insight["cycleHistory"]
            ],
        )


LR4_STATUS_MAP = {
    "ROBOT_CAT_DETECT_DELAY": LitterBoxStatus.CAT_SENSOR_TIMING,
    "ROBOT_CLEAN": LitterBoxStatus.CLEAN_CYCLE,
    # "ROBOT_FIND_DUMP": happened during cleaning
    "ROBOT_IDLE": LitterBoxStatus.READY,
    "ROBOT_POWER_OFF": LitterBoxStatus.OFF,
}


class LitterRobot4(Robot):  # pylint:disable=abstract-method
    """Data and methods for interacting with a Litter-Robot 4 automatic, self-cleaning litter box."""

    VALID_WAIT_TIMES = [3, 5, 7, 15, 30]

    _data_cycle_capacity = "DFINumberOfCycles"
    _data_cycle_count = "odometerCleanCycles"
    _data_drawer_full_cycles = "DFIFullCounter"
    _data_id = "unitId"
    _data_name = "name"
    _data_power_status = "unitPowerType"
    _data_serial = "serial"
    _data_setup_date = "setupDateTime"

    _command_clean = LitterRobot4Command.CLEAN_CYCLE
    _command_night_light_off = LitterRobot4Command.NIGHT_LIGHT_MODE_OFF
    _command_night_light_on = LitterRobot4Command.NIGHT_LIGHT_MODE_AUTO
    _command_panel_lock_off = LitterRobot4Command.KEY_PAD_LOCK_OUT_OFF
    _command_panel_lock_on = LitterRobot4Command.KEY_PAD_LOCK_OUT_ON
    _command_power_off = LitterRobot4Command.POWER_OFF
    _command_power_on = LitterRobot4Command.POWER_ON

    def __init__(
        self,
        id: str = None,  # pylint:disable=redefined-builtin
        serial: str = None,
        user_id: str = None,
        name: str = None,
        session: Session = None,
        data: dict = None,
    ) -> None:
        """Initialize an instance of a Litter-Robot with individual attributes or a data dictionary.

        :param id: Litter-Robot id (optional)
        :param serial: Litter-Robot serial (optional)
        :param user_id: user id that has access to this Litter-Robot (optional)
        :param name: Litter-Robot name (optional)
        :param session: user's session to interact with this Litter-Robot (optional)
        :param data: optional data to pre-populate Litter-Robot's attributes (optional)
        """
        super().__init__(id, serial, user_id, name, session, data)
        self._path = LR4_ENDPOINT
        self._ws: ClientWebSocketResponse | None = None
        self._ws_subscription_id: str | None = None
        self._ws_last_received: datetime | None = None

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Returns the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return self._data.get("cleanCycleWaitTime", 7)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Returns `True` if the drawer full indicator has been triggered."""
        return self._data.get("isDFIFull", False)

    @property
    def is_sleeping(self) -> bool:
        """Returns `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return self._data.get("sleepStatus", "WAKE") != "WAKE"

    @property
    def is_waste_drawer_full(self) -> bool:
        """Returns `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return self._data.get("isDFIFull", False)

    @property
    def model(self) -> str:
        """Return the Litter-Robot model."""
        return "Litter-Robot 4"

    @property
    def night_light_mode_enabled(self) -> bool:
        """Returns `True` if night light mode is enabled."""
        return self._data.get("nightLightMode", "OFF") != "OFF"

    @property
    def panel_lock_enabled(self) -> bool:
        """Returns `True` if the front panel buttons are locked on the Litter-Robot."""
        return self._data.get("isKeypadLockout", False)

    @property
    def sleep_mode_enabled(self) -> bool:
        """Returns `True` if sleep mode is enabled."""
        sleep_schedule = self._data["weekdaySleepModeEnabled"]
        return any(day["isEnabled"] for day in sleep_schedule.values())

    @property
    def sleep_mode_start_time(self) -> datetime | None:
        """Returns the sleep mode start time, if any."""
        self._revalidate_sleep_info()
        return self._sleep_mode_start_time

    @property
    def sleep_mode_end_time(self) -> datetime | None:
        """Returns the sleep mode end time, if any."""
        self._revalidate_sleep_info()
        return self._sleep_mode_end_time

    @property
    def status(self) -> LitterBoxStatus:
        """Returns the status of the Litter-Robot."""
        if self.is_waste_drawer_full:
            return LitterBoxStatus.DRAWER_FULL
        return LR4_STATUS_MAP.get(self._data["robotStatus"], LitterBoxStatus.UNKNOWN)

    @property
    def status_code(self) -> str | None:
        """Returns the status code of the Litter-Robot."""
        return (
            self.status.value
            if self.status != LitterBoxStatus.UNKNOWN
            else self._data.get("robotStatus")
        )

    @property
    def waste_drawer_level(self) -> float:
        """Returns the approximate waste drawer level."""
        return self._data.get("DFILevelPercent", 0)

    def _revalidate_sleep_info(self) -> None:
        """Revalidate sleep info."""
        if (
            self.sleep_mode_enabled
            and (now := utcnow()) > (self._sleep_mode_start_time or now)
            and now > (self._sleep_mode_end_time or now)
        ):
            self._parse_sleep_info()

    def _parse_sleep_info(self) -> None:
        """Parses the sleep info of a Litter-Robot."""
        tz_time = time(tzinfo=ZoneInfo(self._data.get("unitTimezone")))
        sleep_schedule = self._data["weekdaySleepModeEnabled"]
        if not any(sleep_schedule[day]["isEnabled"] for day in sleep_schedule):
            self._sleep_mode_start_time = None
            self._sleep_mode_end_time = None
            return
        for i in range(7):
            if not (
                schedule := sleep_schedule[
                    (next_day := (today_at_time(tz_time) + timedelta(days=i))).strftime(
                        "%A"
                    )
                ]
            )["isEnabled"]:
                continue
            if (wake_time := schedule["wakeTime"]) < (
                sleep_time := schedule["sleepTime"]
            ):
                self._sleep_mode_start_time = next_day - timedelta(
                    minutes=1440 - sleep_time
                )
            else:
                self._sleep_mode_start_time = next_day + timedelta(minutes=sleep_time)
            self._sleep_mode_end_time = next_day + timedelta(minutes=wake_time)
            return

    async def _dispatch_command(self, command: str, **kwargs) -> bool:
        """Sends a command to the Litter-Robot."""
        try:
            data = await self._post(
                json={
                    "query": """
                        mutation sendCommand(
                        $serial: String!
                        $command: String!
                        $value: String
                        $commandSource: String
                        ) {
                        sendLitterRobot4Command(
                            input: {
                            serial: $serial
                            command: $command
                            value: $value
                            commandSource: $commandSource
                            }
                        )
                    }
                    """,
                    "variables": {"serial": self.serial, "command": command, **kwargs},
                }
            )
            assert isinstance(data, dict)
            if "Error" in (
                error := data.get("data", {}).get("sendLitterRobot4Command", "")
            ):
                raise InvalidCommandException(error)
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = await self._post(
            json={
                "query": f"""
                    query GetLR4($serial: String!) {{
                        getLitterRobot4BySerial(serial: $serial) {LITTER_ROBOT_4_MODEL}
                    }}
                    """,
                "variables": {"serial": self.serial},
            },
        )
        assert isinstance(data, dict)
        self._update_data(data.get("data", {}).get("getLitterRobot4BySerial", {}))

    async def set_wait_time(self, wait_time: int) -> bool:
        """Sets the wait time on the Litter-Robot."""
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        return await self._dispatch_command(
            LitterRobot4Command.SET_CLUMP_TIME,
            value=json_dumps({"clumpTime": wait_time}),
        )

    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Returns the activity history."""
        _LOGGER.warning("get_activity_history has not yet been implemented")
        return []

    async def get_insight(self, days: int = 30, timezone_offset: int = None) -> Insight:
        """Returns the insight data."""
        _LOGGER.warning("get_insight has not yet been implemented")
        return Insight(0, 0, [])

    async def subscribe_for_updates(self) -> None:
        """Open a web socket connection to receive updates."""
        if self._session is None or self._session.websession is None:
            _LOGGER.warning("Robot has no session")
            return

        async def _authorization() -> str:
            assert self._session
            if not self._session.is_token_valid():
                await self._session.refresh_token()
            return await self._session.get_bearer_authorization()

        async def _subscribe(send_stop: bool = False) -> None:
            assert self._ws
            if send_stop:
                await self._ws.send_json(
                    {"id": self._ws_subscription_id, "type": "stop"}
                )
            self._ws_subscription_id = str(uuid4())

            await self._ws.send_json(
                {
                    "id": self._ws_subscription_id,
                    "payload": {
                        "data": json_dumps(
                            {
                                "query": f"""
                                        subscription GetLR4($serial: String!) {{
                                            litterRobot4StateSubscriptionBySerial(serial: $serial) {LITTER_ROBOT_4_MODEL}
                                        }}
                                    """,
                                "variables": {"serial": self.serial},
                            }
                        ),
                        "extensions": {
                            "authorization": {"Authorization": await _authorization()}
                        },
                    },
                    "type": "start",
                }
            )

        async def _monitor() -> None:
            assert self._ws
            while True:
                try:
                    msg = await self._ws.receive(timeout=80)
                    if msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        break
                    self._ws_last_received = utcnow()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json_loads(msg.data)
                        if (data_type := data["type"]) == "data":
                            self._update_data(
                                data["payload"]["data"][
                                    "litterRobot4StateSubscriptionBySerial"
                                ]
                            )
                        elif data_type == "error":
                            _LOGGER.error(data)
                        elif data_type not in ("start_ack", "ka", "complete"):
                            _LOGGER.debug(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        _LOGGER.error(msg)
                        break
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "Web socket monitor did not receive a message in time"
                    )
                    await _subscribe(send_stop=True)
            _LOGGER.debug("Web socket monitor stopped")

        try:
            self._ws = await self._session.websession.ws_connect(
                f"{self._path}/realtime",
                params={
                    "header": encode(
                        {
                            "Authorization": await _authorization(),
                            "host": "lr4.iothings.site",
                        }
                    ),
                    "payload": encode({}),
                },
                headers={"sec-websocket-protocol": "graphql-ws"},
            )
            asyncio.create_task(_monitor())
            await _subscribe()
        except Exception as ex:  # pylint:disable=broad-except
            _LOGGER.error(ex)

    async def unsubscribe_from_updates(self) -> None:
        """Stop the web socket."""
        if self._ws is not None:
            await self._ws.send_json({"id": self._ws_subscription_id, "type": "stop"})
            await self._ws.close()
            self._ws = None


# FEEDER_ENDPOINT = "https://graphql.whisker.iothings.site/v1/graphql"
