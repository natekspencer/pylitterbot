import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Iterable, Optional

import pytz

from .const import CYCLE_CAPACITY, CYCLE_COUNT, DRAWER_FULL_CYCLES, ID, NAME, SERIAL
from .exceptions import InvalidCommandException, LitterRobotException
from .session import Session

_LOGGER = logging.getLogger(__name__)

SLEEP_DURATION = 8


class Robot:
    """Data and methods for interacting with a Litter-Robot Connect self-cleaning litter box"""

    VALID_WAIT_TIMES = [3, 7, 15]

    class UnitStatus(Enum):
        def __new__(cls, value, label):
            obj = object.__new__(cls)
            obj._value_ = value
            obj._label = label
            return obj

        BONNET_REMOVED = ("BR", "Bonnet Removed")
        CLEAN_CYCLE_COMPLETE = ("CCC", "Clean Cycle Complete")
        CLEAN_CYCLE = ("CCP", "Clean Cycle In Progress")
        CAT_SENSOR_FAULT = ("CSF", "Cat Sensor Fault")
        CAT_SENSOR_INTERRUPTED = ("CSI", "Cat Sensor Interrupted")
        CAT_SENSOR_TIMING = ("CST", "Cat Sensor Timing")
        DRAWER_FULL_1 = ("DF1", "Drawer Almost Full - 2 Cycles Left")
        DRAWER_FULL_2 = ("DF2", "Drawer Almost Full - 1 Cycle Left")
        DRAWER_FULL = ("DFS", "Drawer Full")
        DUMP_HOME_POSITION_FAULT = ("DHF", "Dump + Home Position Fault")
        DUMP_POSITION_FAULT = ("DPF", "Dump Position Fault")
        EMPTY_CYCLE = ("EC", "Empty Cycle")
        HOME_POSITION_FAULT = ("HPF", "Home Position Fault")
        OFF = ("OFF", "Off")
        OFFLINE = ("OFFLINE", "Offline")
        OVER_TORQUE_FAULT = ("OTF", "Over Torque Fault")
        PAUSED = ("P", "Clean Cycle Paused")
        PINCH_DETECT = ("PD", "Pinch Detect")
        READY = ("RDY", "Ready")
        STARTUP_CAT_SENSOR_FAULT = ("SCF", "Cat Sensor Fault At Startup")
        STARTUP_DRAWER_FULL = ("SDF", "Drawer Full At Startup")
        STARTUP_PINCH_DETECT = ("SPF", "Pinch Detect At Startup")

        # Handle unknown/future unit statuses
        UNKNOWN = (None, "Unknown Status")

        @classmethod
        def _missing_(cls, _):
            return cls.UNKNOWN

        @property
        def label(self):
            return self._label

    class Commands:
        """Known commands that can be sent to trigger an action or setting for a Litter-Robot Connect self-cleaning litter box"""

        _ENDPOINT = "/dispatch-commands"  # the endpoint to send commands to
        _PREFIX = "<"  # prefix sent in front of commands

        CLEAN = "C"  # start cleaning cycle: unitStatus changes from RDY to CCP; upon completion, cycleCount += 1 and unitStatus briefly goes to CCC and panelLockActive = 1 then typically returns to unitStatus of RDY and panelLockActive of previous state
        DEFAULT_SETTINGS = "D"  # reset settings to defaults: sleepModeActive = 0, panelLockActive = 0, nightLightActive = 1, cleanCycleWaitTimeMinutes = 7
        LOCK_OFF = "L0"  # panel lock off: panelLockActive = 0
        LOCK_ON = "L1"  # panel lock active: panelLockActive = 1
        NIGHT_LIGHT_OFF = "N0"  # night light off: nightLightActive = 0
        NIGHT_LIGHT_ON = "N1"  # night light on: nightLightActive = 1
        POWER_OFF = "P0"  # turn power off: unitStatus changes = OFF; on the next report from the unit, powerStatus changes to NC and cleanCycleWaitTimeMinutes shows as 7; device is still wifi connected, but won't respond to any commands except P1 (power on), sleepModeActive and panelLockActive reset to 0
        POWER_ON = "P1"  # turn power on: powerStatus goes from NC -> AC; cleanCycleWaitTimeMinutes returns to previous value; starts clean cycle (see details on "C" command above)
        # REFRESH = "R"  # valid command, not sure what it does though, reset or refresh maybe? weirdly a new parameter showed up called "cyclesUntilFull" after posting this, but still not sure how it is utilized
        SLEEP_MODE_OFF = "S0"  # turn off sleep mode: sleepModeActive = 0
        SLEEP_MODE_ON = "S1"  # this command is invalid on its own and must be combined with a time component so that it forms the syntax S1HH:MI:SS - turn on sleep mode: sleepModeActive = 1HH:MI:SS; HH:MI:SS is a 24 hour clock that enters sleep mode from 00:00:00-08:00:00, so if at midnight you set sleep mode to 122:30:00, then sleep mode will being in 1.5 hours or 1:30am; when coming out of sleep state, a clean cycle is performed (see details on "C" command above)
        WAIT_TIME = "W"  # set wait time to [3, 7 or 15] minutes: cleanCycleWaitTimeMinutes = [3, 7 or F] (hexadecimal representation of minutes)

    def __init__(
        self,
        id: str = None,
        serial: str = None,
        user_id: str = None,
        name: str = None,
        session: Session = None,
        data: dict = None,
    ):
        """Initialize an instance of a robot with individual attributes or a data dictionary.

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

        self.id = id or data.get(ID)
        self.serial = serial or data.get(SERIAL)
        self.name = name or data.get(NAME)
        self._path = f"/users/{user_id}/robots/{self.id}"
        self._session = session

        self.is_loaded = False

        if data:
            self.save_robot_info(data)

    def __str__(self):
        return f"Name: {self.name}, Serial: {self.serial}, id: {self.id}"

    def save_robot_info(self, data: dict):
        """Saves the robot info from a data dictionary."""
        self.power_status = data.get("powerStatus")
        self.last_seen = self.from_litter_robot_timestamp(data.get("lastSeen"))
        self.auto_offline_disabled = data.get("autoOfflineDisabled")
        self.setup_date = self.from_litter_robot_timestamp(data.get("setupDate"))
        self.dfi_cycle_count = int(data.get("DFICycleCount") or 0)
        self.clean_cycle_wait_time_minutes = int(
            data.get("cleanCycleWaitTimeMinutes") or "0", 16
        )
        self.unit_status = self.UnitStatus(data.get("unitStatus"))
        self.is_onboarded = data.get("isOnboarded")
        self.device_type = data.get("deviceType")
        self.name = data.get(NAME)
        self.cycle_count = int(data.get(CYCLE_COUNT) or 0)
        self.panel_lock_active = data.get("panelLockActive") != "0"
        self.cycles_after_drawer_full = int(data.get(DRAWER_FULL_CYCLES) or 0)
        self.cycle_capacity = int(data.get(CYCLE_CAPACITY) or 10)
        self.night_light_active = data.get("nightLightActive") != "0"
        self.did_notify_offline = data.get("didNotifyOffline")
        self.is_dfi_triggered = data.get("isDFITriggered") != "0"
        self.calculate_sleep_info(
            data.get("sleepModeActive"), data.get("sleepModeTime")
        )

        self.is_loaded = True

    def calculate_sleep_info(
        self, sleep_mode_active: Optional[str], sleep_mode_time: Optional[str] = None
    ):
        """Calculates the sleep info of a robot."""
        self.sleep_mode_active = sleep_mode_active not in ["0", None]

        [start_time, end_time] = [None, None]

        # The newer API uses sleepModeTime to avoid "drift" in the reported sleep start time
        if sleep_mode_time:
            start_time = datetime.fromtimestamp(sleep_mode_time, pytz.UTC)

        self.is_sleeping = False
        if self.sleep_mode_active:
            self.is_sleeping = int(sleep_mode_active[1:3]) < SLEEP_DURATION

            # Handle older API sleep start time
            if not start_time:
                [hours, minutes, seconds] = list(
                    map(int, sleep_mode_active[1:].split(":"))
                )
                start_time = self.last_seen + (
                    timedelta(hours=0 if self.is_sleeping else 24)
                    - timedelta(hours=hours, minutes=minutes, seconds=seconds)
                )
                # Round to the nearest minute to reduce "drift"
                start_time = datetime.fromtimestamp(
                    (start_time.timestamp() + 30) // 60 * 60, start_time.tzinfo
                )

        if start_time:
            end_time = start_time + timedelta(hours=SLEEP_DURATION)

        self.sleep_mode_start_time = start_time
        self.sleep_mode_end_time = end_time

    async def _get(self, subpath: str = "", **kwargs):
        return (await self._session.get(self._path + subpath, **kwargs)).json()

    async def _patch(self, subpath: str = "", json=None, **kwargs):
        return (
            await self._session.patch(self._path + subpath, json=json, **kwargs)
        ).json()

    async def _send(self, subpath: str = "", json=None, **kwargs):
        return (
            await self._session.post(self._path + subpath, json=json, **kwargs)
        ).json()

    async def _dispatch_command(self, command: str):
        try:
            await self._send(
                self.Commands._ENDPOINT,
                {"command": f"{self.Commands._PREFIX}{command}"},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(f"{ex}")
            return False

    async def refresh_robot_info(self):
        """Refresh the robots attributes from the Litter-Robot API."""
        data = await self._get()
        self.save_robot_info(data)

    @property
    def waste_drawer_gauge(self):
        return round(self.cycle_count * 100 / self.cycle_capacity)

    async def start_cleaning(self):
        return await self._dispatch_command(self.Commands.CLEAN)

    async def reset_settings(self):
        return await self._dispatch_command(self.Commands.DEFAULT_SETTINGS)

    async def set_panel_lockout(self, value: bool):
        return await self._dispatch_command(
            self.Commands.LOCK_ON if value else self.Commands.LOCK_OFF
        )

    async def set_night_light(self, value: bool):
        return await self._dispatch_command(
            self.Commands.NIGHT_LIGHT_ON if value else self.Commands.NIGHT_LIGHT_OFF
        )

    async def set_power_status(self, value: bool):
        return await self._dispatch_command(
            self.Commands.POWER_ON if value else self.Commands.POWER_OFF
        )

    async def set_sleep_mode(self, value: bool, sleep_time: Optional[time] = None):
        if value and not isinstance(sleep_time, time):
            raise InvalidCommandException(
                f"An attempt to turn on sleep mode was received with an invalid time. Check the time and try again."
            )

        return await self._patch(
            json={
                "sleepModeEnable": value,
                **(
                    {
                        "sleepModeTime": int(
                            datetime.combine(datetime.now(), sleep_time).timestamp()
                        )
                    }
                    if sleep_time
                    else {}
                ),
            }
        )

    async def set_wait_time(self, wait_time: int):
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        return await self._dispatch_command(
            f"{self.Commands.WAIT_TIME}{f'{wait_time:X}'}"
        )

    async def set_robot_name(self, name: str):
        data = await self._patch(json={NAME: name})
        self.save_robot_info(data)

    async def reset_waste_drawer(self):
        data = await self._patch(
            json={
                CYCLE_COUNT: 0,
                CYCLE_CAPACITY: self.cycle_capacity,
                DRAWER_FULL_CYCLES: 0,
            }
        )
        self.save_robot_info(data)

    async def get_robot_activity(self, limit: int = 100):
        return [
            Activity(
                self.from_litter_robot_timestamp(activity["timestamp"]),
                self.UnitStatus(activity["unitStatus"]),
            )
            for activity in await self._get("/activity", params={"limit": limit})[
                "activities"
            ]
        ]

    async def get_robot_insights(self, days: int = 30, timezoneOffset: int = None):
        insights = await self._get(
            "/insights", params={"days": days, "timezoneOffset": timezoneOffset}
        )
        return Insight(
            insights["totalCycles"],
            insights["averageCycles"],
            [
                Activity(
                    datetime.strptime(cycle["date"], "%Y-%m-%d").date(),
                    count=cycle["cyclesCompleted"],
                )
                for cycle in insights["cycleHistory"]
            ],
        )

    @staticmethod
    def from_litter_robot_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
        """Construct a UTC offset-aware datetime from a Litter-Robot API timestamp.

        Litter-Robot timestamps are in the format `YYYY-MM-DDTHH:MM:SS.ffffff`,
        so to get the UTC offset-aware datetime, we just append `+00:00` and
        call the `datetime.fromisoformat` method.
        """
        if timestamp:
            return datetime.fromisoformat(f"{timestamp}+00:00")


@dataclass
class Activity:
    """Represents a historical activity for a Litter-Robot"""

    timestamp: datetime
    unit_status: Optional[Robot.UnitStatus] = Robot.UnitStatus.READY
    count: Optional[int] = 1

    def __str__(self):
        return f"{self.timestamp}: {self.unit_status.value} - {pluralize('cycle', self.count)}"


@dataclass
class Insight:
    """Represents a summary and count of daily cycles per day for a Litter-Robot"""

    total_cycles: int
    average_cycles: float
    cycle_history: Iterable[Activity]

    @property
    def total_days(self):
        return len(self.cycle_history)

    def __str__(self):
        return f"Completed {pluralize('cycle',self.total_cycles)} averaging {self.average_cycles} cycles per day over the last {pluralize('day',self.total_days)}"


def pluralize(word: str, count: int):
    return f"{count} {word}{'s' if count != 1 else ''}"
