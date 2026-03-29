"""Tests for MCP activity tools."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, LitterRobot4
from pylitterbot.activity import Activity, Insight
from pylitterbot.enums import LitterBoxStatus


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with an LR4."""
    account = MagicMock(spec=Account)

    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = "Kitchen"
    lr4.id = "lr4-kitchen-id"
    lr4.model = "Litter-Robot 4"
    lr4.serial = "LR4K001"
    lr4.is_online = True
    lr4.power_status = "AC"
    lr4.status = LitterBoxStatus.READY

    lr4.get_activity_history = AsyncMock(
        return_value=[
            Activity(
                timestamp=datetime(2024, 1, 15, 10, 30),
                action=LitterBoxStatus.CLEAN_CYCLE_COMPLETE,
            ),
            Activity(
                timestamp=datetime(2024, 1, 15, 8, 0),
                action="Pet Weight Recorded: 10.5 lbs",
            ),
        ]
    )

    lr4.get_insight = AsyncMock(
        return_value=Insight(
            total_cycles=45,
            average_cycles=1.5,
            cycle_history=[
                (date(2024, 1, 14), 2),
                (date(2024, 1, 15), 1),
            ],
        )
    )

    account.robots = [lr4]
    return account


class TestGetActivityHistory:
    """Tests for the get_activity_history tool."""

    @pytest.mark.asyncio()
    async def test_returns_formatted_activity_list(
        self, mock_account: MagicMock
    ) -> None:
        """get_activity_history returns a list of formatted activity dicts."""
        from pylitterbot.mcp.tools.activity import get_activity_history

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await get_activity_history(robot="Kitchen")
        assert len(result) == 2
        assert "timestamp" in result[0]
        assert "action" in result[0]

    @pytest.mark.asyncio()
    async def test_passes_limit_parameter(self, mock_account: MagicMock) -> None:
        """get_activity_history passes the limit to the robot method."""
        from pylitterbot.mcp.tools.activity import get_activity_history

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            await get_activity_history(robot="Kitchen", limit=50)
        mock_account.robots[0].get_activity_history.assert_awaited_once_with(limit=50)


class TestGetInsight:
    """Tests for the get_insight tool."""

    @pytest.mark.asyncio()
    async def test_returns_formatted_insight(self, mock_account: MagicMock) -> None:
        """get_insight returns a formatted dict with cycle data."""
        from pylitterbot.mcp.tools.activity import get_insight

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await get_insight(robot="Kitchen")
        assert result["total_cycles"] == 45
        assert result["average_cycles"] == 1.5
        assert result["total_days"] == 2
        assert len(result["cycle_history"]) == 2

    @pytest.mark.asyncio()
    async def test_passes_days_parameter(self, mock_account: MagicMock) -> None:
        """get_insight passes the days parameter to the robot method."""
        from pylitterbot.mcp.tools.activity import get_insight

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            await get_insight(robot="Kitchen", days=7)
        mock_account.robots[0].get_insight.assert_awaited_once_with(days=7)
