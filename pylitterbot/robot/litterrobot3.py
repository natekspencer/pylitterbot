"""Litter-Robot 3."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any, cast

from ..activity import Activity, Insight
from ..enums import LitterBoxCommand, LitterBoxStatus
from ..exceptions import InvalidCommandException
from ..utils import round_time, to_timestamp, today_at_time, urljoin, utcnow
from .litterrobot import MINIMUM_CYCLES_LEFT_DEFAULT, LitterRobot

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://v2.api.whisker.iothings.site"
DEFAULT_ENDPOINT_KEY = "cDduZE1vajYxbnBSWlA1Q1Z6OXY0VWowYkc3Njl4eTY3NThRUkJQYg=="
WEBSOCKET_ENDPOINT = "https://8s1fz54a82.execute-api.us-east-1.amazonaws.com/prod"

SLEEP_MODE_ACTIVE = "sleepModeActive"
SLEEP_MODE_TIME = "sleepModeTime"
UNIT_STATUS = "unitStatus"

SLEEP_DURATION_HOURS = 8
SLEEP_DURATION = timedelta(hours=SLEEP_DURATION_HOURS)


class LitterRobot3(LitterRobot):
    """Data and methods for interacting with a Litter-Robot 3 automatic, self-cleaning litter box."""

    _attr_model = "Litter-Robot 3"

    VALID_WAIT_TIMES = [3, 7, 15]

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Litter-Robot 3."""
        super().__init__(data, account)
        self._path = urljoin(
            DEFAULT_ENDPOINT,
            f"users/{account.user_id}/robots/{self.id}",
        )

    @property
    def clean_cycle_wait_time_minutes(self) -> int:
        """Return the number of minutes after a cat uses the Litter-Robot to begin an automatic clean cycle."""
        return int(self._data.get("cleanCycleWaitTimeMinutes", "7"), 16)

    @property
    def cycle_capacity(self) -> int:
        """Return the total anticpated number of clean cycles that can be performed before the waste drawer is full."""
        minimum_capacity = self.cycle_count + self._minimum_cycles_left
        if self._minimum_cycles_left < MINIMUM_CYCLES_LEFT_DEFAULT:
            return minimum_capacity
        return max(super().cycle_capacity, minimum_capacity)

    @property
    def is_drawer_full_indicator_triggered(self) -> bool:
        """Return `True` if the drawer full indicator has been triggered."""
        return bool(self._data.get("isDFITriggered", "0") != "0")

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return self.power_status != "NC" and self.status != LitterBoxStatus.OFFLINE

    @property
    def is_sleeping(self) -> bool:
        """Return `True` if the Litter-Robot is currently "sleeping" and won't automatically perform a clean cycle."""
        return (
            self.sleep_mode_enabled
            and int(self._data[SLEEP_MODE_ACTIVE][1:3]) < SLEEP_DURATION_HOURS
        )

    @property
    def is_waste_drawer_full(self) -> bool:
        """Return `True` if the Litter-Robot is reporting that the waste drawer is full."""
        return (
            self.is_drawer_full_indicator_triggered and self.cycle_count > 9
        ) or self._minimum_cycles_left < MINIMUM_CYCLES_LEFT_DEFAULT

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return bool(self._data.get("nightLightActive", "0") != "0")

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""
        return bool(self._data.get("panelLockActive", "0") != "0")

    @property
    def sleep_mode_enabled(self) -> bool:
        """Return `True` if sleep mode is enabled."""
        return bool(self._data.get(SLEEP_MODE_ACTIVE, "0") != "0")

    @property
    def status(self) -> LitterBoxStatus:
        """Return the status of the Litter-Robot."""
        return LitterBoxStatus(self.status_code)

    @property
    def status_code(self) -> str | None:
        """Return the status code of the Litter-Robot."""
        return self._data.get(UNIT_STATUS)

    @property
    def waste_drawer_level(self) -> float:
        """Return the approximate waste drawer level."""
        if (capacity := self.cycle_capacity) == 0:
            return 100
        return (self.cycle_count / capacity * 1000 + 0.5) // 1 / 10

    def _parse_sleep_info(self) -> None:
        """Parse the sleep info of a Litter-Robot."""
        sleep_mode_active = self._data.get(SLEEP_MODE_ACTIVE, "0")
        sleep_mode_time = self._data.get(SLEEP_MODE_TIME)

        start_time = end_time = None

        # The newer API uses `sleepModeTime` to avoid "drift" in the reported sleep start time
        if sleep_mode_time:
            start_time = today_at_time(
                datetime.fromtimestamp(sleep_mode_time, timezone.utc).timetz()
            )

        # Handle older API sleep start time
        if self.sleep_mode_enabled and not start_time:
            try:
                [hours, minutes, seconds] = list(
                    map(int, sleep_mode_active[1:].split(":"))
                )
                # Round to the nearest minute to reduce "drift"
                if self.last_seen is not None:
                    start_time = round_time(
                        today_at_time(self.last_seen.timetz())
                        + (
                            timedelta(hours=0 if self.is_sleeping else 24)
                            - timedelta(hours=hours, minutes=minutes, seconds=seconds)
                        )
                    )
                else:
                    start_time = datetime.now(timezone.utc)
            except ValueError:
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

    async def _dispatch_command(self, command: str, **kwargs: Any) -> bool:
        """Send a command to the Litter-Robot."""
        try:
            await self._post(
                LitterBoxCommand.ENDPOINT,
                {"command": f"{LitterBoxCommand.PREFIX}{command}"},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False

    async def refresh(self) -> None:
        """Refresh the Litter-Robot's data from the API."""
        data = cast(dict, await self._get())
        self._update_data(data)

    async def reset_settings(self) -> bool:
        """Set the Litter-Robot back to default settings."""
        return await self._dispatch_command(LitterBoxCommand.DEFAULT_SETTINGS)

    async def set_sleep_mode(self, value: bool, sleep_time: time | None = None) -> bool:
        """Set the sleep mode on the Litter-Robot."""
        if value and not isinstance(sleep_time, time):
            # Handle being able to set sleep mode by using previous start time or now.
            if not sleep_time:
                sleep_time = (self.sleep_mode_start_time or utcnow()).timetz()
            else:
                raise InvalidCommandException(  # pragma: no cover
                    "An attempt to turn on sleep mode was received with an invalid time. Check the time and try again."
                )

        data = await self._patch(
            json={
                "sleepModeEnable": value,
                **(
                    {
                        SLEEP_MODE_TIME: (
                            new_sleep_time := int(today_at_time(sleep_time).timestamp())
                        )
                    }
                    if sleep_time
                    else {}
                ),
            }
        )
        self._update_data(cast(dict, data))
        return sleep_time is None or self._data[SLEEP_MODE_TIME] == new_sleep_time

    async def set_wait_time(self, wait_time: int) -> bool:
        """Set the wait time on the Litter-Robot."""
        if wait_time not in self.VALID_WAIT_TIMES:
            raise InvalidCommandException(
                f"Attempt to send an invalid wait time to Litter-Robot. Wait time must be one of: {self.VALID_WAIT_TIMES}, but received {wait_time}"
            )
        return await self._dispatch_command(
            f"{LitterBoxCommand.WAIT_TIME}{f'{wait_time:X}'}"
        )

    async def set_name(self, name: str) -> bool:
        """Set the name."""
        data = cast(dict, await self._patch(json={self._data_name: name}))
        self._update_data(data)
        return self.name == name

    async def reset_waste_drawer(self) -> bool:
        """Reset the Litter-Robot's cycle counts and capacity."""
        data = await self._patch(
            json={
                self._data_cycle_count: 0,
                self._data_cycle_capacity: self.cycle_capacity,
                self._data_drawer_full_cycles: 0,
            }
        )
        self._update_data(cast(dict, data))
        return self.waste_drawer_level == 0.0

    async def get_activity_history(self, limit: int = 100) -> list[Activity]:
        """Return the activity history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )
        data = cast(dict, await self._get("activity", params={"limit": limit}))
        return [
            Activity(timestamp, LitterBoxStatus(activity[UNIT_STATUS]))
            for activity in data["activities"]
            if (timestamp := to_timestamp(activity["timestamp"])) is not None
        ]

    async def get_insight(
        self, days: int = 30, timezone_offset: int | None = None
    ) -> Insight:
        """Return the insight data."""
        insight = await self._get(
            "insights",
            params={
                "days": days,
                **(
                    {}
                    if timezone_offset is None
                    else {"timezoneOffset": timezone_offset}
                ),
            },
        )
        insight = cast(dict, insight)
        return Insight(
            insight["totalCycles"],
            insight["averageCycles"],
            [
                (
                    datetime.strptime(cycle["date"], "%Y-%m-%d").date(),
                    cycle["cyclesCompleted"],
                )
                for cycle in insight["cycleHistory"]
            ],
        )

    async def send_subscribe_request(self, send_stop: bool = False) -> None:
        """Send a subscribe request and, optionally, unsubscribe from a previous subscription."""
        if not self._ws:
            return
        await self._ws.send_json({"action": "ping"})

    async def send_unsubscribe_request(self) -> None:
        """Send an unsubscribe request."""
        # Litter-Robot 3 does not have a subscription id, so this just does nothing

    @staticmethod
    async def get_websocket_config(account: Account) -> dict[str, Any]:
        """Get wesocket config."""
        return {
            "url": WEBSOCKET_ENDPOINT,
            "params": None,
            "headers": {"authorization": await account.get_bearer_authorization()},
        }

    @staticmethod
    def parse_websocket_message(data: dict) -> dict | None:
        """Parse a wesocket message."""
        if data["type"] == "MODIFY" and data["name"] == "LitterRobot":
            return cast(dict, data["data"])
        _LOGGER.debug(data)
        return None
