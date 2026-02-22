"""pylitterbot enums."""

from __future__ import annotations

import logging
import re
from enum import Enum, IntEnum, IntFlag, auto, unique
from typing import Any

_LOGGER = logging.getLogger(__name__)


class LitterRobotCapability(IntFlag):
    """Capabilities for Litter-Robots."""

    # All models
    WASTE_DRAWER = auto()
    RESET_WASTE_DRAWER = auto()
    CLEAN_CYCLES = auto()
    CYCLE_WAIT_TIME = auto()
    PANEL_LOCKOUT = auto()
    NIGHT_LIGHT_MODE = auto()
    SLEEP_MODE = auto()

    # LR4+
    LITTER_LEVEL = auto()
    PET_WEIGHT = auto()
    NIGHT_LIGHT_BRIGHTNESS = auto()
    PANEL_BRIGHTNESS = auto()
    RESET = auto()
    FIRMWARE_UPDATE = auto()
    LITTER_HOPPER = auto()

    # LR5+

    # LR5 Pro only
    CAMERA = auto()


class FeederRobotCapability(IntFlag):
    """Capabilities for Feeder-Robots."""

    FOOD_LEVEL = auto()
    FOOD_DISPENSING = auto()
    FEEDING_SCHEDULE = auto()
    MEAL_INSERT_SIZE = auto()
    PANEL_LOCKOUT = auto()
    GIVE_SNACK = auto()
    SLEEP_MODE = auto()


class FeederRobotCommand:
    """Known commands that can be sent to trigger an action or setting for a Feeder-Robot."""

    GIVE_SNACK = "giveSnack"
    SET_AUTO_NIGHT_MODE = "setAutoNightMode"
    SET_GRAVITY_MODE = "setGravityMode"
    SET_PANEL_LOCKOUT = "setPanelLockout"


class LitterBoxCommand:
    """Known commands that can be sent to trigger an action or setting for Litter-Robot 3."""

    ENDPOINT = "dispatch-commands"
    PREFIX = "<"

    CLEAN = "C"
    DEFAULT_SETTINGS = "D"
    LOCK_OFF = "L0"
    LOCK_ON = "L1"
    NIGHT_LIGHT_OFF = "N0"
    NIGHT_LIGHT_ON = "N1"
    POWER_OFF = "P0"
    POWER_ON = "P1"
    # REFRESH = "R"  # valid command, not sure what it does though, reset or refresh maybe
    SLEEP_MODE_OFF = "S0"
    SLEEP_MODE_ON = "S1"
    WAIT_TIME = "W"


class LitterRobot4Command:
    """Known commands that can be sent to trigger an action or setting for a Litter-Robot 4."""

    CLEAN_CYCLE = "cleanCycle"
    KEY_PAD_LOCK_OUT_OFF = "keyPadLockOutOff"
    KEY_PAD_LOCK_OUT_ON = "keyPadLockOutOn"
    NIGHT_LIGHT_MODE_AUTO = "nightLightModeAuto"
    NIGHT_LIGHT_MODE_OFF = "nightLightModeOff"
    NIGHT_LIGHT_MODE_ON = "nightLightModeOn"
    PANEL_BRIGHTNESS_LOW = "panelBrightnessLow"
    PANEL_BRIGHTNESS_MEDIUM = "panelBrightnessMed"
    PANEL_BRIGHTNESS_HIGH = "panelBrightnessHigh"
    POWER_OFF = "powerOff"
    POWER_ON = "powerOn"
    REQUEST_STATE = "requestState"
    SET_CLUMP_TIME = "setClumpTime"
    SET_NIGHT_LIGHT_VALUE = "setNightLightValue"
    SHORT_RESET_PRESS = "shortResetPress"


class LitterRobot5Command:
    """Known commands that can be sent to trigger an action or setting for a Litter-Robot 5."""

    # POST /robots/{serial}/commands - operational commands
    CLEAN_CYCLE = "CLEAN_CYCLE"
    POWER_ON = "POWER_ON"
    POWER_OFF = "POWER_OFF"
    REMOTE_RESET = "REMOTE_RESET"
    FACTORY_RESET = "FACTORY_RESET"
    RESET_WASTE_LEVEL = "RESET_WASTE_LEVEL"
    CHANGE_FILTER = "CHANGE_FILTER"
    ONBOARD_PTAG_ON = "ONBOARD_PTAG_ON"
    ONBOARD_PTAG_OFF = "ONBOARD_PTAG_OFF"
    PRIVACY_MODE_ON = "PRIVACY_MODE_ON"
    PRIVACY_MODE_OFF = "PRIVACY_MODE_OFF"
    # Discovered via API 422 response but unverified on litter robot hardware:
    # NO_OP = "NO_OP"  # valid per API enum but returns INTERNAL_SERVER_ERROR
    # FEED_NOW = "FEED_NOW"  # likely for Feeder-Robot or litter hopper accessory
    # DISCARD_MEAL = "DISCARD_MEAL"  # likely for Feeder-Robot or litter hopper accessory

    # PATCH /robots/{serial} - settings keys
    CYCLE_DELAY = "cycleDelay"
    KEYPAD_LOCKED = "isKeypadLocked"
    LITTER_ROBOT_SETTINGS = "litterRobotSettings"
    NIGHT_LIGHT_SETTINGS = "nightLightSettings"
    PANEL_SETTINGS = "panelSettings"
    SOUND_SETTINGS = "soundSettings"


class LitterBoxStatusMixIn:
    """Litter box status mixin."""

    _text: str | None
    _minimum_cycles_left: int


