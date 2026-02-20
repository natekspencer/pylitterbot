"""Feeder-Robot."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, time, timedelta
from typing import TYPE_CHECKING, Any, Callable, ClassVar, TypeVar, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

import aiohttp

from ..enums import FeederRobotCommand
from ..exceptions import InvalidCommandException
from ..transport import WebSocketMonitor, WebSocketProtocol
from ..utils import decode, to_timestamp, utcnow
from . import Robot
from .models import FEEDER_ROBOT_MODEL

if TYPE_CHECKING:
    from ..account import Account

_T = TypeVar("_T")

_LOGGER = logging.getLogger(__name__)

FEEDER_ENDPOINT = "https://cognito.hasura.iothings.site/v1/graphql"
COMMAND_ENDPOINT = (
    "https://42nk7qrhdg.execute-api.us-east-1.amazonaws.com/prod/command/feeder"
)
COMMAND_ENDPOINT_KEY = decode(
    "dzJ0UEZiamxQMTNHVW1iOGRNalVMNUIyWXlQVkQzcEo3RXk2Zno4dg=="
)

FOOD_LEVEL_MAP = {9: 100, 8: 70, 7: 60, 6: 50, 5: 40, 4: 30, 3: 20, 2: 10, 1: 5, 0: 0}
MEAL_INSERT_SIZE_CUPS_MAP = {0: 1 / 4, 1: 1 / 8}
MEAL_INSERT_SIZE_CUPS_REVERSE_MAP = {v: k for k, v in MEAL_INSERT_SIZE_CUPS_MAP.items()}

WEEKDAY_MAP = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


class FeederRobot(Robot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Feeder-Robot automatic pet feeder."""

    _attr_model = "Feeder-Robot"

    VALID_MEAL_INSERT_SIZES = list(MEAL_INSERT_SIZE_CUPS_MAP.values())

    _data_id = "id"
    _data_name = "name"
    _data_serial = "serial"
    _data_setup_date = "created_at"

    _last_updated_at: str | None = None
    _next_feeding: datetime | None = None

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a Feeder-Robot."""
        super().__init__(data, account)
        self._path = FEEDER_ENDPOINT

    def _state_info(self, key: str, default: _T | None = None) -> _T | Any:
        """Get an attribute from the data.state.info section."""
        return cast(_T, self._data["state"]["info"].get(key, default))

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        return str(self._state_info("fwVersion"))

    @property
    def food_level(self) -> int:
        """Return the food level."""
        return FOOD_LEVEL_MAP.get(self._state_info("level"), 0)

    @property
    def gravity_mode_enabled(self) -> bool:
        """Return `True` if gravity mode is enabled."""
        return bool(self._state_info("gravity"))

    @property
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""
        return bool(self._state_info("online"))

    @property
    def last_feeding(self) -> dict[str, Any] | None:
        """Get the last feeding meal or snack dispensed."""
        meal = self.last_meal
        if (snack := self.last_snack) is None or (
            meal is not None and meal["timestamp"] > snack["timestamp"]
        ):
            return meal
        return snack

    @property
    def last_meal(self) -> dict[str, Any] | None:
        """Get the last meal dispensed."""
        if not (meals := self._data.get("feeding_meal")):
            return None
        return {
            "timestamp": to_timestamp(meals[0]["timestamp"]),
            "amount": meals[0]["amount"] * meals[0]["meal_total_portions"],
            "name": meals[0]["meal_name"],
        }

    @property
    def last_snack(self) -> dict[str, Any] | None:
        """Get the last snack dispensed."""
        if not (snacks := self._data.get("feeding_snack")):
            return None
        return {
            "timestamp": to_timestamp(snacks[0]["timestamp"]),
            "amount": snacks[0]["amount"],
            "name": "snack",
        }

    @property
    def meal_insert_size(self) -> float:
        """Return the meal insert size in cups."""
        meal_insert_size = self._state_info("mealInsertSize", 0)
        if not (cups := MEAL_INSERT_SIZE_CUPS_MAP.get(meal_insert_size, 0)):
            _LOGGER.error('Unknown meal insert size "%s"', meal_insert_size)
        return cups

    @property
    def next_feeding(self) -> datetime | None:
        """Return the next feeding, if any."""
        if self._next_feeding and self._next_feeding < utcnow():
            self._calculate_next_feeding()
        return self._next_feeding

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return bool(self._state_info("autoNightMode"))

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""
        return bool(self._state_info("panelLockout"))

    @property
    def power_status(self) -> str:
        """Return the power type.

        `AC` = normal/mains
        `DC` = battery backup
        `NC` = unknown, not connected or off
        """
        if bool(self._state_info("acPower")):
            return "AC"
        if bool(self._state_info("dcPower")):
            return "DC"
        return "NC"  # This *may* never happen

    @property
    def timezone(self) -> str:
        """Return the timezone."""
        return str(self._data.get("timezone"))

    @property
    def updated_at(self) -> str:
        """Return the updated at string."""
        return str(self._data["state"].get("updated_at"))

    def get_food_dispensed_since(self, start: datetime) -> float:
        """Return the amount of food (in cups) since the given datetime."""
        feedings: list[dict] = list(self._data.get("feeding_meal") or [])
        feedings += self._data.get("feeding_snack") or []
        amount: float = sum(
            feeding["amount"] * feeding.get("meal_total_portions", 1)
            for feeding in feedings
            if cast(datetime, to_timestamp(feeding["timestamp"])) >= start
        )
        return amount

    def _calculate_next_feeding(self) -> None:
        """Return the next scheduled feeding, if any."""
        if self.gravity_mode_enabled:
            self._next_feeding = None
            return

        schedule = self._data["state"].get("active_schedule")
        if not schedule or "meals" not in schedule:
            self._next_feeding = None
            return

        tz = ZoneInfo(self.timezone)
        now = datetime.now(tz)

        next_meal_time = None

        for meal in schedule["meals"]:
            if meal.get("paused"):
                continue

            # Skip meals with a skip date that is today or in the future
            skip = meal.get("skip")
            if skip and skip != "0000-01-01T00:00:00.000":
                skip_dt = datetime.fromisoformat(skip)
                if skip_dt.tzinfo is None:
                    skip_dt = skip_dt.replace(tzinfo=tz)
                if skip_dt.date() >= now.date():
                    continue

            meal_time = time(meal["hour"], meal["minute"])

            for day in meal["days"]:
                target_weekday = WEEKDAY_MAP[day]
                days_ahead = (target_weekday - now.weekday() + 7) % 7

                # If today, check if meal time has already passed
                if days_ahead == 0 and meal_time <= now.time():
                    days_ahead = 7

                feeding_datetime = datetime.combine(
                    now.date() + timedelta(days=days_ahead), meal_time
                ).replace(tzinfo=tz)

                if next_meal_time is None or feeding_datetime < next_meal_time:
                    next_meal_time = feeding_datetime

        self._next_feeding = next_meal_time

    def _update_data(
        self,
        data: dict,
        partial: bool = False,
        callback: Callable[[], Any] | None = None,
    ) -> None:
        """Save the Feeder-Robot info from a data dictionary."""

        def _callback() -> None:
            if callback:
                callback()
            if self._last_updated_at != self.updated_at:
                self._calculate_next_feeding()
                self._last_updated_at = self.updated_at

        super()._update_data(data, partial, _callback)

    async def _dispatch_command(self, command: str, value: bool) -> bool:
        """Send a command to the Feeder-Robot."""
        try:
            await self._post(
                COMMAND_ENDPOINT,
                json={
                    "command": command,
                    "id": str(uuid4()),
                    "serial": self.serial,
                    "value": 1 if value else 0,
                },
                headers={"x-api-key": COMMAND_ENDPOINT_KEY},
            )
            return True
        except InvalidCommandException as ex:
            _LOGGER.error(ex)
            return False

    async def give_snack(self) -> bool:
        """Dispense a snack."""
        return await self._dispatch_command(FeederRobotCommand.GIVE_SNACK, True)

    async def refresh(self) -> None:
        """Refresh the Feeder-Robot's data from the API."""
        data = await self._post(
            json={
                "query": f"""
                    query GetFeeder($id: Int!) {{
                        feeder_unit_by_pk(id: $id) {FEEDER_ROBOT_MODEL}
                    }}
                    """,
                "variables": {"id": self.id},
            },
        )
        self._update_data(cast(dict, data).get("data", {}).get("feeder_unit_by_pk", {}))

    async def set_meal_insert_size(self, meal_insert_size: float) -> bool:
        """Set the meal insert size."""
        if (value := MEAL_INSERT_SIZE_CUPS_REVERSE_MAP.get(meal_insert_size)) is None:
            raise InvalidCommandException(
                f"Only meal insert sizes of {list(MEAL_INSERT_SIZE_CUPS_REVERSE_MAP)} are supported."
            )

        data = await self._post(
            json={
                "query": """
                    mutation UpdateFeederState($id: Int!, $state: jsonb) {
                        update_feeder_unit_state_by_pk(pk_columns: {id: $id}, _append: {info: $state}) {
                            info
                            updated_at
                        }
                    }
                """,
                "variables": {
                    "id": self._data["state"]["id"],
                    "state": {
                        "mealInsertSize": value,
                        "historyInvalidationDate": utcnow().strftime(
                            "%Y-%m-%dT%H:%M:%S.%fZ"
                        ),
                    },
                },
            }
        )
        data = cast(dict, data)
        self._update_data(
            {
                **self._data,
                "state": {
                    **self._data["state"],
                    **data.get("data", {}).get("update_feeder_unit_state_by_pk", {}),
                },
            }
        )
        return self.meal_insert_size == meal_insert_size

    async def set_name(self, name: str) -> bool:
        """Set the name."""
        data = await self._post(
            json={
                "query": """
                    mutation UpdateFeeder($id: Int!, $name: String!) {
                        update_feeder_unit_by_pk(pk_columns: {id: $id}, _set: {name: $name}) {
                            name
                        }
                    }
                """,
                "variables": {"id": self.id, "name": name},
            }
        )
        data = cast(dict, data)
        self._update_data(
            {**self._data, **data.get("data", {}).get("update_feeder_unit_by_pk", {})}
        )
        return self.name == name

    async def set_gravity_mode(self, value: bool) -> bool:
        """Turn the gravity mode on or off."""
        if await self._dispatch_command(FeederRobotCommand.SET_GRAVITY_MODE, value):
            data = deepcopy(self._data)
            data["state"]["info"]["gravity"] = value
            data["state"]["updated_at"] = utcnow().isoformat()
            self._update_data(data)
        return self.gravity_mode_enabled == value

    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light mode on or off."""
        if await self._dispatch_command(FeederRobotCommand.SET_AUTO_NIGHT_MODE, value):
            data = deepcopy(self._data)
            data["state"]["info"]["autoNightMode"] = value
            self._update_data(data)
        return self.night_light_mode_enabled == value

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        if await self._dispatch_command(FeederRobotCommand.SET_PANEL_LOCKOUT, value):
            data = deepcopy(self._data)
            data["state"]["info"]["panelLockout"] = value
            self._update_data(data)
        return self.panel_lock_enabled == value

    async def send_subscribe_request(self, send_stop: bool = False) -> None:
        """Send a subscribe request and, optionally, unsubscribe from a previous subscription."""
        if not self._ws:
            return
        if send_stop:
            await self.send_unsubscribe_request()
        self._ws_subscription_id = str(uuid4())

        await self._ws.send_json(
            {
                "type": "connection_init",
                "payload": {
                    "headers": {
                        "Authorization": await self._account.get_bearer_authorization()
                    }
                },
            }
        )
        await self._ws.send_json(
            {
                "type": "start",
                "id": self._ws_subscription_id,
                "payload": {
                    "query": f"""
                            subscription GetFeeder($id: Int!) {{
                                feeder_unit_by_pk(id: $id) {FEEDER_ROBOT_MODEL}
                            }}
                        """,
                    "variables": {"id": self.id},
                },
            }
        )

    @staticmethod
    async def get_websocket_config(account: Account) -> dict[str, Any]:
        """Get wesocket config."""
        return {
            "url": FEEDER_ENDPOINT,
            "params": None,
            "headers": {"sec-websocket-protocol": "graphql-ws"},
        }

    @staticmethod
    def parse_websocket_message(data: dict) -> dict | None:
        """Parse a wesocket message."""
        if (data_type := data["type"]) == "data":
            return cast(dict, data["payload"]["data"]["feeder_unit_by_pk"])
        if data_type == "error":
            _LOGGER.error(data)
        elif data_type not in ("connection_ack", "ka", "complete"):
            _LOGGER.debug(data)
        return None

    @classmethod
    async def fetch_for_account(cls, account: Account) -> list[dict[str, object]]:
        """Fetch robot data for account."""
        result = await account.session.post(
            FEEDER_ENDPOINT,
            json={
                "query": f"""
                    query GetFeeders {{
                        feeder_unit {FEEDER_ROBOT_MODEL}
                    }}
                """
            },
        )

        if not isinstance(result, dict):
            return []

        data = result.get("data")
        if not isinstance(data, dict):
            return []

        robots = data.get("feeder_unit")
        if isinstance(robots, list):
            return [r for r in robots if isinstance(r, dict)]

        return []

    async def _ws_config_factory(self) -> dict[str, Any]:
        """Return the WebSocket configuration."""
        return {
            "url": FEEDER_ENDPOINT,
            "headers": {"sec-websocket-protocol": "graphql-ws"},
        }

    def _ws_message_handler(self, data: dict) -> None:
        """Handle a message from the WebSocket."""
        parsed = self.parse_websocket_message(data)
        if isinstance(parsed, dict) and str(parsed.get(self._data_id)) == self.id:
            self._update_data(parsed)

    async def _ws_subscribe(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Subscribe to the WebSocket for updates."""
        self._ws_subscription_id = str(uuid4())
        auth = await self._account.get_bearer_authorization()
        await ws.send_json(
            {
                "type": "connection_init",
                "payload": {"headers": {"Authorization": auth}},
            }
        )
        await ws.send_json(
            {
                "type": "start",
                "id": self._ws_subscription_id,
                "payload": {
                    "query": f"""
                    subscription GetFeeder($id: Int!) {{
                        feeder_unit_by_pk(id: $id) {FEEDER_ROBOT_MODEL}
                    }}
                """,
                    "variables": {"id": self.id},
                },
            }
        )

    async def _ws_unsubscribe(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Unsubscribe from WebSocket updates."""
        if self._ws_subscription_id:
            await ws.send_json({"id": self._ws_subscription_id, "type": "stop"})

    _WS_PROTOCOL: ClassVar[WebSocketProtocol] = WebSocketProtocol(
        ws_config_factory=_ws_config_factory,
        subscribe_factory=_ws_subscribe,
        message_handler=_ws_message_handler,
        unsubscribe_factory=_ws_unsubscribe,
    )

    def _build_transport(self) -> WebSocketMonitor:
        """Build the transport."""
        return self._account.get_monitor_for(type(self), self._WS_PROTOCOL)
