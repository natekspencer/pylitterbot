"""Feeder-Robot."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from json import loads
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiohttp import ClientWebSocketResponse, WSMsgType

from ..activity import Activity, Insight
from ..enums import FeederRobotCommand
from ..exceptions import InvalidCommandException
from ..session import Session
from ..utils import decode, utcnow
from . import Robot
from .models import FEEDER_ROBOT_MODEL

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

FEEDER_ENDPOINT = "https://graphql.whisker.iothings.site/v1/graphql"
COMMAND_ENDPOINT = (
    "https://42nk7qrhdg.execute-api.us-east-1.amazonaws.com/prod/command/feeder"
)
COMMAND_ENDPOINT_KEY = decode(
    "dzJ0UEZiamxQMTNHVW1iOGRNalVMNUIyWXlQVkQzcEo3RXk2Zno4dg=="
)

# FOOD_LEVEL_PERCENT_MAP = {9: 100, 8: 70, 7: 60, 6: 50, 5: 40, 4: 30, 3: 20, 2: 10, 1: 5, 0: 0}
MEAL_INSERT_SIZE_CUPS_MAP = {0: 1 / 4, 1: 1 / 8}
MEAL_INSERT_SIZE_CUPS_REVERSE_MAP = {v: k for k, v in MEAL_INSERT_SIZE_CUPS_MAP.items()}


class FeederRobot(Robot):  # pylint: disable=abstract-method
    """Data and methods for interacting with a Feeder-Robot automatic pet feeder."""

    _data_id = "id"
    _data_name = "name"
    _data_serial = "serial"
    _data_setup_date = "created_at"

    def __init__(
        self,
        id: str = None,  # pylint: disable=redefined-builtin
        serial: str = None,
        user_id: str = None,
        name: str = None,
        session: Session = None,
        data: dict = None,
        account: Account | None = None,
    ) -> None:
        """Initialize an instance of a Feeder-Robot with individual attributes or a data dictionary."""
        super().__init__(id, serial, user_id, name, session, data, account)
        self._path = FEEDER_ENDPOINT
        self._ws: ClientWebSocketResponse | None = None
        self._ws_subscription_id: str | None = None
        self._ws_last_received: datetime | None = None

    def _state_info(self, key: str) -> Any:
        """Get an attribute from the data.state.info section."""
        return self._data["state"]["info"][key]

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        return str(self._state_info("fwVersion"))

    @property
    def food_level(self) -> int:
        """Return the food level."""
        return int(round(self._state_info("level") / 9 * 100, -1))

    @property
    def meal_insert_size(self) -> float:
        """Return the meal insert size in cups."""
        meal_insert_size = self._state_info("mealInsertSize")
        if not (cups := MEAL_INSERT_SIZE_CUPS_MAP.get(meal_insert_size, 0)):
            _LOGGER.error('Unknown meal insert size "%s"', meal_insert_size)
        return cups

    @property
    def model(self) -> str:
        """Return the robot model."""
        return "Feeder-Robot"

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return bool(self._state_info("autoNightMode"))

    @property
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""
        return bool(self._state_info("panelLockout"))

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
        assert isinstance(data, dict)
        self._update_data(data.get("data", {}).get("feeder_unit_by_pk", {}))

    async def set_meal_insert_size(self, meal_insert_size: float) -> bool:
        """Set the meal insert size."""
        if not (value := MEAL_INSERT_SIZE_CUPS_REVERSE_MAP.get(meal_insert_size)):
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
        assert isinstance(data, dict)
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
        assert isinstance(data, dict)
        self._update_data(
            {**self._data, **data.get("data", {}).get("update_feeder_unit_by_pk", {})}
        )
        return self.name == name

    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light mode on or off."""
        return await self._dispatch_command(
            FeederRobotCommand.SET_AUTO_NIGHT_MODE, value
        )

    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""
        return await self._dispatch_command(FeederRobotCommand.SET_PANEL_LOCKOUT, value)

    async def get_activity_history(
        self, limit: int = 100  # pylint: disable=unused-argument
    ) -> list[Activity]:
        """Return the activity history."""
        _LOGGER.warning("get_activity_history has not yet been implemented")
        return []

    async def get_insight(
        self,
        days: int = 30,  # pylint: disable=unused-argument
        timezone_offset: int = None,  # pylint: disable=unused-argument
    ) -> Insight:
        """Return the insight data."""
        _LOGGER.warning("get_insight has not yet been implemented")
        return Insight(0, 0, [])

    async def subscribe_for_updates(self) -> None:
        """Open a web socket connection to receive updates."""
        if self._session is None or self._session.websession is None:
            _LOGGER.warning("Robot has no session")
            return

        async def _authorization() -> str | None:
            assert self._session
            if not self._session.is_token_valid():
                await self._session.refresh_token()
            return await self._session.get_bearer_authorization()

        async def _subscribe(send_stop: bool = False) -> None:
            assert self._ws
            if send_stop:
                await self._ws.send_json(
                    {"id": self._ws_subscription_id, "type": "stop"}
                )
            self._ws_subscription_id = str(uuid4())
            await self._ws.send_json(
                {
                    "type": "connection_init",
                    "payload": {"headers": {"Authorization": await _authorization()}},
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
                                data["payload"]["data"]["feeder_unit_by_pk"]
                            )
                        elif data_type == "error":
                            _LOGGER.error(data)
                        elif data_type not in ("connection_ack", "ka", "complete"):
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
            assert self._account
            self._ws = await self._account.ws_connect(
                self._path,
                params=None,
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
            assert self._account
            await self._account.ws_disconnect(self.id)
            _LOGGER.debug("Unsubscribed from updates")
