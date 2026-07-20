"""Test transport layer."""

import asyncio
from collections import deque
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import WSMsgType

from pylitterbot.transport import PollingTransport, WebSocketMonitor, WebSocketProtocol

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    """Fake WebSocket that never receives a message."""

    closed = False

    async def receive(self) -> Mock:
        """Block long enough for the monitor receive timeout to fire."""
        await asyncio.sleep(60)
        return Mock(type=None)

    async def close(self) -> None:
        """Close the fake WebSocket."""
        self.closed = True


class FakeMessageWebSocket:
    """Fake WebSocket that returns predefined messages."""

    closed = False

    def __init__(self, *messages: Mock) -> None:
        """Initialize the fake WebSocket."""
        self.messages = deque(messages)
        self.receive_count = 0

    async def receive(self) -> Mock:
        """Return the next fake WebSocket message."""
        self.receive_count += 1
        return self.messages.popleft()

    async def close(self) -> None:
        """Close the fake WebSocket."""
        self.closed = True


class FakeWebSocketContext:
    """Async context manager for the fake WebSocket."""

    def __init__(self, ws: Any) -> None:
        """Initialize the context manager."""
        self.ws = ws

    async def __aenter__(self) -> Any:
        """Enter the fake WebSocket context."""
        return self.ws

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake WebSocket context."""
        return None


async def test_websocket_monitor_reconnects_after_stale_receive() -> None:
    """Test WebSocket monitor closes a stale connection so it can reconnect."""
    ws = FakeWebSocket()
    robot: Any = SimpleNamespace(
        id="robot-1",
        _account=SimpleNamespace(
            session=SimpleNamespace(
                websession=SimpleNamespace(
                    ws_connect=Mock(return_value=FakeWebSocketContext(ws))
                )
            )
        ),
    )

    async def ws_config_factory(robot: object) -> dict[str, Any]:
        """Return fake WebSocket configuration."""
        return {"url": "wss://example.test/graphql/realtime"}

    transport = WebSocketMonitor(
        WebSocketProtocol(ws_config_factory=ws_config_factory),
        stale_timeout=0.01,
    )
    transport._listeners[robot.id] = robot

    await transport._connect()

    assert ws.closed is True
    assert transport._ws is None


async def test_websocket_monitor_breaks_on_closed_message() -> None:
    """Test WebSocket monitor exits when aiohttp reports a closed WebSocket."""
    ws = FakeMessageWebSocket(Mock(type=WSMsgType.CLOSED))
    robot: Any = SimpleNamespace(
        id="robot-1",
        _account=SimpleNamespace(
            session=SimpleNamespace(
                websession=SimpleNamespace(
                    ws_connect=Mock(return_value=FakeWebSocketContext(ws))
                )
            )
        ),
    )

    async def ws_config_factory(robot: object) -> dict[str, Any]:
        """Return fake WebSocket configuration."""
        return {"url": "wss://example.test/graphql/realtime"}

    transport = WebSocketMonitor(WebSocketProtocol(ws_config_factory=ws_config_factory))
    transport._listeners[robot.id] = robot

    await transport._connect()

    assert ws.receive_count == 1
    assert transport._ws is None


async def test_websocket_monitor_ignores_invalid_json_message() -> None:
    """Test WebSocket monitor continues after a malformed text message."""
    bad_message = Mock(type=WSMsgType.TEXT)
    bad_message.json.side_effect = ValueError
    ws = FakeMessageWebSocket(bad_message, Mock(type=WSMsgType.CLOSED))
    robot: Any = SimpleNamespace(
        id="robot-1",
        _account=SimpleNamespace(
            session=SimpleNamespace(
                websession=SimpleNamespace(
                    ws_connect=Mock(return_value=FakeWebSocketContext(ws))
                )
            )
        ),
    )
    message_handler = Mock()

    async def ws_config_factory(robot: object) -> dict[str, Any]:
        """Return fake WebSocket configuration."""
        return {"url": "wss://example.test/graphql/realtime"}

    transport = WebSocketMonitor(
        WebSocketProtocol(
            ws_config_factory=ws_config_factory,
            message_handler=message_handler,
        )
    )
    transport._listeners[robot.id] = robot

    await transport._connect()

    assert ws.receive_count == 2
    assert message_handler.call_count == 0
    assert transport._ws is None


async def test_polling_transport_calls_refresh() -> None:
    """Test polling transport calls refresh."""
    transport = PollingTransport(interval=0.05)
    robot = AsyncMock()
    await transport.start(robot)
    await asyncio.sleep(0.25)  # allow ~2 refresh cycles
    await transport.stop(robot)
    assert robot.refresh.call_count >= 2


async def test_polling_transport_stops_cleanly() -> None:
    """Test polling transport stops cleanly."""
    transport = PollingTransport(interval=60.0)
    robot = AsyncMock()
    await transport.start(robot)
    await transport.stop(robot)  # should not block for 60 s
    assert transport._task is None or transport._task.done()
