"""Litter-Robot 4."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from enum import Enum, IntEnum, unique
from json import dumps, loads
from typing import TYPE_CHECKING, Any, Dict, Union, cast
from uuid import uuid4

from aiohttp import ClientWebSocketResponse, WSMsgType

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from ..activity import Activity, Insight
from ..enums import LitterBoxStatus, LitterRobot4Command
from ..exceptions import InvalidCommandException
from ..utils import encode, to_timestamp, utcnow
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
    "ROBOT_FIND_DUMP": LitterBoxStatus.DUMP_POSITION_FAULT,
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
    "powerTypeDC": "Battery Backup",
    "robotCycleStateCatDetect": LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
    "robotCycleStatusDump": LitterBoxStatus.CLEAN_CYCLE,
    "robotCycleStatusIdle": LitterBoxStatus.CLEAN_CYCLE_COMPLETE,
    "robotStatusCatDetect": LitterBoxStatus.CAT_DETECTED,
}

LITTER_LEVEL_EMPTY = 500


@unique
class NightLightLevel(IntEnum):
    """Night light level of a Litter-Robot 4 unit."""

    LOW = 25
    MEDIUM = 50
    HIGH = 100


@unique
class NightLightMode(Enum):
    """Night light mode of a Litter-Robot 4 unit."""

    ON = "ON"
    OFF = "OFF"
    AUTO = "AUTO"


class LitterRobot4(LitterRobot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Litter-Robot 4 automatic, self-cleaning litter box."""

    _attr_model = "Litter-Robot 4"

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

    _litter_level = LITTER_LEVEL_EMPTY
    _litter_level_exp: datetime | None = None

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Litter-Robot 4."""
        super().__init__(data, account)
        self._path = LR4_ENDPOINT
        self._ws: ClientWebSocketResponse | None = None
        self._ws_subscription_id: str | None = None
        self._ws_last_received: datetime | None = None

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return self._data.get("cleanCycleWaitTime", 7)

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
        return self._data.get("firmwareUpdateStatus", "UNKNOWN")

    @property
    def firmware_update_triggered(self) -> bool:
        """Return `True` if a firmware update has been triggered."""
        return self._data.get("isFirmwareUpdateTriggered", False)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""
        return self._data.get("isDFIFull", False)

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return self._data.get("isOnline", False)

    @property
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return bool(self._data.get("sleepStatus", "WAKE") != "WAKE")

    @property
    def is_waste_drawer_full(self) -> bool:
        """Return `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return self._data.get("isDFIFull", False)

    @property
    def litter_level(self) -> float:
        """Return the litter level.

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
    def night_light_brightness(self) -> int:
        """Return the night light brightness."""
        return int(self._data.get("nightLightBrightness", 0))

    @property
    def night_light_level(self) -> NightLightLevel | None:
        """Return the night light brightness."""
        if (brightness := self.night_light_brightness) in map(int, NightLightLevel):
            return NightLightLevel(brightness)
        return None

    @property
    def night_light_mode(self) -> NightLightMode | None:
        """Return the night light mode setting."""
        mode = self._data.get("nightLightMode", None)
        if mode in (mode.value for mode in NightLightMode):
            return NightLightMode(mode)
        return None

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return bool(self._data.get("nightLightMode", "OFF") != "OFF")

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""
        return self._data.get("isKeypadLockout", False)

    @property
    def pet_weight(self) -> float:
        """Return the last recorded pet weight in pounds (lbs)."""
        return self._data.get("catWeight", 0)

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
        """Return the status of the Litter-Robot."""
        status = self._data["robotStatus"]
        if status == "ROBOT_IDLE" and self.is_waste_drawer_full:
            return LitterBoxStatus.DRAWER_FULL
        return LR4_STATUS_MAP.get(status, LitterBoxStatus.UNKNOWN)

    @property
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""
        return (
            self.status.value
            if self.status != LitterBoxStatus.UNKNOWN
            else self._data.get("robotStatus")
        )

    @property
    def waste_drawer_level(self) -> float:
        """Return the approximate waste drawer level."""
        return self._data.get("DFILevelPercent", 0)

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
        self, brightness: int | NightLightLevel
    ) -> bool:
        """Set the night light brightness on the robot."""
        if brightness not in map(int, NightLightLevel):
            raise InvalidCommandException(
                f"Attempt to send an invalid night light level to Litter-Robot. "
                f"Brightness must be one of: {list(NightLightLevel)}, but received {brightness}"
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

    async def get_firmware_details(self) -> dict[str, bool | dict[str, str]] | None:
        """Get the firmware details."""
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
        data = cast(Dict[str, Dict[str, Dict[str, Union[bool, Dict[str, str]]]]], data)
        return data.get("data", {}).get("litterRobot4CompareFirmwareVersion", {})

    async def get_latest_firmware(self) -> str | None:
        """Get the latest firmware available."""
        if (firmware := await self.get_firmware_details()) is None:
            return None

        latest_firmware = (firmware).get("latestFirmware", {})
        latest_firmware = cast(Dict[str, str], latest_firmware)
        return (
            f"ESP: {latest_firmware.get('espFirmwareVersion')} / "
            f"PIC: {latest_firmware.get('picFirmwareVersion')} / "
            f"TOF: {latest_firmware.get('laserBoardFirmwareVersion')}"
        )

    async def has_firmware_update(self) -> bool:
        """Check if a firmware update is available."""
        if (firmware := await self.get_firmware_details()) is None:
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

    async def subscribe_for_updates(self) -> None:
        """Open a web socket connection to receive updates."""

        async def _authorization() -> str | None:
            if not self._account.session.is_token_valid():
                await self._account.session.refresh_token()
            return await self._account.session.get_bearer_authorization()

        async def _subscribe(send_stop: bool = False) -> None:
            if not self._ws:
                return
            if send_stop:
                await self._ws.send_json(
                    {"id": self._ws_subscription_id, "type": "stop"}
                )
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
                            "authorization": {"Authorization": await _authorization()}
                        },
                    },
                    "type": "start",
                }
            )

        async def _monitor() -> None:
            assert (websocket := self._ws)
            while True:
                try:
                    msg = await websocket.receive(timeout=80)
                    if msg.type in (
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSING,
                        WSMsgType.CLOSED,
                    ):
                        break
                    self._ws_last_received = utcnow()
                    if msg.type == WSMsgType.TEXT:
                        data = loads(msg.data)
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
                    elif msg.type == WSMsgType.ERROR:
                        _LOGGER.error(msg)
                        break
                except asyncio.TimeoutError:
                    _LOGGER.debug(
                        "Web socket monitor did not receive a message in time"
                    )
                    await _subscribe(send_stop=True)
            _LOGGER.debug("Web socket monitor stopped")
            if self._ws is not None:
                if self._ws.closed:
                    await self.subscribe_for_updates()
                    _LOGGER.debug("restarted connection")
                else:
                    asyncio.create_task(_monitor())
                    await _subscribe()
                    _LOGGER.debug("resubscribed")

        try:
            self._ws = await self._account.ws_connect(
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
                subscriber_id=self.id,
            )
            asyncio.create_task(_monitor())
            await _subscribe()
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(ex)

    async def unsubscribe_from_updates(self) -> None:
        """Stop the web socket."""
        if (websocket := self._ws) is not None and not websocket.closed:
            self._ws = None
            await websocket.send_json({"id": self._ws_subscription_id, "type": "stop"})
            await self._account.ws_disconnect(self.id)
            _LOGGER.debug("Unsubscribed from updates")
