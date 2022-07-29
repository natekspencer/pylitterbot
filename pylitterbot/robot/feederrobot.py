"""Feeder-Robot"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from json import loads
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from aiohttp import ClientWebSocketResponse, WSMsgType

from ..activity import Activity, Insight
from ..session import Session
from ..utils import utcnow
from . import Robot
from .models import FEEDER_ROBOT_MODEL

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

FEEDER_ENDPOINT = "https://graphql.whisker.iothings.site/v1/graphql"


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
        """Helper to get an attribute from the data.state.info section."""
        return self._data["state"]["info"][key]

    @property
    def firmware(self) -> str:
        """Return the firmware version."""
        return self._state_info("fwVersion")

    @property
    def food_level(self) -> int:
        """Return the food level."""
        return int(round(self._state_info("level") / 9 * 100, -1))

    @property
    def model(self) -> str:
        """Return the robot model."""
        return "Feeder-Robot"

    @property
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""
        return self._state_info("autoNightMode")

    @property
    def panel_lock_enabled(self) -> bool:
        """Returns `True` if the buttons on the robot are disabled."""
        return self._state_info("panelLockout")

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

    async def get_activity_history(
        self, limit: int = 100  # pylint: disable=unused-argument
    ) -> list[Activity]:
        """Returns the activity history."""
        _LOGGER.warning("get_activity_history has not yet been implemented")
        return []

    async def get_insight(
        self,
        days: int = 30,  # pylint: disable=unused-argument
        timezone_offset: int = None,  # pylint: disable=unused-argument
    ) -> Insight:
        """Returns the insight data."""
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
