"""Litter-Robot 5."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

from aiohttp import ClientConnectionError, ClientConnectorError, ClientResponseError

from ..activity import Activity, Insight
from ..enums import (
    BrightnessLevel,
    GlobeMotorFaultStatus,
    HopperStatus,
    LitterBoxStatus,
    LitterLevelState,
    LitterRobot5Command,
    NightLightMode,
)
from ..event import EVENT_UPDATE
from ..exceptions import (
    CameraNotAvailableException,
    InvalidCommandException,
    LitterRobotException,
)
from ..transport import PollingTransport
from ..utils import calculate_litter_level, to_enum, to_timestamp, urljoin, utcnow
from .litterrobot import LitterRobot

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

LR5_ENDPOINT = "https://ub.prod.iothings.site"
# Maps for state.state field (StPascalCase format from real API)
LR5_STATE_MAP = {
    "StRobotBonnet": LitterBoxStatus.BONNET_REMOVED,
    "StRobotCatDetect": LitterBoxStatus.CAT_DETECTED,
    "StRobotCatDetectDelay": LitterBoxStatus.CAT_SENSOR_TIMING,
    "StRobotClean": LitterBoxStatus.CLEAN_CYCLE,
    "StRobotEmpty": LitterBoxStatus.EMPTY_CYCLE,
    "StRobotFindDump": LitterBoxStatus.CLEAN_CYCLE,
    "StRobotIdle": LitterBoxStatus.READY,
    "StRobotPowerDown": LitterBoxStatus.POWER_DOWN,
    "StRobotPowerOff": LitterBoxStatus.OFF,
    "StRobotPowerUp": LitterBoxStatus.POWER_UP,
}
# Legacy UPPER_SNAKE_CASE format (LR4-style, kept for backwards compatibility)
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
# Maps for state.displayCode field (DcPascalCase from real API)
DISPLAY_CODE_STATUS_MAP = {
    "DcCatDetect": LitterBoxStatus.CAT_DETECTED,
    "DcDfiFull": LitterBoxStatus.DRAWER_FULL,
    "DcModeCycle": LitterBoxStatus.CLEAN_CYCLE,
    "DcModeIdle": LitterBoxStatus.READY,
    "DcxLampTest": LitterBoxStatus.POWER_UP,
    "DcxSuspend": LitterBoxStatus.POWER_DOWN,
    # Legacy UPPER_SNAKE_CASE (LR4 format)
    "DC_CAT_DETECT": LitterBoxStatus.CAT_DETECTED,
}
# Maps for statusIndicator.type field (most reliable status source)
STATUS_INDICATOR_MAP = {
    "READY": LitterBoxStatus.READY,
    "DRAWER_FULL": LitterBoxStatus.DRAWER_FULL,
    "CYCLING": LitterBoxStatus.CLEAN_CYCLE,
    "LITTER_LOW": LitterBoxStatus.READY,
    "CAT_DETECTED": LitterBoxStatus.CAT_DETECTED,
    "BONNET_REMOVED": LitterBoxStatus.BONNET_REMOVED,
    "OFF": LitterBoxStatus.OFF,
    "OFFLINE": LitterBoxStatus.OFFLINE,
}
# Maps for state.cycleState field
CYCLE_STATE_STATUS_MAP = {
    # LR5 format (StPascalCase)
    "StCatDetect": LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
    "StPause": LitterBoxStatus.PAUSED,
    # Legacy UPPER_SNAKE_CASE (LR4 format)
    "CYCLE_STATE_CAT_DETECT": LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
    "CYCLE_STATE_PAUSE": LitterBoxStatus.PAUSED,
}

LITTER_LEVEL_EMPTY = 500

MODEL_TYPE_STANDARD = "LR5"
MODEL_TYPE_PRO = "LR5_PRO"
MODEL_TYPE_MAP = {
    MODEL_TYPE_STANDARD: "Litter-Robot 5",
    MODEL_TYPE_PRO: "Litter-Robot 5 Pro",
}

DEFAULT_POLLING_INTERVAL = 30.0


class LitterRobot5(LitterRobot):
    """Data and methods for interacting with a Litter-Robot 5 automatic, self-cleaning litter box."""

    VALID_WAIT_TIMES = [3, 7, 15, 25, 30]

    _data_cycle_capacity = "DFINumberOfCycles"
    _data_cycle_count = "odometerCleanCycles"
    _data_drawer_full_cycles = "DFIFullCounter"
    _data_id = "serial"
    _data_name = "name"
    _data_power_status = "powerStatus"
    _data_serial = "serial"
    _data_setup_date = "setupDateTime"

    _command_clean = LitterRobot5Command.CLEAN_CYCLE
    _command_power_off = LitterRobot5Command.POWER_OFF
    _command_power_on = LitterRobot5Command.POWER_ON

    _litter_level = LITTER_LEVEL_EMPTY
    _litter_level_exp: datetime | None = None

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Litter-Robot 5."""
        super().__init__(data, account)
        self._path = LR5_ENDPOINT
        self._camera_audio_enabled: bool | None = None

    @property
    def is_pro(self) -> bool:
        """Return `True` if this is a Litter-Robot 5 Pro."""
        return self._data.get("type") == MODEL_TYPE_PRO

    @property
    def model(self) -> str:
        """Return the robot model."""
        model_type = self._data.get("type") or "Unknown"
        return MODEL_TYPE_MAP.get(model_type, model_type)

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
    def setup_date(self) -> datetime | None:
        """Return the datetime the robot was onboarded, if any."""
        return to_timestamp(
            self._state.get(self._data_setup_date)
            or self._data.get(self._data_setup_date)
        )

    @property
    def last_seen(self) -> datetime | None:
        """Return the datetime the Litter-Robot last reported, if any."""
        return to_timestamp(self._state.get("lastSeen") or self._data.get("lastSeen"))

    @property
    def timezone(self) -> str:
        """Return the timezone."""
        return cast(str, self._data.get("timezone"))

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return number of minutes after a cat uses the Litter-Robot to begin automatic clean."""
        return cast(int, self._litter_robot_settings.get("cycleDelay", 7))

    @property
    def camera_metadata(self) -> dict[str, str] | None:
        """Return the camera metadata (Pro only)."""
        cam = self._data.get("cameraMetadata")
        return cam if isinstance(cam, dict) else None

    @property
    def cat_detect(self) -> str:
        """Return the cat detection sensor state."""
        return cast(str, self._state.get("catDetect", ""))

    @property
    def cycle_count(self) -> int:
        """Return the cycle count since the last time the waste drawer was reset."""
        return int(self._state.get(self._data_cycle_count, 0))

    @property
    def cycle_type(self) -> str:
        """Return the current cycle type."""
        return cast(str, self._state.get("cycleType", ""))

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
        parts = []
        if wifi is not None:
            parts.append(f"ESP: {wifi}")
        if mcu is not None:
            parts.append(f"MCU: {mcu}")
        # Pro-specific firmware versions
        for key, label in [
            ("cameraVersion", "CAM"),
            ("edgeVersion", "EDGE"),
            ("aiVersion", "AI"),
        ]:
            ver = fw.get(key)
            if isinstance(ver, dict):
                ver = ver.get("value")
            if ver:
                parts.append(f"{label}: {ver}")
        return " / ".join(parts)

    @property
    def extended_scale_activity(self) -> bool:
        """Return `True` if extended scale activity is detected."""
        return self._state.get("extendedScaleActivity") is True

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
    def globe_motor_fault_status(self) -> GlobeMotorFaultStatus:
        """Return the globe motor fault status."""
        value = self._state.get("globeMotorFaultStatus")
        return GlobeMotorFaultStatus.from_raw(value)

    @property
    def globe_motor_retract_fault_status(self) -> GlobeMotorFaultStatus:
        """Return the globe motor retract fault status."""
        value = self._state.get("globeMotorRetractFaultStatus")
        return GlobeMotorFaultStatus.from_raw(value)

    @property
    def hopper_fault(self) -> str | None:
        """Return the hopper fault status, if any."""
        return self._state.get("hopperFault")

    @property
    def hopper_status(self) -> HopperStatus | None:
        """Return the hopper status."""
        return to_enum(self._state.get("hopperStatus"), HopperStatus)

    @property
    def is_bonnet_removed(self) -> bool:
        """Return `True` if the bonnet is removed."""
        return self._state.get("isBonnetRemoved") is True

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""
        return cast(int, self._state.get("dfiFullCounter", 0)) > 0

    @property
    def is_drawer_removed(self) -> bool:
        """Return `True` if the waste drawer is removed."""
        return self._state.get("isDrawerRemoved") is True

    @property
    def is_firmware_updating(self) -> bool:
        """Return `True` if a firmware update is in progress."""
        return self._state.get("isFirmwareUpdating") is True

    @property
    def is_gas_sensor_fault_detected(self) -> bool:
        """Return `True` if a gas sensor fault is detected."""
        return self._state.get("isGasSensorFaultDetected") is True

    @property
    def is_hopper_removed(self) -> bool:
        """Return `True` if the hopper is removed/disabled."""
        return self._state.get("isHopperInstalled") is False

    @property
    def is_laser_dirty(self) -> bool:
        """Return `True` if the laser sensor needs cleaning."""
        return self._state.get("isLaserDirty") is True

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return self._state.get("isOnline") is True

    @property
    def is_night_light_on(self) -> bool:
        """Return `True` if the night light LED is currently on."""
        return self._state.get("isNightLightOn") is True

    @property
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently 'sleeping'."""
        return self._state.get("isSleeping") is True

    @property
    def is_smart_weight_enabled(self) -> bool:
        """Return `True` if smart weight is enabled."""
        return self._litter_robot_settings.get("isSmartWeightEnabled") is True

    @property
    def is_usb_fault_detected(self) -> bool:
        """Return `True` if a USB fault is detected."""
        return self._state.get("isUsbFaultDetected") is True

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
        is_cleaning = (
            self._state.get("cycleType") or self._state.get("robotCycleState") or ""
        ).upper().find("CLEAN") != -1
        new_level = int(
            self._state.get(
                "globeLitterLevel", self._state.get("litterLevel", LITTER_LEVEL_EMPTY)
            )
        )
        self._litter_level, self._litter_level_exp, percent = calculate_litter_level(
            is_cleaning, new_level, self._litter_level, self._litter_level_exp
        )
        return percent

    @property
    def litter_level_state(self) -> LitterLevelState | None:
        """Return the litter level state."""
        return to_enum(self._state.get("globeLitterLevelIndicator"), LitterLevelState)

    @property
    def last_reset_odometer_clean_cycles(self) -> int:
        """Return the clean cycle count at the last waste drawer reset."""
        return int(self._state.get("lastResetOdometerCleanCycles", 0))

    @property
    def next_filter_replacement_date(self) -> datetime | None:
        """Return the next filter replacement date."""
        return to_timestamp(self._data.get("nextFilterReplacementDate"))

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
        return to_enum(self._night_light_settings.get("mode"), NightLightMode)

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        mode = self._night_light_settings.get("mode")
        return str(mode).lower() != "off" if mode else False

    @property
    def panel_brightness(self) -> BrightnessLevel | None:
        """Return the panel brightness."""
        # LR5 API uses displayIntensity strings ("Low", "Medium", "High")
        display_intensity = self._panel_settings.get("displayIntensity")
        if isinstance(display_intensity, str):
            intensity_map = {
                "low": BrightnessLevel.LOW,
                "medium": BrightnessLevel.MEDIUM,
                "high": BrightnessLevel.HIGH,
            }
            if (level := intensity_map.get(display_intensity.lower())) is not None:
                return level
        # Fall back to numeric brightness for backwards compatibility
        brightness = self._panel_settings.get("brightness")
        if brightness in list(BrightnessLevel):
            return BrightnessLevel(brightness)
        return None

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if keypad lock is enabled."""
        return cast(
            bool, self._panel_settings.get(LitterRobot5Command.KEYPAD_LOCKED, False)
        )

    @property
    def pet_weight(self) -> float:
        """Return the last recorded pet weight in pounds (lbs).

        The API reports weight as pounds * 100 (integer format).
        This property converts the raw value to pounds.
        """
        return (self._state.get("weightSensor") or 0.0) / 100

    @property
    def power_status(self) -> str:
        """Return the power status."""
        return cast(str, self._state.get(self._data_power_status, "On"))

    @property
    def privacy_mode(self) -> str:
        """Return the privacy mode setting."""
        return cast(str, self._state.get("privacyMode", "Normal"))

    @property
    def scoops_saved_count(self) -> int:
        """Return the scoops saved count."""
        return cast(int, self._state.get("scoopsSaved", 0))

    @property
    def stm_update_status(self) -> str:
        """Return the STM (MCU) firmware update status."""
        return cast(str, self._state.get("stmUpdateStatus", "UNKNOWN"))

    @property
    def _sound_settings(self) -> dict[str, Any]:
        """Return the sound settings dict."""
        return self._get_data_dict("soundSettings")

    @property
    def sound_volume(self) -> int:
        """Return the sound volume (0-100)."""
        return int(self._sound_settings.get("volume", 0))

    @property
    def camera_audio_enabled(self) -> bool:
        """Return `True` if camera audio is enabled (Pro only).

        Uses locally cached state from ``set_camera_audio`` when available,
        since the robot API's ``soundSettings.cameraAudioEnabled`` field does
        not reflect changes made via the camera settings API.
        """
        if self._camera_audio_enabled is not None:
            return self._camera_audio_enabled
        return self._sound_settings.get("cameraAudioEnabled") is True

    @property
    def wifi_rssi(self) -> int:
        """Return the WiFi signal strength (RSSI)."""
        return int(self._state.get("wifiRssi", 0))

    @property
    def odometer_empty_cycles(self) -> int:
        """Return the total empty cycle count."""
        return int(self._state.get("odometerEmptyCycles", 0))

    @property
    def odometer_filter_cycles(self) -> int:
        """Return the number of cycles since last filter replacement."""
        return int(self._state.get("odometerFilterCycles", 0))

    @property
    def odometer_power_cycles(self) -> int:
        """Return the total power cycle count."""
        return int(self._state.get("odometerPowerCycles", 0))

    @property
    def optimal_litter_level(self) -> int:
        """Return the optimal litter level."""
        return int(self._state.get("optimalLitterLevel", 0))

    @property
    def pinch_status(self) -> str:
        """Return the pinch detection status."""
        return cast(str, self._state.get("pinchStatus", ""))

    @property
    def sleep_mode_enabled(self) -> bool:
        """Return True if sleep mode is enabled for any day."""
        schedules = self._data.get("sleepSchedules")
        iterable: list[dict[str, Any]]
        if isinstance(schedules, dict):
            iterable = list(schedules.values())
        elif isinstance(schedules, list):
            iterable = schedules
        else:
            return False
        return any(day.get("isEnabled", False) for day in iterable)

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

        Priority:
         1. offline check
         2. cycleState (pause/cat detect interrupts)
         3. state field (StRobotIdle, StRobotClean, etc.)
         4. displayCode (DcModeIdle, DcModeCycle, DcDfiFull, etc.)
         5. statusIndicator.type (READY, DRAWER_FULL, CYCLING, etc.)
         6. status string (legacy "Ready" format)
         7. fall back to UNKNOWN
        """
        if not self.is_online:
            return LitterBoxStatus.OFFLINE

        # 1. Cycle state interrupts (cat detect, pause) take priority
        cycle_state = self._state.get("cycleState") or self._state.get(
            "robotCycleState"
        )
        if cycle_state and (mapped := CYCLE_STATE_STATUS_MAP.get(cycle_state)):
            return mapped

        # 2. Robot state field (StPascalCase from real API)
        robot_state = self._state.get("state")
        if robot_state and (mapped := LR5_STATE_MAP.get(robot_state)):
            if mapped == LitterBoxStatus.READY and self.is_waste_drawer_full:
                return LitterBoxStatus.DRAWER_FULL
            return mapped

        # 3. Display code (DcPascalCase from real API)
        display_code = self._state.get("displayCode")
        if display_code and (mapped := DISPLAY_CODE_STATUS_MAP.get(display_code)):
            if mapped == LitterBoxStatus.READY and self.is_waste_drawer_full:
                return LitterBoxStatus.DRAWER_FULL
            return mapped

        # 4. Status indicator (most readable but used as fallback)
        indicator = self._state.get("statusIndicator")
        if isinstance(indicator, dict):
            indicator_type = indicator.get("type")
            if indicator_type and (mapped := STATUS_INDICATOR_MAP.get(indicator_type)):
                if mapped == LitterBoxStatus.READY and self.is_waste_drawer_full:
                    return LitterBoxStatus.DRAWER_FULL
                return mapped

        # 5. Legacy status string (e.g., "Ready", "ROBOT_IDLE")
        raw_status = self._state.get("status") or self._state.get("robotStatus")
        if isinstance(raw_status, str):
            # Try legacy LR5/LR4 maps
            if mapped := LR5_STATUS_MAP.get(raw_status):
                if mapped == LitterBoxStatus.READY and self.is_waste_drawer_full:
                    return LitterBoxStatus.DRAWER_FULL
                return mapped
            # Normalize and try common patterns
            normalized = raw_status.strip().upper()
            if normalized in ("READY", "IDLE"):
                status = LitterBoxStatus.READY
            elif "CLEAN" in normalized or "DUMP" in normalized:
                status = LitterBoxStatus.CLEAN_CYCLE
            elif "CAT" in normalized:
                status = LitterBoxStatus.CAT_DETECTED
            elif "POWER" in normalized and "UP" in normalized:
                status = LitterBoxStatus.POWER_UP
            elif "POWER" in normalized:
                status = LitterBoxStatus.POWER_DOWN
            elif "OFF" in normalized:
                status = LitterBoxStatus.OFF
            else:
                return LitterBoxStatus.UNKNOWN
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
            # If now is within this sleep window, use it
            if start <= now <= end:
                break

        self._sleep_mode_start_time = start
        self._sleep_mode_end_time = end

    async def _dispatch_command(self, command: str, **kwargs: Any) -> bool:
        """Send a command to the Litter-Robot.

        For LR5, operational commands (clean, power, reset) use POST
        /robots/{serial}/commands. Settings changes use PATCH /robots/{serial}.
        """
        # Operational commands go via POST /commands endpoint
        if command in (
            LitterRobot5Command.CLEAN_CYCLE,
            LitterRobot5Command.POWER_ON,
            LitterRobot5Command.POWER_OFF,
            LitterRobot5Command.REMOTE_RESET,
            LitterRobot5Command.FACTORY_RESET,
            LitterRobot5Command.RESET_WASTE_LEVEL,
            LitterRobot5Command.CHANGE_FILTER,
            LitterRobot5Command.ONBOARD_PTAG_ON,
            LitterRobot5Command.ONBOARD_PTAG_OFF,
            LitterRobot5Command.PRIVACY_MODE_ON,
            LitterRobot5Command.PRIVACY_MODE_OFF,
        ):
            return await self._send_command(command)
        # Settings changes use PATCH
        try:
            await self._patch(
                f"robots/{self.serial}",
                json={command: kwargs.get("value")},
            )
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False
        # Update local state to reflect the change immediately
        value = kwargs.get("value")
        if isinstance(value, dict):
            existing = self._data.get(command)
            if isinstance(existing, dict):
                value = {**existing, **value}
        self._update_data({command: value}, partial=True)
        return True

    async def _send_command(self, command: str) -> bool:
        """Send an operational command via POST /robots/{serial}/commands."""
        try:
            await self._account.session.request(
                "POST",
                f"{LR5_ENDPOINT}/robots/{self.serial}/commands",
                json={"type": command},
            )
            return True
        except (ClientResponseError, ClientConnectorError, ClientConnectionError) as ex:
            _LOGGER.error("Command %s failed: %s", command, ex)
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = await self._get(f"robots/{self.serial}")
        if isinstance(data, dict):
            self._update_data(data)

    async def reset(self) -> bool:
        """Perform a remote reset on the Litter-Robot.

        Clears errors and may trigger a cycle.
        """
        return await self._dispatch_command(LitterRobot5Command.REMOTE_RESET)

    async def reset_waste_drawer(self) -> bool:
        """Reset the waste drawer level indicator."""
        return await self._dispatch_command(LitterRobot5Command.RESET_WASTE_LEVEL)

    async def change_filter(self) -> bool:
        """Reset the filter replacement counter."""
        return await self._dispatch_command(LitterRobot5Command.CHANGE_FILTER)

    async def set_name(self, name: str) -> bool:
        """Set the name."""
        await self._patch(f"robots/{self.serial}", json={"name": name})
        self._update_data({"name": name}, partial=True)
        return self.name == name

    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light on or off."""
        mode = (NightLightMode.ON if value else NightLightMode.OFF).value.capitalize()
        return await self._dispatch_command(
            LitterRobot5Command.NIGHT_LIGHT_SETTINGS,
            value={"mode": mode},
        )

    async def set_night_light_brightness(self, brightness: int) -> bool:
        """Set the night light brightness (0-100)."""
        return await self._dispatch_command(
            LitterRobot5Command.NIGHT_LIGHT_SETTINGS,
            value={"brightness": brightness},
        )

    async def set_night_light_mode(self, mode: NightLightMode) -> bool:
        """Set the night light mode (On, Off, Auto/Ambient)."""
        return await self._dispatch_command(
            LitterRobot5Command.NIGHT_LIGHT_SETTINGS,
            value={"mode": mode.value.capitalize()},
        )

    async def set_panel_brightness(self, brightness: BrightnessLevel) -> bool:
        """Set the panel brightness."""
        level_to_intensity = {
            BrightnessLevel.LOW: "Low",
            BrightnessLevel.MEDIUM: "Medium",
            BrightnessLevel.HIGH: "High",
        }
        if brightness not in level_to_intensity:
            raise InvalidCommandException(
                f"Invalid brightness level: {brightness!r}. Must be one of: {list(level_to_intensity)}"
            )
        return await self._dispatch_command(
            LitterRobot5Command.PANEL_SETTINGS,
            value={"displayIntensity": level_to_intensity[brightness]},
        )

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        if await self._dispatch_command(
            LitterRobot5Command.PANEL_SETTINGS,
            value={LitterRobot5Command.KEYPAD_LOCKED: value},
        ):
            data = deepcopy(self._data)
            data.setdefault(LitterRobot5Command.PANEL_SETTINGS, {})[
                LitterRobot5Command.KEYPAD_LOCKED
            ] = value
            self._update_data(data)
        return self.panel_lock_enabled == value

    async def set_privacy_mode(self, value: bool) -> bool:
        """Turn privacy mode on or off."""
        command = (
            LitterRobot5Command.PRIVACY_MODE_ON
            if value
            else LitterRobot5Command.PRIVACY_MODE_OFF
        )
        return await self._dispatch_command(command)

    async def set_sleep_mode(
        self,
        value: bool,
        sleep_time: int | time | None = None,
        *,
        wake_time: int | None = None,
        day_of_week: int | None = None,
    ) -> bool:
        """Set the sleep mode schedule.

        Args:
            value: Whether to enable or disable sleep mode.
            sleep_time: Minutes from midnight for sleep start (e.g. 1380 = 11PM).
            wake_time: Minutes from midnight for wake (e.g. 420 = 7AM).
            day_of_week: Specific day to update (0=Monday, 6=Sunday).
                If None, updates all days.

        """
        schedules = deepcopy(self._data.get("sleepSchedules", []))
        # Normalize dict format (legacy: {dayName: {...}}) to list format
        if isinstance(schedules, dict):
            schedules = list(schedules.values())
        if not schedules:
            schedules = [
                {"dayOfWeek": d, "isEnabled": False, "sleepTime": 0, "wakeTime": 0}
                for d in range(7)
            ]
        for schedule in schedules:
            if day_of_week is not None and schedule.get("dayOfWeek") != day_of_week:
                continue
            schedule["isEnabled"] = value
            if sleep_time is not None:
                schedule["sleepTime"] = (
                    sleep_time.hour * 60 + sleep_time.minute
                    if isinstance(sleep_time, time)
                    else sleep_time
                )
            if wake_time is not None:
                schedule["wakeTime"] = wake_time
        try:
            await self._patch(
                f"robots/{self.serial}", json={"sleepSchedules": schedules}
            )
            self._update_data({"sleepSchedules": schedules}, partial=True)
            return True
        except Exception as ex:
            _LOGGER.error("Failed to set sleep mode: %s", ex)
            return False

    async def set_volume(self, volume: int) -> bool:
        """Set the sound volume (0-100)."""
        if not 0 <= volume <= 100:
            raise InvalidCommandException(f"Invalid volume {volume!r}: must be 0-100.")
        return await self._dispatch_command(
            LitterRobot5Command.SOUND_SETTINGS,
            value={"volume": volume},
        )

    async def set_camera_audio(self, value: bool) -> bool:
        """Enable or disable camera audio (Pro only)."""
        if not self.has_camera:
            return False
        client = self.get_camera_client()
        if await client.set_audio_enabled(value):
            self._camera_audio_enabled = value
            self.emit(EVENT_UPDATE)
            return True
        return False

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
            data.setdefault(LitterRobot5Command.LITTER_ROBOT_SETTINGS, {})[
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
        try:
            activities = await self.get_activities(limit=limit)
        except Exception as ex:
            raise LitterRobotException(
                "Activity history could not be retrieved."
            ) from ex
        if not isinstance(activities, list):
            raise LitterRobotException("Activity history could not be retrieved.")
        return [
            Activity(timestamp, activity.get("type", ""))
            for activity in activities
            if (timestamp := to_timestamp(activity.get("timestamp"))) is not None
        ]

    async def get_activities(
        self,
        limit: int | None = None,
        offset: int | None = None,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return activities from the REST endpoint.

        Returns richer data than get_activity_history(), including PET_VISIT
        events with waste type, pet IDs, duration, and camera event IDs.

        Args:
            limit: Maximum number of activities to return.
            offset: Number of activities to skip.
            activity_type: Filter by type (e.g. PET_VISIT, CYCLE_COMPLETED,
                CAT_DETECT, OFFLINE, CYCLE_INTERRUPTED, LITTER_LOW).

        """
        params: dict[str, str] = {}
        if limit is not None:
            params["limit"] = str(limit)
        if offset is not None:
            params["offset"] = str(offset)
        if activity_type is not None:
            params["type"] = activity_type
        url = f"{LR5_ENDPOINT}/robots/{self.serial}/activities"
        data = await self._account.session.request("GET", url, params=params)
        return cast(list[dict[str, Any]], data) if isinstance(data, list) else []

    async def reassign_pet_visit(
        self,
        event_id: str,
        from_pet_id: str | None = None,
        to_pet_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Reassign or unassign a pet visit activity.

        Args:
            event_id: The eventId of the activity to modify.
            from_pet_id: Pet to remove from the visit (for reassign/unassign).
            to_pet_id: Pet to assign the visit to (for reassign). Omit for unassign.

        Returns:
            The updated activity dict on success, or None on failure.

        """
        if not from_pet_id and not to_pet_id:
            raise ValueError(
                "At least one of from_pet_id or to_pet_id must be provided"
            )
        body: dict[str, str] = {"eventId": event_id}
        if from_pet_id:
            body["fromPetId"] = from_pet_id
        if to_pet_id:
            body["toPetId"] = to_pet_id
        url = f"{LR5_ENDPOINT}/robots/{self.serial}/activities"
        try:
            data = await self._account.session.request("PATCH", url, json=body)
            return cast(dict[str, Any], data) if isinstance(data, dict) else None
        except (ClientResponseError, ClientConnectorError, ClientConnectionError) as ex:
            _LOGGER.error("Reassign pet visit failed: %s", ex)
            return None

    async def get_insight(
        self, days: int = 30, timezone_offset: int | None = None
    ) -> Insight:
        """Return the insight data.

        Note: The LR5 REST API does not provide an insights endpoint.
        Raises NotImplementedError.
        """
        raise NotImplementedError(
            "Insight data is not available via the LR5 REST API. "
            "Use get_activities() to retrieve activity history instead."
        )

    async def get_firmware_details(
        self, force_check: bool = False
    ) -> dict[str, bool | dict[str, str]] | None:
        """Get the firmware details.

        Note: The LR5 REST API does not provide a firmware comparison endpoint.
        Returns firmware version info from the robot state instead.
        """
        fw = self._state.get("firmwareVersions", {})
        result: dict[str, Any] = {"latestFirmware": {}}
        for key, fw_key, fallback_key in [
            ("espFirmwareVersion", "wifiVersion", "espFirmwareVersion"),
            ("mcuFirmwareVersion", "mcuVersion", "stmFirmwareVersion"),
        ]:
            ver = fw.get(fw_key)
            if isinstance(ver, dict):
                ver = ver.get("value")
            if ver is None:
                ver = self._state.get(fallback_key)
            result["latestFirmware"][key] = ver
        return result

    async def get_latest_firmware(self, force_check: bool = False) -> str | None:
        """Get the latest firmware available."""
        if (firmware := await self.get_firmware_details(force_check)) is None:
            return None

        latest_firmware = cast(dict[str, str], firmware.get("latestFirmware", {}))
        parts = []
        if esp := latest_firmware.get("espFirmwareVersion"):
            parts.append(f"ESP: {esp}")
        if mcu := latest_firmware.get("mcuFirmwareVersion"):
            parts.append(f"MCU: {mcu}")
        return " / ".join(parts) if parts else None

    async def has_firmware_update(self, force_check: bool = False) -> bool:
        """Check if a firmware update is available.

        Note: The LR5 REST API does not provide a firmware comparison endpoint.
        Always returns False since we cannot determine update availability.
        """
        return False

    async def update_firmware(self) -> bool:
        """Trigger a firmware update.

        Note: The LR5 REST API does not provide a firmware update trigger endpoint.
        Raises NotImplementedError.
        """
        raise NotImplementedError(
            "Firmware updates cannot be triggered via the LR5 REST API."
        )

    # -- Camera convenience methods ----------------------------------------

    @property
    def has_camera(self) -> bool:
        """Return `True` if this robot has camera metadata (Pro model)."""
        cam = self.camera_metadata
        return isinstance(cam, dict) and bool(cam.get("deviceId"))

    def get_camera_client(self) -> Any:
        """Return a ``CameraClient`` for this robot's camera.

        Raises:
            CameraNotAvailableException: If the robot has no camera.

        """
        from ..camera import CameraClient
        from ..utils import decode

        cam = self.camera_metadata
        if not cam or not cam.get("deviceId"):
            raise CameraNotAvailableException(
                f"Robot {self.serial} does not have a camera"
            )

        from .litterrobot3 import DEFAULT_ENDPOINT_KEY

        return CameraClient(
            session=self._account.session,
            device_id=cam["deviceId"],
            api_key=decode(DEFAULT_ENDPOINT_KEY),
        )

    async def get_camera_session(self) -> Any:
        """Generate a camera streaming session.

        Returns:
            A ``CameraSession`` with TURN credentials and signaling URL.

        Raises:
            CameraNotAvailableException: If the robot has no camera.

        """
        client = self.get_camera_client()
        return await client.generate_session()

    async def get_camera_videos(
        self, date: str | None = None, limit: int | None = None
    ) -> list[Any]:
        """Fetch recorded camera video clips.

        Args:
            date: Optional date (YYYY-MM-DD) filter.
            limit: Optional max results.

        """
        client = self.get_camera_client()
        return list(await client.get_videos(date=date, limit=limit))

    async def get_camera_video_settings(self) -> dict[str, Any] | None:
        """Fetch the camera's reported video settings."""
        client = self.get_camera_client()
        result: dict[str, Any] | None = await client.get_video_settings()
        return result

    async def set_camera_view(self, view: str) -> bool:
        """Switch the camera live-view canvas.

        Args:
            view: ``"front"`` or ``"globe"``.

        Raises:
            InvalidCommandException: If the view is not recognized.
            CameraNotAvailableException: If the robot has no camera.

        """
        from ..camera import CAMERA_CANVAS_FRONT, CAMERA_CANVAS_GLOBE

        view_map = {
            "front": CAMERA_CANVAS_FRONT,
            "globe": CAMERA_CANVAS_GLOBE,
        }
        canvas = view_map.get(view.lower())
        if canvas is None:
            raise InvalidCommandException(
                f"Invalid camera view {view!r}. Must be 'front' or 'globe'."
            )
        client = self.get_camera_client()
        result: bool = await client.set_camera_canvas(canvas)
        return result

    def create_camera_stream(self, **kwargs: Any) -> Any:
        """Create a ``CameraStream`` for live WebRTC streaming.

        Requires the ``aiortc`` optional dependency.

        Raises:
            CameraNotAvailableException: If the robot has no camera.
            ImportError: If ``aiortc`` is not installed.

        """
        from ..camera import CameraStream

        client = self.get_camera_client()
        return CameraStream(client, **kwargs)

    # -- Class methods / transport -----------------------------------------

    @classmethod
    async def fetch_for_account(cls, account: Account) -> list[dict[str, object]]:
        """Fetch robot data for account."""
        result = await account.session.get(urljoin(LR5_ENDPOINT, "robots"))

        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]

        return []

    def _build_transport(self) -> PollingTransport:
        """Build the transport."""
        return PollingTransport(interval=DEFAULT_POLLING_INTERVAL)
