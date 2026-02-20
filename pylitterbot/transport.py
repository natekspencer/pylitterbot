"""Transport layer for robot update delivery."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, TypeVar

from aiohttp import ClientError, ClientWebSocketResponse, WSMsgType
from yarl import URL

from .utils import utcnow

if TYPE_CHECKING:
    from .robot import Robot

_LOGGER = logging.getLogger(__name__)
_RobotT = TypeVar("_RobotT", bound="Robot")

BACKOFF_SECONDS_MAX = 300.0


async def cancel_task(*tasks: asyncio.Task | None) -> None:
    """Cancel task(s)."""
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


@dataclass
class WebSocketProtocol(Generic[_RobotT]):
    """All WebSocket behaviour for a given robot type."""

    ws_config_factory: Callable[[_RobotT], Awaitable[dict[str, Any]]]
    subscribe_factory: (
        Callable[[_RobotT, ClientWebSocketResponse], Awaitable[None]] | None
    ) = None
    unsubscribe_factory: (
        Callable[[_RobotT, ClientWebSocketResponse], Awaitable[None]] | None
    ) = None
    message_handler: Callable[[_RobotT, dict], None] | None = None


class Transport(ABC):
    """Abstract transport: delivers updates to a robot."""

    _last_received: datetime | None = None

    @abstractmethod
    async def start(self, robot: Robot) -> None:
        """Start delivering updates to *robot*."""

    @abstractmethod
    async def stop(self, robot: Robot) -> None:
        """Stop delivering updates to *robot*."""


class WebSocketMonitor(Transport):
    """Shared WebSocket connection for all robots of the *same class*.

    Multiple robots of the same type register as listeners.  The monitor
    maintains exactly one WebSocket connection, reconnects with exponential
    backoff, and dispatches raw messages to every registered listener.
    """

    def __init__(
        self,
        protocol: WebSocketProtocol,
        reconnect_base: float = 1.0,
    ) -> None:
        """Initialize a WebSocket monitor."""
        self._protocol = protocol
        self._reconnect_base = reconnect_base

        self._listeners: dict[str, Robot] = {}
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._ws: ClientWebSocketResponse | None = None

        self._lock = asyncio.Lock()

    async def start(self, robot: Robot) -> None:
        """Register *robot* as a listener and ensure the loop is running."""
        async with self._lock:
            self._listeners[robot.id] = robot

            if self._task is None or self._task.done():
                self._stop_event.clear()
                self._task = asyncio.create_task(self._run())
            elif self._stop_event.is_set():
                # A concurrent stop() set the event while its task is still
                # winding down.  Clear it so _run() reconnects once _connect()
                # returns, rather than exiting and leaving this listener orphaned.
                self._stop_event.clear()
            elif self._ws is not None and self._protocol.subscribe_factory:
                await self._protocol.subscribe_factory(robot, self._ws)

    async def stop(self, robot: Robot) -> None:
        """Unregister *robot*; stop the loop when the last listener leaves."""
        task_to_await = None

        async with self._lock:
            self._listeners.pop(robot.id, None)

            if self._ws is not None and self._protocol.unsubscribe_factory:
                try:
                    await self._protocol.unsubscribe_factory(robot, self._ws)
                except Exception:
                    _LOGGER.debug(
                        "Error sending unsubscribe for %r", robot, exc_info=True
                    )

            if not self._listeners:
                self._stop_event.set()
                if self._ws is not None:
                    await self._ws.close()
                task_to_await = self._task

        # Await outside the lock so concurrent start() calls don't deadlock
        if task_to_await is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task_to_await), timeout=5.0)
            except asyncio.TimeoutError:
                await cancel_task(task_to_await)

    async def _run(self) -> None:
        """Run the WebSocket monitor."""
        delay = self._reconnect_base
        while not self._stop_event.is_set():
            try:
                await self._connect()
                delay = self._reconnect_base  # reset on clean close
            except (ClientError, OSError) as exc:
                _LOGGER.warning(
                    "WebSocket error (%s); reconnecting in %.1fs", exc, delay
                )
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass  # normal: keep looping
                delay = min(delay * 2, BACKOFF_SECONDS_MAX)
            except asyncio.CancelledError:
                break

    async def _connect(self) -> None:
        """Open one WebSocket session and dispatch messages."""
        if not self._listeners:
            return

        robot = next(iter(self._listeners.values()))
        config = await self._protocol.ws_config_factory(robot)
        connection_init = config.pop("connection_init", None)

        _LOGGER.debug("WebSocket connecting: %s", URL(config["url"]).with_query(None))
        session = robot._account.session.websession
        async with session.ws_connect(**config) as ws:
            _LOGGER.debug("WebSocket connected")
            self._ws = ws
            try:
                if connection_init:
                    await ws.send_json(connection_init)

                if self._protocol.subscribe_factory:
                    for robot in list(self._listeners.values()):
                        await self._protocol.subscribe_factory(robot, ws)

                async for msg in ws:
                    if self._stop_event.is_set():
                        await ws.close()
                        return
                    self._last_received = utcnow()
                    if msg.type == WSMsgType.TEXT:
                        if self._protocol.message_handler:
                            for robot in list(self._listeners.values()):
                                try:
                                    self._protocol.message_handler(robot, msg.json())
                                except Exception:
                                    _LOGGER.exception(
                                        "Error dispatching WS message to %r", robot
                                    )
                    elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                        break
            finally:
                self._ws = None


class PollingTransport(Transport):
    """REST polling loop for robots without a WebSocket endpoint (e.g. LR5).

    Each robot instance gets its *own* ``PollingTransport``.  The transport
    periodically calls ``robot.refresh()`` and lets the robot decide how to
    update its own state.
    """

    def __init__(self, interval: float = 30.0) -> None:
        """Initialize a polling transport."""
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self, robot: Robot) -> None:
        """Start polling *robot*."""
        if self._task and not self._task.done():
            return  # already running
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(robot))

    async def stop(self, robot: Robot) -> None:
        """Stop polling *robot*."""
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except asyncio.TimeoutError:
                await cancel_task(self._task)

    async def _run(self, robot: Robot) -> None:
        """Run the polling transport."""
        delay = self._interval
        while not self._stop_event.is_set():
            try:
                await robot.refresh()
                self._last_received = utcnow()
                delay = self._interval  # reset on success
            except Exception as exc:
                _LOGGER.warning("Polling refresh failed for %r: %s", robot, exc)
                delay = min(delay * 2, BACKOFF_SECONDS_MAX)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass  # normal: keep looping
