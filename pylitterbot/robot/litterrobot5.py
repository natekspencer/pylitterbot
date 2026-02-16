"""Litter-Robot 5."""

from __future__ import annotations

import asyncio
import logging
import re
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from enum import Enum, IntEnum, unique
from typing import TYPE_CHECKING, Any, cast

from aiohttp import ClientResponseError

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from ..activity import Activity, Insight
from ..enums import LitterBoxStatus, LitterRobot5Command
from ..exceptions import InvalidCommandException
from ..utils import decode, to_enum, to_timestamp, utcnow
from .litterrobot import LitterRobot
from .litterrobot3 import DEFAULT_ENDPOINT_KEY  # reuse existing key material

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

LR5_ENDPOINT = "https://ub.prod.iothings.site"
LR5_OTAUPDATE_ENDPOINT = "https://otaupdate.prod.iothings.site/graphql"
IENSO_ENDPOINT = "https://watford.ienso-dev.com"
IENSO_GENERATE_SESSION_PATH = "api/device-manager/client/generate-session"
LR5_CAMERA_SETTINGS_ENDPOINT = (
    "https://7mnuil943l.execute-api.us-east-1.amazonaws.com/prod/v1/cameras"
)
LR5_CAMERA_INVENTORY_ENDPOINT = (
    "https://rrntg65uwf.execute-api.us-east-1.amazonaws.com/prod/v1/cameras"
)