class LitterBoxStatus(LitterBoxStatusMixIn, Enum):
    """Representation of a Litter-Robot status."""

    def __new__(
        cls, value: str | None, text: str | None = None, minimum_cycles_left: int = 3
    ) -> LitterBoxStatus:
        """Create and return a new Litter Box Status."""
        obj = object.__new__(cls)
        obj._value_ = value
        obj._text = text
        obj._minimum_cycles_left = minimum_cycles_left
        return obj

    BONNET_REMOVED = ("BR", "Bonnet Removed")
    CLEAN_CYCLE_COMPLETE = ("CCC", "Clean Cycle Complete")
    CLEAN_CYCLE = ("CCP", "Clean Cycle In Progress")
    CAT_DETECTED = ("CD", "Cat Detected")
    CAT_SENSOR_FAULT = ("CSF", "Cat Sensor Fault")
    CAT_SENSOR_INTERRUPTED = ("CSI", "Cat Sensor Interrupted")
    CAT_SENSOR_TIMING = ("CST", "Cat Sensor Timing")
    DRAWER_FULL_1 = ("DF1", "Drawer Almost Full - 2 Cycles Left", 2)
    DRAWER_FULL_2 = ("DF2", "Drawer Almost Full - 1 Cycle Left", 1)
    DRAWER_FULL = ("DFS", "Drawer Full", 0)
    DUMP_HOME_POSITION_FAULT = ("DHF", "Dump + Home Position Fault")
    DUMP_POSITION_FAULT = ("DPF", "Dump Position Fault")
    EMPTY_CYCLE = ("EC", "Empty Cycle")
    HOME_POSITION_FAULT = ("HPF", "Home Position Fault")
    OFF = ("OFF", "Off")
    OFFLINE = ("OFFLINE", "Offline")
    OVER_TORQUE_FAULT = ("OTF", "Over Torque Fault")
    PAUSED = ("P", "Clean Cycle Paused")
    PINCH_DETECT = ("PD", "Pinch Detect")
    POWER_DOWN = ("PWRD", "Powering Down")
    POWER_UP = ("PWRU", "Powering Up")
    READY = ("RDY", "Ready")
    STARTUP_CAT_SENSOR_FAULT = ("SCF", "Cat Sensor Fault At Startup")
    STARTUP_DRAWER_FULL = ("SDF", "Drawer Full At Startup", 0)
    STARTUP_PINCH_DETECT = ("SPF", "Pinch Detect At Startup")

    # Handle unknown/future unit statuses
    UNKNOWN = (None, "Unknown")

    @classmethod
    def _missing_(cls, _: Any) -> LitterBoxStatus:
        _LOGGER.error('Unknown status code "%s"', _)
        return cls.UNKNOWN

    @property
    def text(self) -> str | None:
        """Return the textual representation of a litter box's status."""
        return self._text

    @property
    def minimum_cycles_left(self) -> int:
        """Return the minimum number of cycles left based on a litter box's status."""
        return self._minimum_cycles_left

    @classmethod
    def get_drawer_full_statuses(
        cls,
        completely_full: bool = True,
        almost_full: bool = True,
        codes_only: bool = False,
    ) -> list[LitterBoxStatus | str]:
        """Return the statuses that represent that the waste drawer is full."""
        return [
            status.value if codes_only else status
            for status in (
                [cls.DRAWER_FULL, cls.STARTUP_DRAWER_FULL] if completely_full else []
            )
            + ([cls.DRAWER_FULL_1, cls.DRAWER_FULL_2] if almost_full else [])
        ]


@unique
class BrightnessLevel(IntEnum):
    """Brightness level of a Robot supporting brightness."""

    LOW = 25
    MEDIUM = 50
    HIGH = 100


@unique
class GlobeMotorFaultStatus(Enum):
    """Globe motor fault status."""

    NONE = "NONE"
    FAULT_CLEAR = "FAULT_CLEAR"
    FAULT_TIMEOUT = "FAULT_TIMEOUT"
    FAULT_DISCONNECT = "FAULT_DISCONNECT"
    FAULT_UNDERVOLTAGE = "FAULT_UNDERVOLTAGE"
    FAULT_OVERTORQUE_AMP = "FAULT_OVERTORQUE_AMP"
    FAULT_OVERTORQUE_SLOPE = "FAULT_OVERTORQUE_SLOPE"
    FAULT_PINCH = "FAULT_PINCH"
    FAULT_ALL_SENSORS = "FAULT_ALL_SENSORS"
    FAULT_UNKNOWN = "FAULT_UNKNOWN"

    @classmethod
    def from_raw(cls, raw: str | None) -> GlobeMotorFaultStatus:
        """Convert from a raw string."""
        if raw is None or (value := raw.strip()) == "":
            return cls.NONE

        # LR4 already matches exactly
        if value in cls._value2member_map_:
            return cls(value)

        # Convert PascalCase to SNAKE_CASE
        value = re.sub(r"(?<!^)(?=[A-Z])", "_", value).upper()

        # Strip common LR5 prefixes
        value = value.replace("MTR_", "")
        value = value.replace("MOTOR_", "")

        # Ensure FAULT_ prefix
        if not value.startswith("FAULT_") and value != "NONE":
            value = f"FAULT_{value}"

        try:
            return cls(value)
        except ValueError:
            return cls.FAULT_UNKNOWN


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
    """Night light mode of a Robot."""

    OFF = "OFF"
    ON = "ON"
    AUTO = "AUTO"
