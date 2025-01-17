"""pylitterbot enums."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

_LOGGER = logging.getLogger(__name__)


class FeederRobotCommand:
    """Known commands that can be sent to trigger an action or setting for a Feeder-Robot."""

    GIVE_SNACK = "giveSnack"
    SET_AUTO_NIGHT_MODE = "setAutoNightMode"
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
