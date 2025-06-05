"""Litter-Robot 4."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from enum import Enum, IntEnum, unique
from json import dumps
from typing import TYPE_CHECKING, Any, Dict, Union, cast
from uuid import uuid4

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from ..activity import Activity, Insight
from ..enums import LitterBoxStatus, LitterRobot4Command
from ..exceptions import InvalidCommandException, LitterRobotException
from ..utils import encode, to_enum, to_timestamp, utcnow
from .litterrobot import LitterRobot
from .models import LITTER_ROBOT_4_MODEL

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

LR4_ENDPOINT = "https://lr4.iothings.site/graphql"
LR4_STATUS_MAP = {
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
    """Brightness level of a Litter-Robot 4 unit."""

    LOW = 25
    MEDIUM = 50
    HIGH = 100


# Deprecated. Use BrightnessLevel.
NightLightLevel = BrightnessLevel


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
    """Night light mode of a Litter-Robot 4 unit."""

    OFF = "OFF"
    ON = "ON"
    AUTO = "AUTO"


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


class LitterRobot4(LitterRobot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Litter-Robot 4 automatic, self-cleaning litter box."""

    _attr_model = "Litter-Robot 4"

    VALID_WAIT_TIMES = [3, 7, 15, 25, 30]

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

    _litter_level = LITTER_LEVEL_EMPTY
    _litter_level_exp: datetime | None = None

    _firmware_details: dict[str, bool | dict[str, str]] | None = None
    _firmware_details_requested: datetime | None = None

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Litter-Robot 4."""
        super().__init__(data, account)
        self._path = LR4_ENDPOINT

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return cast(int, self._data.get("cleanCycleWaitTime", 7))

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        return (
            f"ESP: {self._data.get('espFirmware')} / "
            f"PIC: {self._data.get('picFirmwareVersion')} / "
            f"TOF: {self._data.get('laserBoardFirmwareVersion')}"
        )

    @property
    def firmware_update_status(self) -> str:
        """Return the firmware update status."""
        return cast(str, self._data.get("firmwareUpdateStatus", "UNKNOWN"))

    @property
    def firmware_update_triggered(self) -> bool:
        """Return `True` if a firmware update has been triggered."""
        return self._data.get("isFirmwareUpdateTriggered") is True

    @property
    def hopper_status(self) -> HopperStatus | None:
        """Return the hopper status."""
        return to_enum(self._data.get("hopperStatus"), HopperStatus)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""
        return self._data.get("isDFIFull") is True

    @property
    def is_hopper_removed(self) -> bool | None:
        """Return `True` if the hopper is removed/disabled."""
        return self._data.get("isHopperRemoved") is True

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return self._data.get("isOnline") is True

    @property
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return bool(self._data.get("sleepStatus", "WAKE") != "WAKE")

    @property
    def is_waste_drawer_full(self) -> bool:
        """Return `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return self._data.get("isDFIFull") is True

    @property
    def litter_level(self) -> float:
        """Return the litter level."""
        return cast(float, self._data.get("litterLevelPercentage", 0)) * 100

    @property
    def litter_level_calculated(self) -> float:
        """Return the calculated litter level.

        The litterLevel field from the API is a millimeter distance to the
        top center time of flight (ToF) sensor and is interpreted as:

        ~ 441 full
        ~ 451 nominal
        ~ 461 low
        ~ 471 very low
        """
        new_level = int(self._data.get("litterLevel", LITTER_LEVEL_EMPTY))
        now = datetime.now(timezone.utc)
        if self._data.get("robotStatus") == "ROBOT_CLEAN":
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
        return to_enum(self._data.get("litterLevelState"), LitterLevelState)

    @property
    def night_light_brightness(self) -> int:
        """Return the night light brightness."""
        return int(self._data.get("nightLightBrightness", 0))

    @property
    def night_light_level(self) -> BrightnessLevel | None:
        """Return the night light level."""
        return to_enum(self.night_light_brightness, BrightnessLevel, False)

    @property
    def night_light_mode(self) -> NightLightMode | None:
        """Return the night light mode setting."""
        return to_enum(self._data.get("nightLightMode"), NightLightMode)

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return bool(self._data.get("nightLightMode", "OFF") != "OFF")

    @property
    def panel_brightness(self) -> BrightnessLevel | None:
        """Return the panel brightness."""
        brightness = self._data.get("panelBrightnessHigh")
        if brightness in list(BrightnessLevel):
            return BrightnessLevel(brightness)
        return None

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""
        return self._data.get("isKeypadLockout") is True

    @property
    def pet_weight(self) -> float:
        """Return the last recorded pet weight in pounds (lbs)."""
        return cast(float, self._data.get("catWeight", 0))

    @property
    def scoops_saved_count(self) -> int:
        """Return the scoops saved count."""
        return cast(int, self._data.get("scoopsSavedCount", 0))

    @property
    def sleep_mode_enabled(self) -> bool:
        """Return `True` if sleep mode is enabled."""
        sleep_schedule = self._data["weekdaySleepModeEnabled"]
        return any(day["isEnabled"] for day in sleep_schedule.values())

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
        """Return the status of the Litter-Robot.

        The Litter-Robot 4's status is determined based on the values of:
          - `displayCode`
          - `robotCycleState`
          - `robotStatus`
          - `isDFIFull`
          - `isOnline`
        """
        if not self.is_online:
            return LitterBoxStatus.OFFLINE
        if status := CYCLE_STATE_STATUS_MAP.get(self._data["robotCycleState"]):
            return status
        status = LR4_STATUS_MAP.get(self._data["robotStatus"], LitterBoxStatus.UNKNOWN)
        if status == LitterBoxStatus.READY:
            if display_code := DISPLAY_CODE_STATUS_MAP.get(self._data["displayCode"]):
                return display_code
            if self.is_waste_drawer_full:
                return LitterBoxStatus.DRAWER_FULL
        return status

    @property
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""
        return (
            self.status.value
            if self.status != LitterBoxStatus.UNKNOWN
            else self._data.get("robotStatus")
        )

    @property
    def surface_type(self) -> SurfaceType | None:
        """Return the surface type."""
        return to_enum(self._data.get("surfaceType"), SurfaceType)

    @property
    def usb_fault_status(self) -> UsbFaultStatus | None:
        """Return the USB fault status."""
        return to_enum(self._data.get("USBFaultStatus"), UsbFaultStatus)

    @property
    def waste_drawer_level(self) -> float:
        """Return the approximate waste drawer level."""
        return cast(float, self._data.get("DFILevelPercent", 0))

    @property
    def wifi_mode_status(self) -> WifiModeStatus | None:
        """Return the Wi-Fi mode status."""
        return to_enum(self._data.get("wifiModeStatus"), WifiModeStatus)

    def _revalidate_sleep_info(self) -> None:
        """Revalidate sleep info."""
        if (
            self.sleep_mode_enabled
            and (now := utcnow()) > (self._sleep_mode_start_time or now)
            and now > (self._sleep_mode_end_time or now)
        ):
            self._parse_sleep_info()

    def _parse_activity(self, activity: dict[str, str]) -> LitterBoxStatus | str:
        """Parse an activity."""
        value = activity["value"]
        action = ACTIVITY_STATUS_MAP.get(value, value)
        if value == "catWeight":
            action = f"{action}: {activity['actionValue']} lbs"
        if value == self._data_cycle_count:
            action = f"{action}: {activity['actionValue']}"
        if value == "litterHopperDispensed":
            # TODO: figure out what this value refers to. Could it be a fraction of lbs? Number of motor revolutions?
            action = f"{action}: {activity['actionValue']}"
        return action

    def _parse_sleep_info(self) -> None:
        """Parse the sleep info of a Litter-Robot."""
        start = end = None
        now = datetime.now(ZoneInfo(self._data["unitTimezone"]))
        sleep_schedule = self._data["weekdaySleepModeEnabled"]
        for idx in range(-7, 8):
            day = now + timedelta(days=idx)
            if (schedule := sleep_schedule[day.strftime("%A")])["isEnabled"]:
                start_of_day = datetime.combine(day, time(), day.tzinfo)
                if (wake_time := schedule["wakeTime"]) < (
                    sleep_time := schedule["sleepTime"]
                ):
                    start = start_of_day - timedelta(minutes=1440 - sleep_time)
                else:
                    start = start_of_day + timedelta(minutes=sleep_time)
                if now > start or end is None:
                    end = start_of_day + timedelta(minutes=wake_time)
                if now > max(start, end):
                    continue
                break
        self._sleep_mode_start_time = start
        self._sleep_mode_end_time = end

    async def _dispatch_command(self, command: str, **kwargs: Any) -> bool:
        """Send a command to the Litter-Robot."""
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
            data = cast(dict, data)
            error = data.get("data", {}).get("sendLitterRobot4Command", "")
            if error and "Error" in error:
                raise InvalidCommandException(error)
            if error := ", ".join(e.get("message", "") for e in data.get("errors", {})):
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
        data = cast(dict, data)
        self._update_data(data.get("data", {}).get("getLitterRobot4BySerial", {}))

    async def reset(self) -> bool:
        """Perform a reset on the Litter-Robot.

        Clears errors and may trigger a cycle. Make sure the globe is clear before proceeding.
        """
        return await self._dispatch_command(LitterRobot4Command.SHORT_RESET_PRESS)

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

    async def set_night_light_brightness(
        self, brightness: int | BrightnessLevel
    ) -> bool:
        """Set the night light brightness on the robot."""
        if brightness not in list(BrightnessLevel):
            raise InvalidCommandException(
                f"Attempt to send an invalid night light level to Litter-Robot. "
                f"Brightness must be one of: {list(BrightnessLevel)}, but received {brightness}"
            )
        return await self._dispatch_command(
            LitterRobot4Command.SET_NIGHT_LIGHT_VALUE,
            value=dumps({"nightLightPower": int(brightness)}),
        )

    async def set_night_light_mode(self, mode: NightLightMode) -> bool:
        """Set the night light mode on the robot."""
        mode_to_command = {
            NightLightMode.ON: LitterRobot4Command.NIGHT_LIGHT_MODE_ON,
            NightLightMode.OFF: LitterRobot4Command.NIGHT_LIGHT_MODE_OFF,
            NightLightMode.AUTO: LitterRobot4Command.NIGHT_LIGHT_MODE_AUTO,
        }
        return await self._dispatch_command(mode_to_command[mode])

    async def set_panel_brightness(self, brightness: BrightnessLevel) -> bool:
        """Set the panel brightness."""
        level_to_command = {
            BrightnessLevel.LOW: LitterRobot4Command.PANEL_BRIGHTNESS_LOW,
            BrightnessLevel.MEDIUM: LitterRobot4Command.PANEL_BRIGHTNESS_MEDIUM,
            BrightnessLevel.HIGH: LitterRobot4Command.PANEL_BRIGHTNESS_HIGH,
        }
        return await self._dispatch_command(level_to_command[brightness])

    async def set_wait_time(self, wait_time: int) -> bool:
        """Set the wait time on the Litter-Robot."""
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        return await self._dispatch_command(
            LitterRobot4Command.SET_CLUMP_TIME,
            value=dumps({"clumpTime": wait_time}),
        )

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

    async def toggle_hopper(self, is_removed: bool) -> bool:
        """Enables/Disables the LitterHopper. A disabled hopper is synonymous with being removed. Returns `True` if request was successful.

        NOTE: The API appears to take ~5 seconds to reflect the data changes made by this method. To prevent surprises, this method will fake the expected changes to Hopper-related data properties before returning. If you need a guaranteed state, refresh the data afterwards.
        """
        data = await self._post(
            json={
                "query": """
                    mutation ToggleHopper($serial: String!, $isRemoved: Boolean!) {
                        toggleHopper(serial: $serial, isRemoved: $isRemoved) {
                            success
                        }
                    }
                """,
                "variables": {"serial": self.serial, "isRemoved": is_removed},
            }
        )
        data = cast(dict, data)
        toggle_hopper = data.get("data", {}).get("toggleHopper", {})
        is_success = bool(toggle_hopper.get("success", False))
        if is_success:
            # data is now stale, hopper-related properties will have changed as
            # a consequence. This mutation doesn't expose robot data for a
            # partial update, so we splice in reasonable data changes instead.
            #
            # Unfortunately `hopperStatus` doesn't instantaneously update to
            # reflect the changes from the mutation, so we can't perform a
            # simple data refresh. This is likely due to the LitterHopper
            # device reporting back its own status back to the API.
            self._update_data(
                {
                    "isHopperRemoved": is_removed,
                    "hopperStatus": "DISABLED" if is_removed else "ENABLED",
                },
                partial=True,
            )
        return is_success

    async def send_subscribe_request(self, send_stop: bool = False) -> None:
        """Send a subscribe request and, optionally, unsubscribe from a previous subscription."""
        if not self._ws:
            return
        if send_stop:
            await self.send_unsubscribe_request()
        self._ws_subscription_id = str(uuid4())

        await self._ws.send_json(
            {
                "id": self._ws_subscription_id,
                "payload": {
                    "data": dumps(
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
                        "authorization": {
                            "Authorization": await self._account.get_bearer_authorization(),
                            "host": "lr4.iothings.site",
                        }
                    },
                },
                "type": "start",
            }
        )

    @staticmethod
    async def get_websocket_config(account: Account) -> dict[str, Any]:
        """Get wesocket config."""
        return {
            "url": f"{LR4_ENDPOINT}/realtime",
            "params": {
                "header": encode(
                    {
                        "Authorization": await account.get_bearer_authorization(),
                        "host": "lr4.iothings.site",
                    }
                ),
                "payload": encode({}),
            },
            "headers": {"sec-websocket-protocol": "graphql-ws"},
        }

    @staticmethod
    def parse_websocket_message(data: dict) -> dict | None:
        """Parse a wesocket message."""
        if (data_type := data["type"]) == "data":
            data = data["payload"]["data"]["litterRobot4StateSubscriptionBySerial"]
            return data
        if data_type == "error":
            _LOGGER.error(data)
        elif data_type not in ("start_ack", "ka", "complete"):
            _LOGGER.debug(data)
        return None
