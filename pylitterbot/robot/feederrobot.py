"""Feeder-Robot."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import uuid4

from ..enums import FeederRobotCommand
from ..exceptions import InvalidCommandException
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


class FeederRobot(Robot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Feeder-Robot automatic pet feeder."""

    _attr_model = "Feeder-Robot"

    VALID_MEAL_INSERT_SIZES = list(MEAL_INSERT_SIZE_CUPS_MAP.values())

    _data_id = "id"
    _data_name = "name"
    _data_serial = "serial"
    _data_setup_date = "created_at"

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
