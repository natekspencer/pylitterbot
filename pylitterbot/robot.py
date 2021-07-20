import json
import logging
from datetime import datetime, time, timedelta
from typing import List, Optional

import pytz

from .activity import Activity, Insight
from .enums import LitterBoxCommand, LitterBoxStatus
from .exceptions import InvalidCommandException, LitterRobotException
from .session import Session
from .utils import (
    DeprecatedClassMeta,
    from_litter_robot_timestamp,
    round_time,
    send_deprecation_warning,
    today_at_time,
    utcnow,
)

_LOGGER = logging.getLogger(__name__)

CYCLE_CAPACITY = "cycleCapacity"
CYCLE_CAPACITY_DEFAULT = 30
CYCLE_COUNT = "cycleCount"
DRAWER_FULL_CYCLES = "cyclesAfterDrawerFull"
LITTER_ROBOT_ID = "litterRobotId"
LITTER_ROBOT_NICKNAME = "litterRobotNickname"
LITTER_ROBOT_SERIAL = "litterRobotSerial"
SLEEP_MODE_ACTIVE = "sleepModeActive"
SLEEP_MODE_TIME = "sleepModeTime"
UNIT_STATUS = "unitStatus"

SLEEP_DURATION_HOURS = 8
SLEEP_DURATION = timedelta(hours=SLEEP_DURATION_HOURS)

VALID_WAIT_TIMES = [3, 7, 15]


