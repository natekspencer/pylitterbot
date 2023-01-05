"""Websocket monitor."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from json import loads
from typing import TYPE_CHECKING

from aiohttp import ClientWebSocketResponse, WSMsgType

from .robot import Robot
from .utils import utcnow

if TYPE_CHECKING:
    from .account import Account

_LOGGER = logging.getLogger(__name__)


class WebSocketMonitor:
    """Web socket monitor for a robot."""

    def __init__(self, account: Account, robot_class: type[Robot]) -> None:
        """Initialize a web socket monitor."""
        self._account = account
        self._robot_class = robot_class
        self._ws: ClientWebSocketResponse | None = None
        self._monitor_task: asyncio.Task | None = None
        self._last_received: datetime | None = None

    @property
    def websocket(self) -> ClientWebSocketResponse | None:
        """Return the web socket."""
        return self._ws

    @property
    def monitor(self) -> asyncio.Task | None:
        """Return the monitor task."""
        return self._monitor_task

    async def new_connection(self) -> None:
        """Create a new connection."""
        self._ws = await self._account.session.websession.ws_connect(
            **await self._robot_class.get_websocket_config(self._account)
        )

    async def _monitor(self) -> None:
        """Monitor a web socket."""
        if not self._ws:
            return
        while True:
            try:
                msg = await self._ws.receive(timeout=80)
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
                self._last_received = utcnow()
                if msg.type == WSMsgType.TEXT:
                    data = loads(msg.data)
                    # pylint: disable=protected-access
                    if (data := self._robot_class.parse_websocket_message(data)) and (
                        robot := self._account.get_robot(
                            data.get(self._robot_class._data_id)
                        )
                    ):
                        robot._update_data(data)
                elif msg.type == WSMsgType.ERROR:
                    _LOGGER.error(msg)
                    break
            except asyncio.TimeoutError:
                _LOGGER.debug("Web socket monitor did not receive a message in time")
                # should we resubscribe?
                # await _subscribe(send_stop=True)
        _LOGGER.debug("Web socket monitor stopped")
        if self._ws is not None:
            if self._ws.closed:
                pass  # restart?
                # await self.subscribe_for_updates()
                # _LOGGER.debug("restarted connection")
            else:
                pass  # resubscribe?
                # await self._start_ws_monitor(ws_monitor)
                # await _subscribe()
                # _LOGGER.debug("resubscribed")

    async def start_monitor(self) -> None:
        """Start or restart the monitor task."""
        if (task := self._monitor_task) is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._monitor_task = asyncio.ensure_future(self._monitor())

    async def close(self) -> None:
        """Close the web socket."""
        if self._ws:
            await self._ws.close()
