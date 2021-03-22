from __future__ import annotations

import logging
from enum import Enum
from typing import Any, List

from pylitterbot.utils import send_deprecation_warning

_LOGGER = logging.getLogger(__name__)


class LitterBoxCommand:
    """Known commands that can be sent to trigger an action or setting for a Litter-Robot Connect self-cleaning litter box."""

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


class LitterBoxStatus(Enum):
    """Representation of a Litter-Robot status."""

    def __new__(
        cls, value: str, text: str, minimum_cycles_left: int = 3
    ) -> LitterBoxStatus:
        obj = object.__new__(cls)
        obj._value_ = value
        obj._text = text
        obj._minimum_cycles_left = minimum_cycles_left
        return obj

    BONNET_REMOVED = ("BR", "Bonnet Removed")
    CLEAN_CYCLE_COMPLETE = ("CCC", "Clean Cycle Complete")
    CLEAN_CYCLE = ("CCP", "Clean Cycle In Progress")
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
    def text(self) -> str:
        """Returns the textual representation of a litter box's status."""
        return self._text

    @property
    def label(self) -> str:  # pragma: no cover
        """.. deprecated::

        (deprecated) Use `text` instead.
        """
        send_deprecation_warning("label", "text")
        return self.text

    @property
    def minimum_cycles_left(self) -> int:
        """Returns the minimum number of cycles left based on a litter box's status."""
        return self._minimum_cycles_left

    @classmethod
    def get_drawer_full_statuses(
        cls,
        completely_full: bool = True,
        almost_full: bool = True,
        codes_only: bool = False,
    ) -> List[LitterBoxStatus | str]:
        """Returns the statuses that represent that the waste drawer is full."""
        return [
            status.value if codes_only else status
            for status in (
                [cls.DRAWER_FULL, cls.STARTUP_DRAWER_FULL] if completely_full else []
            )
            + ([cls.DRAWER_FULL_1, cls.DRAWER_FULL_2] if almost_full else [])
        ]
