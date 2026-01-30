"""Litter-Robot 5."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from enum import Enum, IntEnum, unique
from typing import TYPE_CHECKING, Any, Dict, Union, cast

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from ..activity import Activity, Insight
from ..enums import LitterBoxStatus, LitterRobot5Command
from ..exceptions import InvalidCommandException, LitterRobotException
from ..utils import to_enum, to_timestamp, utcnow
from .litterrobot import LitterRobot

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

LR5_ENDPOINT = "https://ub.prod.iothings.site"
LR5_STATUS_MAP = {
    "ROBOT_BONNET": LitterBoxStatus.BONNET_REMOVED,
    "ROBOT_CAT_DETECT": LitterBoxStatus.CAT_DETECTED,
    "ROBOT_CAT_DETECT_DELAY": LitterBoxStatus.CAT_SENSOR_TIMING,
    "ROBOT_CLEAN": LitterBoxStatus.CLEAN_CYCLE,
    "ROBOT_EMPTY": LitterBoxStatus.EMPTY_CYCLE,
    "ROBOT_FIND_DUMP": LitterBoxStatus.CLEAN_CYCLE,
    "ROBOT_IDLE": LitterBoxStatus.READY,
    "ROBOT_POWER_DOWN": LitterBoxStatus.POWER_DOWN,
    "ROBOT_POWER_OFF": LitterBoxStatus.OFF,
    "ROBOT_POWER_UP": LitterBoxStatus.POWER_UP,
}
ACTIVITY_STATUS_MAP: dict[str, LitterBoxStatus | str] = {
    "bonnetRemovedYes": LitterBoxStatus.BONNET_REMOVED,
    "catDetectStuckLaser": LitterBoxStatus.CAT_SENSOR_FAULT,
    "catWeight": "Pet Weight Recorded",
    "DFIFullFlagOn": LitterBoxStatus.DRAWER_FULL,
    "litterHopperDispensed": "Litter Dispensed",
    "odometerCleanCycles": "Clean Cycles",
    "powerTypeDC": "Battery Backup",
    "robotCycleStateCatDetect": LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
    "robotCycleStatusDump": LitterBoxStatus.CLEAN_CYCLE,
    "robotCycleStatusIdle": LitterBoxStatus.CLEAN_CYCLE_COMPLETE,
    "robotStatusCatDetect": LitterBoxStatus.CAT_DETECTED,
}
CYCLE_STATE_STATUS_MAP = {
    "CYCLE_STATE_CAT_DETECT": LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
    "CYCLE_STATE_PAUSE": LitterBoxStatus.PAUSED,
}
DISPLAY_CODE_STATUS_MAP = {"DC_CAT_DETECT": LitterBoxStatus.CAT_DETECTED}

LITTER_LEVEL_EMPTY = 500


@unique
class BrightnessLevel(IntEnum):
    """Brightness level of a Litter-Robot 5 unit."""

    LOW = 25
    MEDIUM = 50
    HIGH = 100


@unique
class FirmwareUpdateStatus(Enum):
    """Firmware update status."""

    NONE = "NONE"
    TRIGGERED = "TRIGGERED"
    PICTRIGGERED = "PICTRIGGERED"
    LASERBOARDTRIGGERED = "LASERBOARDTRIGGERED"
    ESPTRIGGERED = "ESPTRIGGERED"
    STARTED = "STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    DELETED = "DELETED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    REMOVED = "REMOVED"
    COMPLETED = "COMPLETED"
    CANCELLATION_IN_PROGRESS = "CANCELLATION_IN_PROGRESS"
    DELETION_IN_PROGRESS = "DELETION_IN_PROGRESS"


@unique
class HopperStatus(Enum):
    """Hopper status."""

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    MOTOR_FAULT_SHORT = "MOTOR_FAULT_SHORT"
    MOTOR_OT_AMPS = "MOTOR_OT_AMPS"
    MOTOR_DISCONNECTED = "MOTOR_DISCONNECTED"
    EMPTY = "EMPTY"


@unique
class LitterLevelState(Enum):
    """Litter level state."""

    OVERFILL = "OVERFILL"
    OPTIMAL = "OPTIMAL"
    REFILL = "REFILL"
    LOW = "LOW"
    EMPTY = "EMPTY"


@unique
class NightLightMode(Enum):
    """Night light mode of a Litter-Robot 5 unit."""

    OFF = "off"
    ON = "on"
    AUTO = "auto"


@unique
class SurfaceType(Enum):
    """Surface type."""

    TILE = "TILE"
    CARPET = "CARPET"
    UNKNOWN = "UNKNOWN"


@unique
class UsbFaultStatus(Enum):
    """USB fault status."""

    NONE = "NONE"
    CLEAR = "CLEAR"
    SET = "SET"


@unique
class WifiModeStatus(Enum):
    """Wi-Fi mode status."""

    NONE = "NONE"
    OFF = "OFF"
    OFF_WAITING = "OFF_WAITING"
    OFF_CONNECTED = "OFF_CONNECTED"
    OFF_FAULT = "OFF_FAULT"
    HOTSPOT_WAITING = "HOTSPOT_WAITING"
    HOTSPOT_CONNECTED = "HOTSPOT_CONNECTED"
    HOTSPOT_FAULT = "HOTSPOT_FAULT"
    ROUTER_WAITING = "ROUTER_WAITING"
    ROUTER_CONNECTED = "ROUTER_CONNECTED"
    ROUTER_FAULT = "ROUTER_FAULT"


class LitterRobot5(LitterRobot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Litter-Robot 5 automatic, self-cleaning litter box."""

    _attr_model = "Litter-Robot 5"

    VALID_WAIT_TIMES = [3, 7, 15, 25, 30]

    _data_cycle_capacity = "DFINumberOfCycles"
    _data_cycle_count = "odometerCleanCycles"
    _data_drawer_full_cycles = "DFIFullCounter"
    _data_id = "serial"
    _data_name = "name"
    _data_power_status = "powerStatus"
    _data_serial = "serial"
    _data_setup_date = "setupDateTime"

    # _command_clean = LitterRobot4Command.CLEAN_CYCLE
    # _command_night_light_off = LitterRobot4Command.NIGHT_LIGHT_MODE_OFF
    # _command_night_light_on = LitterRobot4Command.NIGHT_LIGHT_MODE_AUTO
    # _command_panel_lock_off = LitterRobot4Command.KEY_PAD_LOCK_OUT_OFF
    # _command_panel_lock_on = LitterRobot4Command.KEY_PAD_LOCK_OUT_ON
    # _command_power_off = LitterRobot4Command.POWER_OFF
    # _command_power_on = LitterRobot4Command.POWER_ON

    _litter_level = LITTER_LEVEL_EMPTY
    _litter_level_exp: datetime | None = None

    _firmware_details: dict[str, bool | dict[str, str]] | None = None
    _firmware_details_requested: datetime | None = None

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Litter-Robot 5."""
        super().__init__(data, account)
        self._path = LR5_ENDPOINT

    def _get_data_dict(self, key: str) -> dict[str, Any]:
        """Get a dict from the underlying data object."""
        if isinstance((data := self._data.get(key, {})), dict):
            return data
        _LOGGER.warning("Expected dict for '%s' but got: %s", key, data)
        return {}

    @property
    def _litter_robot_settings(self) -> dict[str, Any]:
        """Return the litter robot settings dict."""
        return self._get_data_dict("litterRobotSettings")

    @property
    def _night_light_settings(self) -> dict[str, Any]:
        """Return the night light settings dict."""
        return self._get_data_dict("nightLightSettings")

    @property
    def _panel_settings(self) -> dict[str, Any]:
        """Return the panel settings dict."""
        return self._get_data_dict("panelSettings")

    @property
    def _state(self) -> dict[str, Any]:
        """Return the state dict."""
        return self._get_data_dict("state")

    @property
    def timezone(self) -> str:
        """Return the timezone."""
        return cast(str, self._data.get("timezone"))

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return number of minutes after a cat uses the Litter-Robot to begin automatic clean."""
        return cast(int, self._litter_robot_settings.get("cycleDelay", 7))

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        fw = self._state.get("firmwareVersions", {})
        mcu = None
        wifi = None
        if isinstance(mcu := fw.get("mcuVersion"), dict):
            mcu = mcu.get("value")
        else:
            mcu = mcu or self._state.get("stmFirmwareVersion")
        if isinstance(wifi := fw.get("wifiVersion"), dict):
            wifi = wifi.get("value")
        else:
            wifi = wifi or self._state.get("espFirmwareVersion")
        return f"ESP: {wifi} / MCU: {mcu}"

    @property
    def firmware_update_status(self) -> str:
        """Return the firmware update status."""
        return cast(
            str,
            self._state.get("espUpdateStatus")
            or self._state.get("firmwareUpdateStatus")
            or "UNKNOWN",
        )

    @property
    def firmware_update_triggered(self) -> bool:
        """Return `True` if a firmware update has been triggered."""
        return self._data.get("isFirmwareUpdateTriggered") is True

    @property
    def hopper_status(self) -> HopperStatus | None:
        """Return the hopper status."""
        return to_enum(self._state.get("hopperStatus"), HopperStatus)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""
        return cast(int, self._state.get("dfiFullCounter", 0)) > 0

    @property
    def is_hopper_removed(self) -> bool | None:
        """Return `True` if the hopper is removed/disabled."""
        return self._state.get("isHopperInstalled") is False

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return self._state.get("isOnline") is True

    @property
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently 'sleeping'."""
        return self._state.get("isSleeping") is True

    @property
    def is_smart_weight_enabled(self) -> bool:
        """Return `True` if smart weight is enabled."""
        return self._litter_robot_settings.get("isSmartWeightEnabled") is True

    @property
    def is_waste_drawer_full(self) -> bool:
        """Return `True` if the Litter-Robot reports the waste drawer is full."""
        return self._state.get("isDrawerFull") is True

    @property
    def litter_level(self) -> float:
        """Return the litter level percent."""
        return cast(float, self._state.get("litterLevelPercent", 0.0))

    @property
    def litter_level_calculated(self) -> float:
        """Return calculated litter level as before but using LR5 keys where present."""
        new_level = int(
            self._state.get(
                "globeLitterLevel", self._state.get("litterLevel", LITTER_LEVEL_EMPTY)
            )
        )
        now = datetime.now(timezone.utc)
        if (
            self._state.get("cycleType") or self._state.get("robotCycleState") or ""
        ).upper().find("CLEAN") != -1:
            self._litter_level_exp = now + timedelta(minutes=1)
        elif (
            self._litter_level_exp is None
            or self._litter_level_exp < now
            or abs(self._litter_level - new_level) < 10
        ):
            self._litter_level = new_level
        return max(round(100 - (self._litter_level - 440) / 0.6, -1), 0)

    @property
    def litter_level_state(self) -> LitterLevelState | None:
        """Return the litter level state."""
        return to_enum(self._state.get("globeLitterLevelIndicator"), LitterLevelState)

    @property
    def night_light_brightness(self) -> int:
        """Return the night light brightness."""
        return int(self._night_light_settings.get("brightness", 0))

    @property
    def night_light_color(self) -> str | None:
        """Return the night light color hex code."""
        return self._night_light_settings.get("color")

    @property
    def night_light_level(self) -> BrightnessLevel | None:
        """Return the night light level."""
        brightness = self._night_light_settings.get("brightness")
        return to_enum(brightness, BrightnessLevel, False)

    @property
    def night_light_mode(self) -> NightLightMode | None:
        """Return the night light mode setting."""
        mode = str(self._night_light_settings.get("mode", "")).lower()
        return to_enum(mode, NightLightMode)

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return str(self._night_light_settings.get("mode", "")).lower() != "off"

    @property
    def panel_brightness(self) -> BrightnessLevel | None:
        """Return the panel brightness."""
        brightness = self._panel_settings.get("brightness")
        if brightness in list(BrightnessLevel):
            return BrightnessLevel(brightness)
        # brightness is numeric (0-100) — map to enum if equals exact values
        try:
            if int(brightness) == BrightnessLevel.LOW:
                return BrightnessLevel.LOW
            if int(brightness) == BrightnessLevel.MEDIUM:
                return BrightnessLevel.MEDIUM
            if int(brightness) == BrightnessLevel.HIGH:
                return BrightnessLevel.HIGH
        except Exception:
            pass
        return None

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if keypad lock is enabled."""
        return cast(
            bool, self._panel_settings.get(LitterRobot5Command.KEYPAD_LOCKED, False)
        )

    @property
    def pet_weight(self) -> float:
        """Return the last recorded pet weight in pounds (lbs)."""
        return cast(float, self._state.get("weightSensor", 0.0))

    @property
    def power_status(self) -> str:
        """Return the power status."""
        return cast(str, self._state.get(self._data_power_status, "On"))

    @property
    def scoops_saved_count(self) -> int:
        """Return the scoops saved count."""
        return cast(int, self._state.get("scoopsSaved", 0))

    @property
    def sleep_mode_enabled(self) -> bool:
        """Return True if sleep mode is enabled for any day."""
        schedules = self._data.get("sleepSchedules") or {}
        return any(day.get("isEnabled", False) for day in schedules)

    @property
    def sleep_mode_start_time(self) -> datetime | None:
        """Return the sleep mode start time, if any."""
        self._revalidate_sleep_info()
        return self._sleep_mode_start_time

    @property
    def sleep_mode_end_time(self) -> datetime | None:
        """Return the sleep mode end time, if any."""
        self._revalidate_sleep_info()
        return self._sleep_mode_end_time

    @property
    def status(self) -> LitterBoxStatus:
        """Return the status of the Litter-Robot).

        Priority:
         - offline check
         - cycleState / cycleType
         - displayCode
         - status (string like 'Ready')
         - fall back to UNKNOWN
        """
        if not self.is_online:
            return LitterBoxStatus.OFFLINE

        # cycle state checks (sample uses 'cycleState' and 'cycleType')
        cycle_state = self._state.get("cycleState") or self._state.get(
            "robotCycleState"
        )
        if cycle_state and (mapped := CYCLE_STATE_STATUS_MAP.get(cycle_state)):
            return mapped

        # displayCode (sample: 'displayCode': 'DcModeIdle')
        display_code = self._state.get("displayCode")
        if display_code and (mapped := DISPLAY_CODE_STATUS_MAP.get(display_code)):
            return mapped

        # status (sample uses 'status': 'Ready')
        raw_status = self._state.get("status") or self._state.get("robotStatus")
        if isinstance(raw_status, str):
            normalized = raw_status.strip().upper()
            # Simple LR5 mapping: common string -> LitterBoxStatus
            if normalized in ("READY", "STROBOTIDLE", "IDLE", "STCYCLEIDLE"):
                status = LitterBoxStatus.READY
            elif "CLEAN" in normalized or "DUMP" in normalized:
                status = LitterBoxStatus.CLEAN_CYCLE
            elif "POWER" in normalized:
                status = LitterBoxStatus.POWER_DOWN
            elif "OFF" in normalized:
                status = LitterBoxStatus.OFF
            else:
                # try LR5 map for backwards compatibility
                status = LR5_STATUS_MAP.get(raw_status, LitterBoxStatus.UNKNOWN)
            # check drawer full
            if status == LitterBoxStatus.READY and self.is_waste_drawer_full:
                return LitterBoxStatus.DRAWER_FULL
            return status

        return LitterBoxStatus.UNKNOWN

    @property
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""
        return (
            self.status.value
            if self.status != LitterBoxStatus.UNKNOWN
            else self._state.get("status")
        )

    @property
    def waste_drawer_level(self) -> float:
        """Return the approximate waste drawer level."""
        return cast(float, self._state.get("dfiLevelPercent", 0.0))

    def _revalidate_sleep_info(self) -> None:
        """Revalidate sleep info."""
        if (
            self.sleep_mode_enabled
            and (now := utcnow()) > (self._sleep_mode_start_time or now)
            and now > (self._sleep_mode_end_time or now)
        ):
            self._parse_sleep_info()

    def _parse_activity(self, activity: dict[str, str]) -> LitterBoxStatus | str:
        """Parse an activity value."""
        value = activity.get("value", "")
        action = ACTIVITY_STATUS_MAP.get(value, value)
        if value == "catWeight":
            action = f"{action}: {activity.get('actionValue')} lbs"
        if value == self._data_cycle_count or value == "odometerCleanCycles":
            action = f"{action}: {activity.get('actionValue')}"
        if value == "litterHopperDispensed":
            action = f"{action}: {activity.get('actionValue')}"
        return action

    def _parse_sleep_info(self) -> None:
        """Parse the sleep info."""
        start = end = None
        try:
            now = (
                datetime.now(ZoneInfo(self.timezone))
                if self.timezone
                else datetime.now(timezone.utc)
            )
        except Exception:
            now = datetime.now(timezone.utc)

        schedules = self._data.get("sleepSchedules")
        # Normalize schedules into a dict keyed by weekday name for compatibility with original code
        schedule_by_weekday: dict[str, dict] = {}

        if isinstance(schedules, list):
            # schedule items are {dayOfWeek: 0-6, isEnabled, sleepTime, wakeTime}
            for item in schedules:
                dow = item.get("dayOfWeek")
                try:
                    day_name = (now + timedelta(days=(dow - now.weekday()))).strftime(
                        "%A"
                    )
                except Exception:
                    # fallback: map 0->Monday per common conventions? Use Python weekday: Monday=0
                    # If user supplies Sunday=0 adjust accordingly. We'll attempt both: check for 0->Sunday vs 0->Monday heuristics.
                    # Try direct mapping first: 0->Monday
                    mapping = [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ]
                    day_name = (
                        mapping[dow]
                        if isinstance(dow, int) and 0 <= dow <= 6
                        else "Monday"
                    )
                schedule_by_weekday[day_name] = item
        elif isinstance(schedules, dict):
            # older shape: direct weekday->schedule mapping
            schedule_by_weekday = schedules
        else:
            schedule_by_weekday = {}

        for idx in range(-7, 8):
            day = now + timedelta(days=idx)
            name = day.strftime("%A")
            schedule = schedule_by_weekday.get(name)
            if not schedule or not schedule.get("isEnabled"):
                continue

            start_of_day = datetime.combine(day.date(), time(), day.tzinfo)
            sleep_time = schedule.get("sleepTime", 0)
            wake_time = schedule.get("wakeTime", 0)
            # sleepTime/wakeTime appear to be minutes from midnight in original code
            if sleep_time < wake_time:
                start = start_of_day + timedelta(minutes=sleep_time)
            else:
                # sleep crosses previous day boundary (e.g., sleep at 22:00, wake at 7:00)
                start = start_of_day - timedelta(minutes=1440 - sleep_time)
            end = start_of_day + timedelta(minutes=wake_time)
            # If now is within this window, break and keep start/end
            if start <= now <= end or start <= now or end >= now:
                break

        self._sleep_mode_start_time = start
        self._sleep_mode_end_time = end

    async def _dispatch_command(self, command: str, **kwargs: Any) -> bool:
        """Send a command to the Litter-Robot."""
        try:
            await self._patch(
                f"robots/{self.serial}",
                json={command: kwargs.get("value")},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = await self._get(f"robots/{self.serial}")
        # data = cast(dict, data)
        self._update_data(data)

    # async def reset(self) -> bool:
    #     """Perform a reset on the Litter-Robot.

    #     Clears errors and may trigger a cycle. Make sure the globe is clear before proceeding.
    #     """
    #     return await self._dispatch_command(LitterRobot4Command.SHORT_RESET_PRESS)

    async def set_name(self, name: str) -> bool:
        """Set the name."""
        data = await self._post(
            json={
                "query": """
                    mutation rename(
                        $serial: String!
                        $name: String
                    ) {
                        updateLitterRobot4(
                            input: {
                                serial: $serial
                                name: $name
                            }
                        ) {
                            name
                        }
                    }
                """,
                "variables": {"serial": self.serial, "name": name},
            }
        )
        updated_data = cast(dict, data).get("data", {}).get("updateLitterRobot4", {})
        self._update_data(updated_data, partial=True)
        return self.name == name

    # async def set_night_light_brightness(
    #     self, brightness: int | BrightnessLevel
    # ) -> bool:
    #     """Set the night light brightness on the robot."""
    #     if brightness not in list(BrightnessLevel):
    #         raise InvalidCommandException(
    #             f"Attempt to send an invalid night light level to Litter-Robot. "
    #             f"Brightness must be one of: {list(BrightnessLevel)}, but received {brightness}"
    #         )
    #     return await self._dispatch_command(
    #         LitterRobot4Command.SET_NIGHT_LIGHT_VALUE,
    #         value=dumps({"nightLightPower": int(brightness)}),
    #     )

    # async def set_night_light_mode(self, mode: NightLightMode) -> bool:
    #     """Set the night light mode on the robot."""
    #     mode_to_command = {
    #         NightLightMode.ON: LitterRobot4Command.NIGHT_LIGHT_MODE_ON,
    #         NightLightMode.OFF: LitterRobot4Command.NIGHT_LIGHT_MODE_OFF,
    #         NightLightMode.AUTO: LitterRobot4Command.NIGHT_LIGHT_MODE_AUTO,
    #     }
    #     return await self._dispatch_command(mode_to_command[mode])

    # async def set_panel_brightness(self, brightness: BrightnessLevel) -> bool:
    #     """Set the panel brightness."""
    #     level_to_command = {
    #         BrightnessLevel.LOW: LitterRobot4Command.PANEL_BRIGHTNESS_LOW,
    #         BrightnessLevel.MEDIUM: LitterRobot4Command.PANEL_BRIGHTNESS_MEDIUM,
    #         BrightnessLevel.HIGH: LitterRobot4Command.PANEL_BRIGHTNESS_HIGH,
    #     }
    #     return await self._dispatch_command(level_to_command[brightness])

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        if await self._dispatch_command(
            LitterRobot5Command.PANEL_SETTINGS,
            value={LitterRobot5Command.KEYPAD_LOCKED: value},
        ):
            data = deepcopy(self._data)
            data[LitterRobot5Command.PANEL_SETTINGS][
                LitterRobot5Command.KEYPAD_LOCKED
            ] = value
            self._update_data(data)
        return self.panel_lock_enabled == value

    async def set_wait_time(self, wait_time: int) -> bool:
        """Set the wait time on the Litter-Robot."""
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        if await self._dispatch_command(
            LitterRobot5Command.LITTER_ROBOT_SETTINGS,
            value={LitterRobot5Command.CYCLE_DELAY: wait_time},
        ):
            data = deepcopy(self._data)
            data[LitterRobot5Command.LITTER_ROBOT_SETTINGS][
                LitterRobot5Command.CYCLE_DELAY
            ] = wait_time
            self._update_data(data)
        return self.clean_cycle_wait_time_minutes == wait_time

    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Return the activity history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )
        data = await self._post(
            json={
                "query": """
                    query GetLR4Activity(
                        $serial: String!
                        $startTimestamp: String
                        $endTimestamp: String
                        $limit: Int
                        $consumer: String
                    ) {
                        getLitterRobot4Activity(
                            serial: $serial
                            startTimestamp: $startTimestamp
                            endTimestamp: $endTimestamp
                            limit: $limit
                            consumer: $consumer
                        ) {
                            serial
                            measure
                            timestamp
                            value
                            actionValue
                            originalHex
                            valueString
                            stateString
                            consumer
                            commandSource
                        }
                    }
                """,
                "variables": {
                    "serial": self.serial,
                    "limit": limit,
                    "consumer": "app",
                },
            }
        )
        activities = cast(dict, data).get("data", {}).get("getLitterRobot4Activity", {})
        if activities is None:
            raise LitterRobotException("Activity history could not be retrieved.")
        return [
            Activity(timestamp, self._parse_activity(activity))
            for activity in activities
            if (timestamp := to_timestamp(activity["timestamp"])) is not None
        ]

    async def get_insight(
        self, days: int = 30, timezone_offset: int | None = None
    ) -> Insight:
        """Return the insight data."""
        data = await self._post(
            json={
                "query": """
                    query GetLR4Insights(
                        $serial: String!
                        $startTimestamp: String
                        $timezoneOffset: Int
                    ) {
                        getLitterRobot4Insights(
                            serial: $serial
                            startTimestamp: $startTimestamp
                            timezoneOffset: $timezoneOffset
                        ) {
                            totalCycles
                            averageCycles
                            cycleHistory {
                                date
                                numberOfCycles
                            }
                            totalCatDetections
                        }
                    }
                """,
                "variables": {
                    "serial": self.serial,
                    "startTimestamp": (utcnow() - timedelta(days=days)).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    "timezoneOffset": timezone_offset,
                },
            }
        )
        insight = cast(dict, data).get("data", {}).get("getLitterRobot4Insights", {})
        if insight is None:
            raise LitterRobotException("Insight data could not be retrieved.")
        return Insight(
            insight["totalCycles"],
            insight["averageCycles"],
            [
                (
                    datetime.strptime(cycle["date"], "%Y-%m-%d").date(),
                    cycle["numberOfCycles"],
                )
                for cycle in insight["cycleHistory"]
            ],
        )

    async def get_firmware_details(
        self, force_check: bool = False
    ) -> dict[str, bool | dict[str, str]] | None:
        """Get the firmware details."""
        if (
            force_check
            or not self._firmware_details
            or (requested := self._firmware_details_requested) is None
            or requested + timedelta(minutes=15) < utcnow()
        ):
            data = await self._post(
                json={
                    "query": """
                        query getFirmwareDetails($serial: String!) {
                            litterRobot4CompareFirmwareVersion(serial: $serial) {
                                isEspFirmwareUpdateNeeded
                                isPicFirmwareUpdateNeeded
                                isLaserboardFirmwareUpdateNeeded
                                latestFirmware {
                                    espFirmwareVersion
                                    picFirmwareVersion
                                    laserBoardFirmwareVersion
                                }
                            }
                        }
                    """,
                    "variables": {"serial": self.serial},
                }
            )
            self._firmware_details = (
                cast(Dict[str, Dict[str, Dict[str, Union[bool, Dict[str, str]]]]], data)
                .get("data", {})
                .get("litterRobot4CompareFirmwareVersion", {})
            )
            self._firmware_details_requested = utcnow()
        return self._firmware_details

    async def get_latest_firmware(self, force_check: bool = False) -> str | None:
        """Get the latest firmware available."""
        if (firmware := await self.get_firmware_details(force_check)) is None:
            return None

        latest_firmware = cast(Dict[str, str], firmware.get("latestFirmware", {}))
        return (
            f"ESP: {latest_firmware.get('espFirmwareVersion')} / "
            f"PIC: {latest_firmware.get('picFirmwareVersion')} / "
            f"TOF: {latest_firmware.get('laserBoardFirmwareVersion')}"
        )

    async def has_firmware_update(self, force_check: bool = False) -> bool:
        """Check if a firmware update is available."""
        if (firmware := await self.get_firmware_details(force_check)) is None:
            return False
        return any(value for value in firmware.values() if isinstance(value, bool))

    async def update_firmware(self) -> bool:
        """Trigger a firmware update."""
        data = await self._post(
            json={
                "query": """
                    mutation updateFirmware($serial: String!) {
                        litterRobot4TriggerFirmwareUpdate(input: {serial: $serial}) {
                            isUpdateTriggered
                            isEspFirmwareUpdateNeeded
                            isPicFirmwareUpdateNeeded
                            isLaserboardFirmwareUpdateNeeded
                        }
                    }
                """,
                "variables": {"serial": self.serial},
            }
        )
        data = cast(dict, data)
        firmware = data.get("data", {}).get("litterRobot4TriggerFirmwareUpdate", {})
        return bool(firmware.get("isUpdateTriggered", False))
