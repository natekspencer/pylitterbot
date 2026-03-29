"""Tests for MCP status tools: get_robots, get_robot_status."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot4
from pylitterbot.enums import LitterBoxStatus, NightLightMode


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with robots."""
    account = MagicMock(spec=Account)
    account.refresh_robots = AsyncMock()

    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = "Kitchen"
    lr4.id = "lr4-kitchen-id"
    lr4.model = "Litter-Robot 4"
    lr4.serial = "LR4K001"
    lr4.is_online = True
    lr4.power_status = "AC"
    lr4.status = LitterBoxStatus.READY
    lr4.waste_drawer_level = 45.0
    lr4.cycle_count = 12
    lr4.cycle_capacity = 30
    lr4.is_sleeping = False
    lr4.clean_cycle_wait_time_minutes = 7
    lr4.litter_level = 80.0
    lr4.night_light_mode = NightLightMode.AUTO
    lr4.pet_weight = 10.5
    lr4.refresh = AsyncMock()

    feeder = MagicMock(spec=FeederRobot)
    feeder.name = "Feeder"
    feeder.id = "feeder-id"
    feeder.model = "Feeder-Robot"
    feeder.serial = "FR001"
    feeder.is_online = True
    feeder.power_status = "AC"
    feeder.food_level = 70
    feeder.meal_insert_size = 0.25
    feeder.last_feeding = None
    feeder.refresh = AsyncMock()

    account.robots = [lr4, feeder]
    return account


class TestGetRobots:
    """Tests for the get_robots tool."""

    @pytest.mark.asyncio()
    async def test_returns_list_of_robot_summaries(
        self, mock_account: MagicMock
    ) -> None:
        """get_robots returns a summary for each robot."""
        from pylitterbot.mcp.tools.status import get_robots

        with patch(
            "pylitterbot.mcp.tools.status.get_account", return_value=mock_account
        ):
            result = await get_robots()
        assert len(result) == 2
        assert result[0]["name"] == "Kitchen"
        assert result[1]["name"] == "Feeder"

    @pytest.mark.asyncio()
    async def test_refreshes_robots_before_returning(
        self, mock_account: MagicMock
    ) -> None:
        """get_robots calls refresh_robots on the account."""
        from pylitterbot.mcp.tools.status import get_robots

        with patch(
            "pylitterbot.mcp.tools.status.get_account", return_value=mock_account
        ):
            await get_robots()
        mock_account.refresh_robots.assert_awaited_once()


class TestGetRobotStatus:
    """Tests for the get_robot_status tool."""

    @pytest.mark.asyncio()
    async def test_returns_detailed_status(self, mock_account: MagicMock) -> None:
        """get_robot_status returns a detailed summary for the specified robot."""
        from pylitterbot.mcp.tools.status import get_robot_status

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await get_robot_status(robot="Kitchen")
        assert result["name"] == "Kitchen"
        assert result["status"] == "Ready"

    @pytest.mark.asyncio()
    async def test_refreshes_robot_before_returning(
        self, mock_account: MagicMock
    ) -> None:
        """get_robot_status refreshes the individual robot."""
        from pylitterbot.mcp.tools.status import get_robot_status

        lr4 = mock_account.robots[0]
        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            await get_robot_status(robot="Kitchen")
        lr4.refresh.assert_awaited_once()