LR5_CAMERA_CANVAS_FRONT = "sensor_0_1080p"
LR5_CAMERA_CANVAS_GLOBE = "sensor_1_720p"
LR5_CAMERA_CANVAS_LABELS = {
    LR5_CAMERA_CANVAS_FRONT: "Front Camera",
    LR5_CAMERA_CANVAS_GLOBE: "Globe Camera",
}
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
    # LR5-specific statusIndicator types (not part of base LitterBoxStatus set).
    # Map these to the closest existing status code and rely on other sensors for detail.
    "REFILL_LITTER": LitterBoxStatus.READY,
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

    _otaupdate_progress: dict[str, Any] | None = None
    _otaupdate_progress_requested: datetime | None = None

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
    def _sound_settings(self) -> dict[str, Any]:
        """Return the sound settings dict."""
        return self._get_data_dict("soundSettings")

    @property
    def _camera_metadata(self) -> dict[str, Any]:
        """Return the camera metadata dict."""
        return self._get_data_dict("cameraMetadata")

    @property
    def _state(self) -> dict[str, Any]:
        """Return the state dict."""
        return self._get_data_dict("state")

    @property
    def timezone(self) -> str:
        """Return the timezone."""
        return cast(str, self._data.get("timezone"))

    @property
    def robot_variant(self) -> str | None:
        """Return the API-reported robot variant (e.g. LR5_PRO)."""
        value = self._data.get("type")
        return value if isinstance(value, str) else None

    @property
    def updated_at(self) -> datetime | None:
        """Return the last updated timestamp from the API, if any."""
        return to_timestamp(cast(str | None, self._data.get("updatedAt")))

    @property
    def next_filter_replacement_date(self) -> datetime | None:
        """Return the next filter replacement date, if available."""
        return to_timestamp(
            cast(str | None, self._data.get("nextFilterReplacementDate"))
        )

    @property
    def camera_device_id(self) -> str | None:
        """Return the camera device id, if present."""
        value = self._camera_metadata.get("deviceId")
        return value if isinstance(value, str) else None

    @property
    def camera_serial_number(self) -> str | None:
        """Return the camera serial number, if present."""
        value = self._camera_metadata.get("serialNumber")
        return value if isinstance(value, str) else None

    @property
    def camera_space_id(self) -> str | None:
        """Return the camera space id, if present."""
        value = self._camera_metadata.get("spaceId")
        return value if isinstance(value, str) else None

    @property
    def wifi_rssi(self) -> int | None:
        """Return the Wi-Fi RSSI value, if available."""
        value = self._state.get("wifiRssi")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def is_night_light_on(self) -> bool | None:
        """Return True if the night light is currently on (runtime state), if available."""
        value = self._state.get("isNightLightOn")
        if isinstance(value, bool):
            return value
        return None

    @property
    def is_drawer_removed(self) -> bool | None:
        """Return True if the waste drawer is reported removed, if available."""
        value = self._state.get("isDrawerRemoved")
        if isinstance(value, bool):
            return value
        return None

    @property
    def is_usb_fault_detected(self) -> bool | None:
        """Return True if a USB fault is detected, if available."""
        value = self._state.get("isUsbFaultDetected")
        if isinstance(value, bool):
            return value
        return None

    @property
    def is_gas_sensor_fault_detected(self) -> bool | None:
        """Return True if a gas sensor fault is detected, if available."""
        value = self._state.get("isGasSensorFaultDetected")
        if isinstance(value, bool):
            return value
        return None

    @property
    def is_laser_dirty(self) -> bool | None:
        """Return True if the laser is dirty, if available."""
        value = self._state.get("isLaserDirty")
        if isinstance(value, bool):
            return value
        return None

    @property
    def pinch_status(self) -> str | None:
        """Return the pinch sensor status string, if available."""
        value = self._state.get("pinchStatus")
        return value if isinstance(value, str) else None

    @property
    def display_code(self) -> str | None:
        """Return the display code, if available."""
        value = self._state.get("displayCode")
        return value if isinstance(value, str) else None

    @property
    def cycle_state(self) -> str | None:
        """Return the cycle state string, if available."""
        value = self._state.get("cycleState")
        return value if isinstance(value, str) else None

    @property
    def cycle_type(self) -> str | None:
        """Return the cycle type string, if available."""
        value = self._state.get("cycleType")
        return value if isinstance(value, str) else None

    @property
    def cat_detect(self) -> str | None:
        """Return the cat-detect state string, if available."""
        value = self._state.get("catDetect")
        return value if isinstance(value, str) else None

    @property
    def privacy_mode(self) -> str | None:
        """Return the privacy mode string, if available."""
        value = self._state.get("privacyMode")
        return value if isinstance(value, str) else None

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return number of minutes after a cat uses the Litter-Robot to begin automatic clean."""
        return cast(int, self._litter_robot_settings.get("cycleDelay", 7))

    @property
    def cycle_count(self) -> int:
        """Return the cycle count since the last time the waste drawer was reset."""
        try:
            return int(self._state.get("odometerCleanCycles") or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def cycles_after_drawer_full(self) -> int:
        """Return the cycles after the drawer is full."""
        try:
            return int(
                self._state.get("dfiFullCounter")
                or self._state.get("DFIFullCounter")
                or 0
            )
        except (TypeError, ValueError):
            return 0

    @property
    def last_seen(self) -> datetime | None:
        """Return the datetime the Litter-Robot last reported, if any."""
        return to_timestamp(
            cast(str | None, self._state.get("lastSeen") or self._data.get("lastSeen"))
        )

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        fw = self._state.get("firmwareVersions") or {}
        if not isinstance(fw, dict):
            fw = {}

        def _version(entry: Any) -> str | None:
            if isinstance(entry, dict):
                return cast(str | None, entry.get("value"))
            if isinstance(entry, str):
                return entry
            return None

        parts: list[str] = []
        if mcu := _version(fw.get("mcuVersion")) or self._state.get(
            "stmFirmwareVersion"
        ):
            parts.append(f"MCU: {mcu}")
        if edge := _version(fw.get("edgeVersion")):
            parts.append(f"Edge: {edge}")
        if camera := _version(fw.get("cameraVersion")):
            parts.append(f"Camera: {camera}")
        if ai := _version(fw.get("aiVersion")):
            parts.append(f"AI: {ai}")
        if esp := _version(fw.get("wifiVersion")) or self._state.get(
            "espFirmwareVersion"
        ):
            parts.append(f"ESP: {esp}")

        return " / ".join(parts) or "UNKNOWN"

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
        value = self._state.get("hopperStatus")
        if isinstance(value, str):
            value = value.upper()
        return to_enum(value, HopperStatus)

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
        value = self._state.get("globeLitterLevelIndicator")
        if isinstance(value, str):
            value = value.upper()
        return to_enum(value, LitterLevelState)

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
        if brightness is None:
            return None

        try:
            value = int(brightness)
        except (TypeError, ValueError):
            return None

        # If the value exactly matches an enum member, return it. Otherwise the
        # LR5 can report arbitrary values (0-100), so map to the nearest level.
        if value in list(BrightnessLevel):
            return BrightnessLevel(value)

        # Midpoints: 25/50 -> 37.5, 50/100 -> 75.
        if value < 38:
            return BrightnessLevel.LOW
        if value < 75:
            return BrightnessLevel.MEDIUM
        return BrightnessLevel.HIGH

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
        display_intensity = self._panel_settings.get("displayIntensity")
        if isinstance(display_intensity, str):
            mapped = {
                "LOW": BrightnessLevel.LOW,
                "MEDIUM": BrightnessLevel.MEDIUM,
                "HIGH": BrightnessLevel.HIGH,
            }.get(display_intensity.strip().upper())
            if mapped is not None:
                return mapped

        brightness = self._panel_settings.get("brightness")
        if brightness in list(BrightnessLevel):
            return BrightnessLevel(brightness)
        if brightness is None:
            return None
        # brightness is numeric (0-100) — map to enum level
        try:
            value = int(brightness)
        except (TypeError, ValueError):
            return None

        # Midpoints: 25/50 -> 37.5, 50/100 -> 75.
        if value < 38:
            return BrightnessLevel.LOW
        if value < 75:
            return BrightnessLevel.MEDIUM
        return BrightnessLevel.HIGH

    @property
    def panel_brightness_raw(self) -> int | None:
        """Return the raw panel brightness value (0-100) if reported by the API."""
        value = self._panel_settings.get("brightness")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if keypad lock is enabled."""
        return cast(
            bool, self._panel_settings.get(LitterRobot5Command.KEYPAD_LOCKED, False)
        )

    @property
    def pet_weight_raw(self) -> float:
        """Return the raw weight sensor reading from the robot state."""
        value = self._state.get("weightSensor")
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @property
    def pet_weight(self) -> float:
        """Return the last recorded pet weight in pounds (lbs).

        Observed LR5 payloads report weight values in hundredths of pounds:
        - `petWeight`: 1107.0 -> 11.07 lbs
        - `state.weightSensor`: 1110.0 -> 11.10 lbs

        For safety, we only apply the scaling heuristic for values >= 100.
        """
        raw = self.pet_weight_raw
        return raw / 100.0 if raw >= 100 else raw

    @property
    def power_status(self) -> str:
        """Return the power status."""
        return cast(str, self._state.get(self._data_power_status, "On"))

    @property
    def scoops_saved_count(self) -> int:
        """Return the scoops saved count."""
        return cast(int, self._state.get("scoopsSaved", 0))

    @property
    def sound_volume(self) -> int | None:
        """Return the robot sound volume, if available."""
        value = self._sound_settings.get("volume")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @property
    def camera_audio_enabled(self) -> bool | None:
        """Return True if camera audio is enabled, if available."""
        value = self._sound_settings.get("cameraAudioEnabled")
        if isinstance(value, bool):
            return value
        return None

    @property
    def sleep_mode_enabled(self) -> bool:
        """Return True if sleep mode is enabled for any day."""
        schedules = self._data.get("sleepSchedules")
        if isinstance(schedules, list):
            return any(
                item.get("isEnabled", False)
                for item in schedules
                if isinstance(item, dict)
            )
        if isinstance(schedules, dict):
            return any(
                item.get("isEnabled", False)
                for item in schedules.values()
                if isinstance(item, dict)
            )
        return False

    @property
    def setup_date(self) -> datetime | None:
        """Return the datetime the robot was onboarded, if any."""
        return to_timestamp(
            cast(
                str | None,
                self._state.get("setupDateTime") or self._data.get("setupDateTime"),
            )
        )

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
    def sleep_schedules(self) -> list[dict[str, Any]]:
        """Return the raw sleep schedules list, if available."""
        schedules = self._data.get("sleepSchedules")
        if isinstance(schedules, list):
            return [item for item in schedules if isinstance(item, dict)]
        return []

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

        if self._state.get("isBonnetRemoved") is True:
            return LitterBoxStatus.BONNET_REMOVED

        # cycle state checks (sample uses 'cycleState' and 'cycleType')
        cycle_state = self._state.get("cycleState") or self._state.get(
            "robotCycleState"
        )
        if cycle_state and (mapped := CYCLE_STATE_STATUS_MAP.get(cycle_state)):
            return mapped
        cycle_type = self._state.get("cycleType") or self._state.get("robotCycleStatus")

        # displayCode (sample: 'displayCode': 'DcModeIdle')
        display_code = self._state.get("displayCode")
        if display_code and (mapped := DISPLAY_CODE_STATUS_MAP.get(display_code)):
            return mapped

        indicator_type = None
        indicator_title = None
        if isinstance(indicator := self._state.get("statusIndicator"), dict):
            indicator_type = indicator.get("type")
            indicator_title = indicator.get("title")

        candidates = [
            indicator_type,
            indicator_title,
            cycle_state,
            cycle_type,
            self._state.get("state"),
            self._state.get("status"),
            self._state.get("robotStatus"),
        ]
        for raw in candidates:
            if not isinstance(raw, str) or not raw:
                continue
            normalized = raw.strip().upper()
            if normalized in ("READY", "STROBOTIDLE", "IDLE", "STCYCLEIDLE"):
                status = LitterBoxStatus.READY
            elif (
                "CLEAN" in normalized or "PROCESS" in normalized or "DUMP" in normalized
            ):
                status = LitterBoxStatus.CLEAN_CYCLE
            elif "PAUSE" in normalized:
                status = LitterBoxStatus.PAUSED
            elif "EMPTY" in normalized:
                status = LitterBoxStatus.EMPTY_CYCLE
            elif "POWER" in normalized and "DOWN" in normalized:
                status = LitterBoxStatus.POWER_DOWN
            elif "OFF" == normalized:
                status = LitterBoxStatus.OFF
            else:
                status = LR5_STATUS_MAP.get(raw, LitterBoxStatus.UNKNOWN)

            if status == LitterBoxStatus.READY and self.is_waste_drawer_full:
                return LitterBoxStatus.DRAWER_FULL
            if status != LitterBoxStatus.UNKNOWN:
                return status

        return LitterBoxStatus.UNKNOWN

    @property
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""
        status = self.status
        if status != LitterBoxStatus.UNKNOWN:
            return cast(str, status.value)
        return None

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
        schedule_by_weekday: dict[str, dict] = {}
        if isinstance(schedules, list):
            # Observed LR5 shape: list of 7 entries keyed by dayOfWeek 0-6.
            #
            # Heuristic: treat 0 as Sunday to align with common conventions and
            # observed "weekday-only" configs where 1-5 are enabled.
            dow_to_name = [
                "Sunday",
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
            ]
            for item in schedules:
                if not isinstance(item, dict):
                    continue
                raw_dow = item.get("dayOfWeek")
                if raw_dow is None:
                    continue
                try:
                    dow = int(raw_dow)
                except (TypeError, ValueError):
                    continue
                if 0 <= dow <= 6:
                    schedule_by_weekday[dow_to_name[dow]] = item
        elif isinstance(schedules, dict):
            schedule_by_weekday = schedules

        windows: list[tuple[datetime, datetime]] = []
        for idx in range(-7, 8):
            day = now + timedelta(days=idx)
            schedule = schedule_by_weekday.get(day.strftime("%A"))
            if not isinstance(schedule, dict) or not schedule.get("isEnabled"):
                continue

            start_of_day = datetime.combine(day.date(), time(), day.tzinfo)
            try:
                sleep_time = int(schedule.get("sleepTime", 0))
                wake_time = int(schedule.get("wakeTime", 0))
            except (TypeError, ValueError):
                continue

            # Interpret sleepTime/wakeTime as minutes from midnight for this weekday.
            # If sleep_time > wake_time, the window crosses into the next day.
            start_candidate = start_of_day + timedelta(minutes=sleep_time)
            if sleep_time < wake_time:
                end_candidate = start_of_day + timedelta(minutes=wake_time)
            else:
                end_candidate = start_of_day + timedelta(days=1, minutes=wake_time)

            if end_candidate <= start_candidate:
                continue
            windows.append((start_candidate, end_candidate))

        if windows:
            windows.sort(key=lambda w: w[0])
            # Prefer the currently-active window; otherwise choose the next one.
            for s, e in windows:
                if s <= now < e:
                    start, end = s, e
                    break
            else:
                for s, e in windows:
                    if s > now:
                        start, end = s, e
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
        if isinstance(data, dict):
            self._update_data(data)
        else:
            _LOGGER.warning(
                "Unexpected refresh payload for %s: %s",
                self.serial,
                type(data).__name__,
            )

    async def send_subscribe_request(self, send_stop: bool = False) -> None:
        """Send a subscribe request and, optionally, unsubscribe from a previous subscription.

        Litter-Robot 5 does not currently support real-time state subscriptions via
        this library, so this is a no-op.
        """
        return

    async def _dispatch_command_bus(self, command_type: str) -> bool:
        """Send a command over the LR5 command bus.

        This uses `POST /robots/{serial}/commands` with JSON: {"type": "..."}.
        """
        try:
            await self._post(
                f"robots/{self.serial}/commands",
                json={"type": command_type},
            )
            return True
        except (InvalidCommandException, ClientResponseError) as ex:
            _LOGGER.error(ex)
            return False

    async def start_cleaning(self) -> bool:
        """Start a cleaning cycle."""
        return await self._dispatch_command_bus("CLEAN_CYCLE")

    # async def reset(self) -> bool:
    #     """Perform a reset on the Litter-Robot.

    #     Clears errors and may trigger a cycle. Make sure the globe is clear before proceeding.
    #     """
    #     return await self._dispatch_command(LitterRobot4Command.SHORT_RESET_PRESS)

    async def set_name(self, name: str) -> bool:
        """Set the name."""
        await self._patch(
            f"robots/{self.serial}",
            json={"name": name},
        )
        self._update_data({"name": name})
        return self.name == name

    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light mode on or off."""
        mode = "Auto" if value else "Off"
        await self._patch(
            f"robots/{self.serial}",
            json={
                "nightLightSettings": {
                    "mode": mode,
                }
            },
        )

        data = deepcopy(self._data)
        data.setdefault("nightLightSettings", {})
        if isinstance(data.get("nightLightSettings"), dict):
            data["nightLightSettings"]["mode"] = mode
        self._update_data(data)
        return self.night_light_mode_enabled == value

    async def set_power_status(self, value: bool) -> bool:
        """Turn the Litter-Robot on or off."""
        ok = await self._dispatch_command_bus("POWER_ON" if value else "POWER_OFF")
        if ok:
            data = deepcopy(self._data)
            data.setdefault("state", {})
            if isinstance(data.get("state"), dict):
                data["state"]["powerStatus"] = "On" if value else "Off"
            self._update_data(data)
        return ok

    async def set_sleep_mode(self, value: bool, sleep_time: time | None = None) -> bool:
        """Set sleep mode by enabling/disabling all weekday schedules.

        Unlike LR3, the LR5 does not have a single "sleep mode enable" flag. The
        API stores a per-weekday schedule list under `sleepSchedules`.

        This method maps the base-class API onto LR5 by:
          - `value=False`: disabling all days (preserving configured times)
          - `value=True`: enabling all days (optionally updating `sleepTime`)
        """
        if value and sleep_time is not None and not isinstance(sleep_time, time):
            raise InvalidCommandException(
                "An attempt to turn on sleep mode was received with an invalid time. "
                "Check the time and try again."
            )

        sleep_minutes: int | None = None
        if value and isinstance(sleep_time, time):
            sleep_minutes = int(sleep_time.hour) * 60 + int(sleep_time.minute)
            # Seconds are ignored; the API uses minute precision.
            if sleep_minutes < 0 or sleep_minutes > 1439:
                raise InvalidCommandException(
                    f"Invalid sleep_time {sleep_time!r}, expected within 00:00-23:59"
                )

        existing = self.sleep_schedules
        by_dow: dict[int, dict[str, Any]] = {}
        for item in existing:
            raw_dow = item.get("dayOfWeek")
            if raw_dow is None:
                continue
            try:
                dow = int(raw_dow)
            except (TypeError, ValueError):
                continue
            if 0 <= dow <= 6 and dow not in by_dow:
                by_dow[dow] = dict(item)

        schedules: list[dict[str, Any]] = []
        for dow in range(7):
            entry = by_dow.get(dow) or {
                "dayOfWeek": dow,
                "isEnabled": False,
                "sleepTime": 0,
                "wakeTime": 0,
            }
            entry = {**entry, "dayOfWeek": dow, "isEnabled": bool(value)}
            if sleep_minutes is not None:
                entry["sleepTime"] = sleep_minutes
            schedules.append(entry)

        await self._patch(
            f"robots/{self.serial}",
            json={"sleepSchedules": schedules},
        )

        data = deepcopy(self._data)
        data["sleepSchedules"] = schedules
        self._update_data(data)
        return self.sleep_mode_enabled == bool(value)

    async def set_night_light_brightness(
        self, brightness: int | BrightnessLevel
    ) -> bool:
        """Set the night light brightness.

        The LR5 supports arbitrary brightness values (0-100).
        """
        value = int(brightness)
        if value < 0 or value > 100:
            raise InvalidCommandException(
                "Attempt to send an invalid night light brightness to Litter-Robot. "
                f"Brightness must be within 0-100, but received {brightness}"
            )

        await self._patch(
            f"robots/{self.serial}",
            json={"nightLightSettings": {"brightness": value}},
        )

        data = deepcopy(self._data)
        settings = data.setdefault("nightLightSettings", {})
        if isinstance(settings, dict):
            settings["brightness"] = value
        self._update_data(data)
        return self.night_light_brightness == value

    async def set_night_light_color(self, color: str) -> bool:
        """Set the night light color hex string."""
        if not isinstance(color, str) or not re.match(
            r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$",
            color,
        ):
            raise InvalidCommandException(
                "Attempt to send an invalid night light color to Litter-Robot. "
                f"Expected a hex string like '#FFF'/'#FFF5'/'#FFFFFF'/'#FFFFFFFF', got {color!r}"
            )

        # Empirically, PATCHing only "color" can cause the backend to normalize
        # (reset) other nightLightSettings fields. Preserve the currently-known
        # mode + brightness by sending the full object.
        raw_mode = self._night_light_settings.get("mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            mode_value = raw_mode.strip().title()
        else:
            mode_value = (self.night_light_mode or NightLightMode.OFF).value.title()
        brightness_value = int(self.night_light_brightness)

        await self._patch(
            f"robots/{self.serial}",
            json={
                "nightLightSettings": {
                    "mode": mode_value,
                    "brightness": brightness_value,
                    "color": color,
                }
            },
        )

        data = deepcopy(self._data)
        settings = data.setdefault("nightLightSettings", {})
        if isinstance(settings, dict):
            settings["mode"] = mode_value
            settings["brightness"] = brightness_value
            settings["color"] = color
        self._update_data(data)
        return self.night_light_color == color

    async def set_night_light_mode(self, mode: NightLightMode) -> bool:
        """Set the night light mode."""
        mode_value = mode.value.title()
        await self._patch(
            f"robots/{self.serial}",
            json={"nightLightSettings": {"mode": mode_value}},
        )

        data = deepcopy(self._data)
        settings = data.setdefault("nightLightSettings", {})
        if isinstance(settings, dict):
            settings["mode"] = mode_value
        self._update_data(data)
        return self.night_light_mode == mode

    async def set_panel_brightness(self, brightness: BrightnessLevel) -> bool:
        """Set the panel brightness."""
        intensity = {
            BrightnessLevel.LOW: "Low",
            BrightnessLevel.MEDIUM: "Medium",
            BrightnessLevel.HIGH: "High",
        }.get(brightness)
        if intensity is None:
            raise InvalidCommandException(
                f"Attempt to send an invalid panel brightness to Litter-Robot. Expected {list(BrightnessLevel)}, got {brightness}"
            )

        await self._patch(
            f"robots/{self.serial}",
            json={"panelSettings": {"displayIntensity": intensity}},
        )

        data = deepcopy(self._data)
        settings = data.setdefault("panelSettings", {})
        if isinstance(settings, dict):
            settings["displayIntensity"] = intensity
        self._update_data(data)
        return self.panel_brightness == brightness

    async def set_sound_volume(self, volume: int) -> bool:
        """Set the robot sound volume (range to confirm; 0-100 accepted)."""
        if volume < 0 or volume > 100:
            raise InvalidCommandException(
                f"Attempt to send an invalid sound volume to Litter-Robot. Volume must be within 0-100, but received {volume}"
            )

        await self._patch(
            f"robots/{self.serial}",
            json={"soundSettings": {"volume": volume}},
        )

        data = deepcopy(self._data)
        settings = data.setdefault("soundSettings", {})
        if isinstance(settings, dict):
            settings["volume"] = volume
        self._update_data(data)
        return self.sound_volume == volume

    async def set_camera_audio_enabled(self, value: bool) -> bool:
        """Enable or disable camera audio."""
        await self._patch(
            f"robots/{self.serial}",
            json={"soundSettings": {"cameraAudioEnabled": value}},
        )

        data = deepcopy(self._data)
        settings = data.setdefault("soundSettings", {})
        if isinstance(settings, dict):
            settings["cameraAudioEnabled"] = value
        self._update_data(data)
        return self.camera_audio_enabled == value

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        if await self._dispatch_command(
            LitterRobot5Command.PANEL_SETTINGS,
            value={LitterRobot5Command.KEYPAD_LOCKED: value},
        ):
            data = deepcopy(self._data)
            settings = data.setdefault(LitterRobot5Command.PANEL_SETTINGS, {})
            if isinstance(settings, dict):
                settings[LitterRobot5Command.KEYPAD_LOCKED] = value
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
            settings = data.setdefault(LitterRobot5Command.LITTER_ROBOT_SETTINGS, {})
            if isinstance(settings, dict):
                settings[LitterRobot5Command.CYCLE_DELAY] = wait_time
            self._update_data(data)
        return self.clean_cycle_wait_time_minutes == wait_time

    async def set_sleep_schedule(
        self,
        day_of_week: int,
        *,
        is_enabled: bool,
        sleep_time: int,
        wake_time: int,
    ) -> bool:
        """Set a single day sleep schedule.

        The LR5 API represents sleep schedules as a list of 7 entries:
          {"dayOfWeek": 0-6, "isEnabled": bool, "sleepTime": minutes, "wakeTime": minutes}
        """
        if day_of_week < 0 or day_of_week > 6:
            raise InvalidCommandException(
                f"Invalid day_of_week {day_of_week}, expected 0-6"
            )
        for name, value in (("sleep_time", sleep_time), ("wake_time", wake_time)):
            if value < 0 or value > 1439:
                raise InvalidCommandException(
                    f"Invalid {name} {value}, expected 0-1439 minutes from midnight"
                )

        existing = self.sleep_schedules
        by_dow: dict[int, dict[str, Any]] = {}
        for item in existing:
            raw_dow = item.get("dayOfWeek")
            if raw_dow is None:
                continue
            try:
                dow = int(raw_dow)
            except (TypeError, ValueError):
                continue
            if 0 <= dow <= 6 and dow not in by_dow:
                by_dow[dow] = dict(item)

        schedules: list[dict[str, Any]] = []
        for dow in range(7):
            entry = by_dow.get(dow) or {
                "dayOfWeek": dow,
                "isEnabled": False,
                "sleepTime": 0,
                "wakeTime": 0,
            }
            if dow == day_of_week:
                entry = {
                    **entry,
                    "dayOfWeek": dow,
                    "isEnabled": bool(is_enabled),
                    "sleepTime": int(sleep_time),
                    "wakeTime": int(wake_time),
                }
            schedules.append(entry)

        await self._patch(
            f"robots/{self.serial}",
            json={"sleepSchedules": schedules},
        )

        data = deepcopy(self._data)
        data["sleepSchedules"] = schedules
        self._update_data(data)

        updated = next(
            (
                item
                for item in self.sleep_schedules
                if int(item.get("dayOfWeek", -1)) == day_of_week
            ),
            None,
        )
        try:
            return bool(
                isinstance(updated, dict)
                and updated.get("isEnabled") == bool(is_enabled)
                and int(updated.get("sleepTime", -1)) == int(sleep_time)
                and int(updated.get("wakeTime", -1)) == int(wake_time)
            )
        except (TypeError, ValueError):
            return False

    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Return the activity history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )

        data = await self._get(f"robots/{self.serial}/activities?limit={limit}")
        if not isinstance(data, list):
            raise InvalidCommandException("Activity history could not be retrieved.")

        type_to_action: dict[str, LitterBoxStatus | str] = {
            "BONNET_REMOVED": LitterBoxStatus.BONNET_REMOVED,
            "CAT_DETECT": LitterBoxStatus.CAT_DETECTED,
            "CYCLE_COMPLETED": LitterBoxStatus.CLEAN_CYCLE_COMPLETE,
            "CYCLE_INTERRUPTED": LitterBoxStatus.PAUSED,
            "DRAWER_FULL": LitterBoxStatus.DRAWER_FULL,
            "OFFLINE": LitterBoxStatus.OFFLINE,
            "PET_VISIT": "Pet Visit",
        }

        activities: list[Activity] = []
        for item in data:
            timestamp = to_timestamp(
                cast(str | None, item.get("timestamp") or item.get("visitTime"))
            )
            if timestamp is None:
                continue

            raw_type = item.get("type")
            raw_subtype = item.get("subtype")
            action: LitterBoxStatus | str
            if isinstance(raw_type, str) and raw_type in type_to_action:
                action = type_to_action[raw_type]
            elif isinstance(raw_subtype, str) and raw_subtype:
                action = raw_subtype
            elif isinstance(raw_type, str) and raw_type:
                action = raw_type
            else:
                action = "Unknown"

            if action == "Pet Visit":
                pet_weight = item.get("petWeight")
                if pet_weight is not None:
                    try:
                        raw_weight = float(pet_weight)
                        lbs = raw_weight / 100.0 if raw_weight >= 100 else raw_weight
                        action = f"Pet Visit: {lbs:.2f} lbs"
                    except (TypeError, ValueError):
                        pass

            activities.append(Activity(timestamp=timestamp, action=action))

        return activities

    async def get_insight(
        self, days: int = 30, timezone_offset: int | None = None
    ) -> Insight:
        """Return the insight data."""
        if days < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter days, value: {days}, valid range: 1-inf"
            )

        tz: tzinfo = timezone.utc
        if timezone_offset is not None:
            try:
                tz = timezone(timedelta(minutes=int(timezone_offset)))
            except Exception:
                tz = timezone.utc
        elif self.timezone:
            try:
                tz = ZoneInfo(self.timezone)
            except Exception:
                tz = timezone.utc

        now_local = utcnow().astimezone(tz)
        end_date = now_local.date()
        start_date = end_date - timedelta(days=days - 1)

        counts_by_date = {(end_date - timedelta(days=i)): 0 for i in range(days)}

        offset = 0
        page_size = 100
        seen_first_event_id: str | None = None

        while True:
            url = f"robots/{self.serial}/activities?limit={page_size}&offset={offset}"
            page = await self._get(url)
            if not isinstance(page, list) or not page:
                break

            first = page[0] if page else None
            if isinstance(first, dict):
                first_id = cast(str | None, first.get("eventId"))
                if first_id and first_id == seen_first_event_id:
                    break
                if seen_first_event_id is None:
                    seen_first_event_id = first_id

            oldest_local_date: date | None = None
            for item in page:
                timestamp = to_timestamp(cast(str | None, item.get("timestamp")))
                if timestamp is None:
                    continue
                local_date = timestamp.astimezone(tz).date()

                if oldest_local_date is None or local_date < oldest_local_date:
                    oldest_local_date = local_date

                if (
                    item.get("type") == "CYCLE_COMPLETED"
                    and start_date <= local_date <= end_date
                ):
                    counts_by_date[local_date] = counts_by_date.get(local_date, 0) + 1

            if oldest_local_date is not None and oldest_local_date < start_date:
                break
            if len(page) < page_size:
                break

            offset += len(page)

        total_cycles = sum(counts_by_date.values())
        average_cycles = total_cycles / days if days else 0.0

        cycle_history = [(d, counts_by_date.get(d, 0)) for d in counts_by_date.keys()]
        return Insight(total_cycles, average_cycles, cycle_history)

    async def get_camera_session(
        self, *, auto_start: bool = True
    ) -> dict[str, Any] | None:
        """Create or refresh a camera session for this robot, if it has camera metadata.

        The Whisker app uses Ienso for LR5 camera signaling + TURN credentials. This
        call returns a session token and a websocket signaling URL, which can be used
        to negotiate a WebRTC connection.
        """
        if not (device_id := self.camera_device_id):
            return None

        url = f"{IENSO_ENDPOINT}/{IENSO_GENERATE_SESSION_PATH}/{device_id}"
        data = await self._account.session.get(
            url,
            params={"autoStart": "true" if auto_start else "false"},
        )
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

    @classmethod
    def camera_canvas_label(cls, canvas: str) -> str:
        """Return a friendly label for a canvas value."""
        return LR5_CAMERA_CANVAS_LABELS.get(canvas, canvas)

    @classmethod
    def camera_canvas_options(cls) -> dict[str, str]:
        """Return supported canvas options as {canvas_value: friendly_label}."""
        return dict(LR5_CAMERA_CANVAS_LABELS)

    def _camera_settings_headers(self) -> dict[str, str]:
        """Headers required for the Whisker camera settings execute-api endpoints."""
        return {"x-api-key": decode(DEFAULT_ENDPOINT_KEY)}

    @staticmethod
    def _extract_live_view_canvas(
        reported_video_settings: dict[str, Any] | None,
    ) -> str | None:
        """Extract the current live-view canvas from reported video settings."""
        if not reported_video_settings:
            return None

        reported = reported_video_settings.get("reportedSettings")
        if not isinstance(reported, list) or not reported:
            return None
        entry = reported[0]
        if not isinstance(entry, dict):
            return None
        data = entry.get("data")
        if not isinstance(data, dict):
            return None
        streams = data.get("streams")
        if not isinstance(streams, dict):
            return None
        live = streams.get("live-view")
        if not isinstance(live, dict):
            return None
        canvas = live.get("canvas")
        return canvas if isinstance(canvas, str) else None

    async def get_camera_reported_video_settings(
        self, *, camera_device_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch the camera's reported video settings.

        This endpoint is used by the app to determine stream properties and the
        currently selected live-view canvas.
        """
        device_id = camera_device_id or self.camera_device_id
        if not device_id:
            return None
        url = f"{LR5_CAMERA_SETTINGS_ENDPOINT}/{device_id}/reported-settings/videoSettings"
        try:
            data = await self._account.session.get(
                url, headers=self._camera_settings_headers()
            )
        except ClientResponseError:
            return None
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

    async def get_camera_inventory(
        self, *, camera_device_id: str | None = None
    ) -> dict[str, Any] | None:
        """Fetch camera inventory details for a camera device id."""
        device_id = camera_device_id or self.camera_device_id
        if not device_id:
            return None
        url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{device_id}"
        try:
            data = await self._account.session.get(
                url, headers=self._camera_settings_headers()
            )
        except ClientResponseError:
            return None
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

    async def get_camera_videos(
        self, *, camera_device_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]] | None:
        """Fetch recent camera videos (clips metadata + presigned thumbnail URLs)."""
        device_id = camera_device_id or self.camera_device_id
        if not device_id:
            return None
        url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{device_id}/videos"
        params = {"limit": str(limit)} if limit is not None else None
        try:
            data = await self._account.session.get(
                url, headers=self._camera_settings_headers(), params=params
            )
        except ClientResponseError:
            return None
        if not isinstance(data, list):
            return None
        return [cast(dict[str, Any], item) for item in data if isinstance(item, dict)]

    async def get_camera_events(
        self, *, camera_device_id: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]] | None:
        """Fetch recent camera events (AI detections, metadata)."""
        device_id = camera_device_id or self.camera_device_id
        if not device_id:
            return None
        url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{device_id}/events"
        params = {"limit": str(limit)} if limit is not None else None
        try:
            data = await self._account.session.get(
                url, headers=self._camera_settings_headers(), params=params
            )
        except ClientResponseError:
            return None
        if not isinstance(data, list):
            return None
        return [cast(dict[str, Any], item) for item in data if isinstance(item, dict)]

    async def get_camera_live_canvas(
        self, *, camera_device_id: str | None = None
    ) -> str | None:
        """Return the current live-view canvas (e.g. sensor_0_1080p)."""
        reported = await self.get_camera_reported_video_settings(
            camera_device_id=camera_device_id
        )
        return self._extract_live_view_canvas(reported)

    async def set_camera_live_canvas(
        self,
        canvas: str,
        *,
        camera_device_id: str | None = None,
        wait_for_reported: bool = True,
        timeout_seconds: float = 15.0,
    ) -> bool:
        """Select the active live-view canvas.

        The Whisker app's "switch camera" button updates the camera setting:
          streams.live-view.canvas = <canvas>

        Warning:
        - This setting is global to the camera device. Multiple concurrent live
          viewers may affect each other.

        """
        device_id = camera_device_id or self.camera_device_id
        if not device_id:
            return False

        payload = {
            "timestamp": utcnow().isoformat().replace("+00:00", "Z"),
            "streams": {"live-view": {"canvas": canvas}},
        }
        url = (
            f"{LR5_CAMERA_SETTINGS_ENDPOINT}/{device_id}/desired-settings/videoSettings"
        )
        try:
            await self._account.session.patch(
                url, json=payload, headers=self._camera_settings_headers()
            )
        except ClientResponseError:
            return False

        if not wait_for_reported:
            return True

        deadline = utcnow() + timedelta(seconds=timeout_seconds)
        while utcnow() < deadline:
            current = await self.get_camera_live_canvas(camera_device_id=device_id)
            if current == canvas:
                return True
            await asyncio.sleep(0.5)
        return False

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
            if force_check:
                await self.refresh()

            versions = self._state.get("firmwareVersions")
            if not isinstance(versions, dict):
                return None

            current: dict[str, str] = {}
            for key, value in versions.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                version = value.get("value")
                if isinstance(version, str):
                    current[key] = version

            for key in ("espUpdateStatus", "stmUpdateStatus"):
                value = self._state.get(key)
                if isinstance(value, str) and value:
                    current[key] = value

            self._firmware_details = {
                "isFirmwareUpdating": self._state.get("isFirmwareUpdating") is True,
                "currentFirmware": current,
            }
            self._firmware_details_requested = utcnow()

        return self._firmware_details

    async def get_latest_firmware(self, force_check: bool = False) -> str | None:
        """Get the latest firmware available."""
        progress = await self._get_otaupdate_progress(force_check=force_check)
        latest = progress.get("latestFirmware") if isinstance(progress, dict) else None
        return latest if isinstance(latest, str) and latest else None

    async def has_firmware_update(self, force_check: bool = False) -> bool:
        """Check if a firmware update is available."""
        progress = await self._get_otaupdate_progress(force_check=force_check)
        status = progress.get("status") if isinstance(progress, dict) else None
        if isinstance(status, str):
            return status in {"AVAILABLE", "PENDING", "IN_PROGRESS"}

        # Fallback: we can't reliably compare latest vs current firmware for LR5 yet,
        # but we can at least report when the robot is already updating.
        return self._state.get("isFirmwareUpdating") is True

    async def update_firmware(self) -> bool:
        """Trigger a firmware update."""
        self._otaupdate_progress = None
        self._otaupdate_progress_requested = None

        data = await self._account.session.post(
            LR5_OTAUPDATE_ENDPOINT,
            json={
                "query": """
                    mutation TriggerRobotUpdateBySerial($serialNumber: String!) {
                        triggerRobotUpdateBySerial(serialNumber: $serialNumber) {
                            success
                            serialNumber
                            message
                        }
                    }
                """,
                "variables": {"serialNumber": self.serial},
            },
        )
        payload = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        response = payload.get("data", {}).get("triggerRobotUpdateBySerial", {})
        return bool(response.get("success", False))

    async def _get_otaupdate_progress(
        self, *, force_check: bool = False
    ) -> dict[str, Any] | None:
        if (
            force_check
            or (requested := self._otaupdate_progress_requested) is None
            or requested + timedelta(minutes=15) < utcnow()
        ):
            progress = await self._fetch_otaupdate_progress()
            self._otaupdate_progress = progress
            self._otaupdate_progress_requested = utcnow()
        return self._otaupdate_progress

    async def _fetch_otaupdate_progress(self) -> dict[str, Any] | None:
        data = await self._account.session.post(
            LR5_OTAUPDATE_ENDPOINT,
            json={
                "query": """
                    query CheckUpdateStatusBySerial($serialNumber: String!) {
                        checkUpdateStatusBySerial(serialNumber: $serialNumber) {
                            serialNumber
                            status
                            progress
                            currentFirmware
                            latestFirmware
                            message
                        }
                    }
                """,
                "variables": {"serialNumber": self.serial},
            },
        )
        payload = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        response = payload.get("data", {}).get("checkUpdateStatusBySerial")
        if isinstance(response, dict):
            return response

        # Fallback: some devices (currently LR5) return marshal errors for the
        # serial-specific query, but may still be visible via user-scoped status.
        if not (user_id := self._account.user_id):
            return None

        data = await self._account.session.post(
            LR5_OTAUPDATE_ENDPOINT,
            json={
                "query": """
                    query CheckUpdateStatusByUser($userId: String!) {
                        checkUpdateStatusByUser(userId: $userId) {
                            serialNumber
                            status
                            progress
                            currentFirmware
                            latestFirmware
                            message
                        }
                    }
                """,
                "variables": {"userId": user_id},
            },
        )
        payload = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        items = payload.get("data", {}).get("checkUpdateStatusByUser")
        if not isinstance(items, list):
            return None

        for item in items:
            if isinstance(item, dict) and item.get("serialNumber") == self.serial:
                return item

        return None
