"""Websocket monitor."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from json import loads
from random import uniform
from typing import TYPE_CHECKING

from aiohttp import ClientWebSocketResponse, WSMsgType

from .robot import Robot
from .utils import utcnow

if TYPE_CHECKING:
    from .account import Account

_LOGGER = logging.getLogger(__name__)


async def cancel_task(*tasks: asyncio.Task | None) -> None:
    """Cancel task(s)."""
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class WebSocketMonitor:
    """Web socket monitor for a robot."""

    def __init__(self, account: Account, robot_class: type[Robot]) -> None:
        """Initialize a web socket monitor."""
        self._account = account
        self._robot_class = robot_class
        self._disconnect = False
        self._ws: ClientWebSocketResponse | None = None
        self._monitor_task: asyncio.Task | None = None
        self._receiver_task: asyncio.Task | None = None
        self._last_received: datetime | None = None

    @property
    def connected(self) -> bool:
        """Return `True` if the web socket is connected."""
        if self._disconnect:
            return False
        return False if self._ws is None else not self._ws.closed

    @property
    def websocket(self) -> ClientWebSocketResponse | None:
        """Return the web socket."""
        return self._ws

    @property
    def monitor(self) -> asyncio.Task | None:
        """Return the monitor task."""
        return self._monitor_task

    async def new_connection(self, start_monitor: bool = False) -> None:
        """Create a new connection and, optionally, start the monitor."""
        await cancel_task(self._receiver_task)
        self._disconnect = False
        self._ws = await self._account.session.websession.ws_connect(
            **await self._robot_class.get_websocket_config(self._account)
        )
        self._receiver_task = asyncio.ensure_future(self._receiver())
        if start_monitor:
            await self.start_monitor()

    async def _receiver(self) -> None:
        """Receive a message from a web socket."""
        if not (websocket := self._ws):
            return
        while not websocket.closed:
            try:
                msg = await websocket.receive(timeout=300)
                if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
                    break
                self._last_received = utcnow()
                if msg.type == WSMsgType.TEXT:
                    m_data = loads(msg.data)
                    # pylint: disable=protected-access
                    if (data := self._robot_class.parse_websocket_message(m_data)) and (
                        robot := self._account.get_robot(
                            data.get(self._robot_class._data_id)
                        )
                    ):
                        robot._update_data(data)
                elif msg.type == WSMsgType.ERROR:
                    self._log_message(msg, True)
                    continue
            except asyncio.TimeoutError:
                for robot in self._account.get_robots(self._robot_class):
                    await robot.send_subscribe_request(send_stop=True)
        self._log_message("web socket stopped")

    async def _monitor(self) -> None:
        """Monitor a web socket connection."""
        attempt = 0
        while not self._disconnect:
            while self.connected:
                await asyncio.sleep(1)
            if not self._disconnect:
                try:
                    await self.new_connection()
                except Exception as ex:  # pylint: disable=broad-except
                    self._log_message(ex, True)
                if not self._ws or self._ws.closed:
                    await asyncio.sleep(min(1 * 2**attempt + uniform(0, 1), 300))
                    attempt += 1
                    continue
                attempt = 0
                self._log_message("web socket connection reopened")
                for robot in self._account.get_robots(self._robot_class):
                    await robot.subscribe()

    async def start_monitor(self) -> None:
        """Start or restart the monitor task."""
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.ensure_future(self._monitor())

    async def stop_monitor(self) -> None:
        """Stop the monitor task."""
        await cancel_task(self._monitor_task)

    async def close(self) -> None:
        """Close the web socket."""
        self._disconnect = True
        if self._ws:
            await self._ws.close()
        await cancel_task(self._monitor_task, self._receiver_task)

    def _log_message(self, message: str | Exception, is_error: bool = False) -> None:
        """Log a message."""
        log_method = _LOGGER.error if is_error else _LOGGER.debug
        log_method("%s %s", self._robot_class.__name__, message)