class Robot:
    """Data and methods for interacting with a Litter-Robot Connect self-cleaning litter box"""

    class UnitStatus(metaclass=DeprecatedClassMeta):
        """.. deprecated::

        (deprecated) Use `pylitterbot.enums.LitterBoxStatus` instead.
        """

        _DeprecatedClassMeta__alias = LitterBoxStatus

    class Commands(metaclass=DeprecatedClassMeta):
        """.. deprecated::

        (deprecated) Use `pylitterbot.enums.LitterBoxCommand` instead.
        """

        _DeprecatedClassMeta__alias = LitterBoxCommand

    def __init__(
        self,
        id: str = None,
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
        if not id and not data:
            raise LitterRobotException(
                "An id or data dictionary is required to initilize a Litter-Robot."
            )

        self.__data = dict()
        self.__minimum_cycles_left = 3
        self._sleep_mode_start_time = self._sleep_mode_end_time = None

        self._id = id
        self._name = name
        self._serial = serial
        self._session = session

        self._is_loaded = False
        if data:
            self._update_data(data)

        self._path = f"/users/{user_id}/robots/{self.id}"

    def __str__(self) -> str:
        return f"Name: {self.name}, Serial: {self.serial}, id: {self.id}"

    @property
    def auto_offline_disabled(self) -> bool:
        """Returns `True` if the Litter-Robot's automatic offline status is disabled."""
        return self.__data.get("autoOfflineDisabled", True)

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Returns the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return int(self.__data.get("cleanCycleWaitTimeMinutes", "7"), 16)

    @property
    def cycle_capacity(self) -> int:
        """Returns the cycle capacity of the Litter-Robot."""
        return max(
            int(self.__data.get(CYCLE_CAPACITY, CYCLE_CAPACITY_DEFAULT)),
            self.cycle_count + self.__minimum_cycles_left,
        )

    @property
    def cycle_count(self) -> int:
        """Returns the cycle count since the last time the waste drawer was reset."""
        return int(self.__data.get(CYCLE_COUNT, 0))

    @property
    def cycles_after_drawer_full(self) -> int:
        """Returns the cycles after the drawer is full."""
        return int(self.__data.get(DRAWER_FULL_CYCLES, 0))

    @property
    def device_type(self) -> Optional[str]:
        """Returns the device type of the Litter-Robot."""
        return self.__data.get("deviceType")

    @property
    def did_notify_offline(self) -> bool:
        """Returns `True` if a notification was sent about the Litter-Robot going offline."""
        return self.__data.get("didNotifyOffline", False)

    @property
    def drawer_full_indicator_cycle_count(self) -> int:
        """Returns the cycle count since the drawer full indicator was triggered."""
        return int(self.__data.get("DFICycleCount", 0))

    @property
    def dfi_cycle_count(self) -> int:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `drawer_full_indicator_cycle_count` instead.
        """
        send_deprecation_warning("dfi_cycle_count", "drawer_full_indicator_cycle_count")
        return self.drawer_full_indicator_cycle_count

    @property
    def id(self) -> str:
        """Returns the id of the Litter-Robot."""
        return self._id if self._id else self.__data.get(LITTER_ROBOT_ID)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Returns `True` if the drawer full indicator has been triggered."""
        return self.__data.get("isDFITriggered", "0") != "0"

    @property
    def is_dfi_triggered(self) -> bool:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `is_drawer_full_indicator_triggered` instead.
        """
        send_deprecation_warning(
            "is_dfi_triggered", "is_drawer_full_indicator_triggered"
        )
        return self.is_drawer_full_indicator_triggered

    @property
    def is_onboarded(self) -> bool:
        """Returns `True` if the Litter-Robot is onboarded."""
        return self.__data.get("isOnboarded", False)

    @property
    def is_sleeping(self) -> bool:
        """Returns `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return (
            self.sleep_mode_enabled
            and int(self.__data.get(SLEEP_MODE_ACTIVE)[1:3]) < SLEEP_DURATION_HOURS
        )

    @property
    def is_waste_drawer_full(self) -> bool:
        """Returns `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return (
            self.is_drawer_full_indicator_triggered and self.cycle_count > 9
        ) or self.__minimum_cycles_left < 3

    @property
    def last_seen(self) -> Optional[datetime]:
        """Returns the datetime the Litter-Robot last reported, if any."""
        return from_litter_robot_timestamp(self.__data.get("lastSeen"))

    @property
    def model(self) -> str:
        return (
            "Litter-Robot 3 Connect"
            if self.serial and self.serial.startswith("LR3C")
            else "Other Litter-Robot Connected Device"
        )

    @property
    def name(self) -> Optional[str]:
        """Returns the name of the Litter-Robot, if any."""
        return self._name if self._name else self.__data.get(LITTER_ROBOT_NICKNAME)

    @property
    def night_light_mode_enabled(self) -> bool:
        """Returns `True` if night light mode is enabled."""
        return self.__data.get("nightLightActive", "0") != "0"

    @property
    def night_light_active(self) -> bool:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `night_light_mode_enabled` instead.
        """
        send_deprecation_warning("night_light_active", "night_light_mode_enabled")
        return self.night_light_mode_enabled

    @property
    def panel_lock_enabled(self) -> bool:
        """Returns `True` if the front panel buttons are locked on the Litter-Robot."""
        return self.__data.get("panelLockActive", "0") != "0"

    @property
    def panel_lock_active(self) -> bool:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `panel_lock_enabled` instead.
        """
        send_deprecation_warning("panel_lock_active", "panel_lock_enabled")
        return self.panel_lock_enabled

    @property
    def power_status(self) -> Optional[str]:
        """Returns the power status of the Litter-Robot.

        `AC` = normal,
        `DC` = battery backup,
        `NC` = not connected or off
        """
        return self.__data.get("powerStatus")

    @property
    def serial(self) -> Optional[str]:
        """Returns the serial of the Litter-Robot, if any."""
        return self._serial if self._serial else self.__data.get(LITTER_ROBOT_SERIAL)

    @property
    def setup_date(self) -> Optional[datetime]:
        """Returns the datetime the Litter-Robot was onboarded, if any."""
        return from_litter_robot_timestamp(self.__data.get("setupDate"))

    @property
    def sleep_mode_enabled(self) -> bool:
        """Returns `True` if sleep mode is enabled."""
        return self.__data.get(SLEEP_MODE_ACTIVE, "0") != "0"

    @property
    def sleep_mode_active(self) -> bool:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `sleep_mode_enabled` instead.
        """
        send_deprecation_warning("sleep_mode_active", "sleep_mode_enabled")
        return self.sleep_mode_enabled

    @property
    def sleep_mode_start_time(self) -> Optional[datetime]:
        """Returns the sleep mode start time, if any."""
        return self._sleep_mode_start_time

    @property
    def sleep_mode_end_time(self) -> Optional[datetime]:
        """Returns the sleep mode end time, if any."""
        return self._sleep_mode_end_time

    @property
    def status(self) -> LitterBoxStatus:
        """Returns the status of the Litter-Robot."""
        return LitterBoxStatus(self.status_code)

    @property
    def unit_status(self) -> LitterBoxStatus:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `status` instead.
        """
        send_deprecation_warning("unit_status", "status")
        return self.status

    @property
    def status_code(self) -> Optional[str]:
        """Returns the status code of the Litter-Robot."""
        return self.__data.get(UNIT_STATUS)

    @property
    def status_text(self) -> Optional[str]:
        """Returns the status text of the Litter-Robot."""
        return self.status.text

    @property
    def waste_drawer_level(self) -> float:
        """Returns the approximate waste drawer level."""
        return (self.cycle_count / self.cycle_capacity * 1000 + 0.5) // 1 / 10

    @property
    def waste_drawer_gauge(self) -> int:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `waste_drawer_level` instead.
        """
        send_deprecation_warning("waste_drawer_gauge", "waste_drawer_level")
        return self.waste_drawer_level

    def _update_data(self, data: dict) -> None:
        """Saves the Litter-Robot info from a data dictionary."""
        _LOGGER.debug("Robot data: %s", json.dumps(data))
        self.__data.update(data)
        self._parse_sleep_info()
        self._update_minimum_cycles_left()

        self._is_loaded = True

    def _parse_sleep_info(self) -> None:
        """Parses the sleep info of a Litter-Robot."""
        sleep_mode_active = self.__data.get(SLEEP_MODE_ACTIVE)
        sleep_mode_time = self.__data.get(SLEEP_MODE_TIME)

        start_time = end_time = None

        # The newer API uses `sleepModeTime` to avoid "drift" in the reported sleep start time
        if sleep_mode_time:
            start_time = today_at_time(
                datetime.fromtimestamp(sleep_mode_time, pytz.UTC).timetz()
            )

        # Handle older API sleep start time
        if self.sleep_mode_enabled and not start_time:
            try:
                [hours, minutes, seconds] = list(
                    map(int, sleep_mode_active[1:].split(":"))
                )
                # Round to the nearest minute to reduce "drift"
                start_time = round_time(
                    today_at_time(self.last_seen.timetz())
                    + (
                        timedelta(hours=0 if self.is_sleeping else 24)
                        - timedelta(hours=hours, minutes=minutes, seconds=seconds)
                    )
                )
            except ValueError as ex:
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

    def _update_minimum_cycles_left(self) -> None:
        """Updates the minimum cycles left."""
        if (
            self.status == LitterBoxStatus.READY
            or self.__minimum_cycles_left > self.status.minimum_cycles_left
        ):
            self.__minimum_cycles_left = self.status.minimum_cycles_left

    async def _get(self, subpath: str = "", **kwargs) -> dict:
        """Sends a GET request to the Litter-Robot API."""
        return (await self._session.get(self._path + subpath, **kwargs)).json()

    async def _patch(self, subpath: str = "", json=None, **kwargs) -> dict:
        """Sends a PATCH request to the Litter-Robot API."""
        return (
            await self._session.patch(self._path + subpath, json=json, **kwargs)
        ).json()

    async def _post(self, subpath: str = "", json=None, **kwargs) -> dict:
        """Sends a POST request to the Litter-Robot API."""
        return (
            await self._session.post(self._path + subpath, json=json, **kwargs)
        ).json()

    async def _dispatch_command(self, command: str) -> bool:
        """Sends a command to the Litter-Robot."""
        try:
            await self._post(
                LitterBoxCommand._ENDPOINT,
                {"command": f"{LitterBoxCommand._PREFIX}{command}"},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(f"{ex}")
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = await self._get()
        self._update_data(data)

    async def refresh_robot_info(self) -> None:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `refresh` instead.
        """
        send_deprecation_warning("refresh_robot_info", "refresh")
        await self.refresh()

    async def start_cleaning(self) -> None:
        """Starts a cleaning cycle."""
        await self._dispatch_command(LitterBoxCommand.CLEAN)

    async def reset_settings(self) -> None:
        """Sets the Litter-Robot back to default settings."""
        await self._dispatch_command(LitterBoxCommand.DEFAULT_SETTINGS)

    async def set_panel_lockout(self, value: bool) -> None:
        """Turns the panel lock on or off."""
        await self._dispatch_command(
            LitterBoxCommand.LOCK_ON if value else LitterBoxCommand.LOCK_OFF
        )

    async def set_night_light(self, value: bool) -> None:
        """Turns the night light mode on or off."""
        await self._dispatch_command(
            LitterBoxCommand.NIGHT_LIGHT_ON
            if value
            else LitterBoxCommand.NIGHT_LIGHT_OFF
        )

    async def set_power_status(self, value: bool) -> None:
        """Turns the Litter-Robot on or off."""
        await self._dispatch_command(
            LitterBoxCommand.POWER_ON if value else LitterBoxCommand.POWER_OFF
        )

    async def set_sleep_mode(
        self, value: bool, sleep_time: Optional[time] = None
    ) -> None:
        """Sets the sleep mode on the Litter-Robot."""
        if value and not isinstance(sleep_time, time):
            # Handle being able to set sleep mode by using previous start time or now.
            if not sleep_time:
                sleep_time = (self.sleep_mode_start_time or utcnow()).timetz()
            else:
                raise InvalidCommandException(
                    f"An attempt to turn on sleep mode was received with an invalid time. Check the time and try again."
                )

        data = await self._patch(
            json={
                "sleepModeEnable": value,
                **(
                    {SLEEP_MODE_TIME: int(today_at_time(sleep_time).timestamp())}
                    if sleep_time
                    else {}
                ),
            }
        )
        self._update_data(data)

    async def set_wait_time(self, wait_time: int) -> None:
        """Sets the wait time on the Litter-Robot."""
        if wait_time not in VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {VALID_WAIT_TIMES}, but received {wait_time}"
            )
        await self._dispatch_command(f"{LitterBoxCommand.WAIT_TIME}{f'{wait_time:X}'}")

    async def set_name(self, name: str) -> None:
        """Sets the Litter-Robot's name."""
        data = await self._patch(json={LITTER_ROBOT_NICKNAME: name})
        self._update_data(data)

    async def set_robot_name(self, name: str) -> None:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `set_name` instead.
        """
        send_deprecation_warning("set_robot_name", "set_name")
        await self.set_name(name)

    async def reset_waste_drawer(self) -> None:
        """Resets the Litter-Robot's cycle counts and capacity."""
        data = await self._patch(
            json={
                CYCLE_COUNT: 0,
                CYCLE_CAPACITY: self.cycle_capacity,
                DRAWER_FULL_CYCLES: 0,
            }
        )
        self._update_data(data)

    async def get_activity_history(self, limit: int = 100) -> List[Activity]:
        """Returns the activity history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )

        return [
            Activity(
                from_litter_robot_timestamp(activity["timestamp"]),
                LitterBoxStatus(activity[UNIT_STATUS]),
            )
            for activity in (await self._get("/activity", params={"limit": limit}))[
                "activities"
            ]
        ]

    async def get_robot_activity(
        self, limit: int = 100
    ) -> List[Activity]:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `get_activity_history` instead.
        """
        send_deprecation_warning("get_robot_activity", "get_activity_history")
        return await self.get_activity_history(limit)

    async def get_insight(self, days: int = 30, timezoneOffset: int = None) -> Insight:
        """Returns the insight data."""
        insight = await self._get(
            "/insights",
            params={
                "days": days,
                **(
                    {} if timezoneOffset is None else {"timezoneOffset": timezoneOffset}
                ),
            },
        )
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

    async def get_robot_insights(
        self, days: int = 30, timezoneOffset: int = None
    ) -> Insight:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `get_insight` instead.
        """
        send_deprecation_warning("get_robot_insights", "get_insight")
        return await self.get_insight(days, timezoneOffset)
