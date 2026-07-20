"""Test transport layer."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from pylitterbot.transport import PollingTransport, WebSocketMonitor, WebSocketProtocol

pytestmark = pytest.mark.asyncio


class FakeWebSocket:
    """Fake WebSocket that never receives a message."""

    closed = False

    async def receive(self) -> None:
        """Block long enough for the monitor receive timeout to fire."""
        await asyncio.sleep(60)

    async def close(self) -> None:
        """Close the fake WebSocket."""
        self.closed = True


class FakeWebSocketContext:
    """Async context manager for the fake WebSocket."""

    def __init__(self, ws: FakeWebSocket) -> None:
        """Initialize the context manager."""
        self.ws = ws

    async def __aenter__(self) -> FakeWebSocket:
        """Enter the fake WebSocket context."""
        return self.ws

    async def __aexit__(self, *args: object) -> None:
        """Exit the fake WebSocket context."""
        return None


async def test_websocket_monitor_reconnects_after_stale_receive() -> None:
    """Test WebSocket monitor closes a stale connection so it can reconnect."""
    ws = FakeWebSocket()
    robot = SimpleNamespace(
        id="robot-1",
        _account=SimpleNamespace(
            session=SimpleNamespace(
                websession=SimpleNamespace(
                    ws_connect=Mock(return_value=FakeWebSocketContext(ws))
                )
            )
        ),
    )

    async def ws_config_factory(robot: object) -> dict[str, str]:
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
