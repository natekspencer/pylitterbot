"""Test transport layer."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from pylitterbot.transport import PollingTransport

pytestmark = pytest.mark.asyncio


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
