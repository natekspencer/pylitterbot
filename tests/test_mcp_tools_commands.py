"""Tests for MCP command tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot3, LitterRobot4, LitterRobot5
from pylitterbot.enums import LitterBoxStatus, NightLightMode


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with LR4, LR3, and FeederRobot."""
    account = MagicMock(spec=Account)

    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = "Kitchen"
    lr4.id = "lr4-kitchen-id"
    lr4.model = "Litter-Robot 4"
    lr4.serial = "LR4K001"
    lr4.is_online = True
    lr4.power_status = "AC"
    lr4.status = LitterBoxStatus.READY
    lr4.start_cleaning = AsyncMock(return_value=True)
    lr4.reset = AsyncMock(return_value=True)
    lr4.set_power_status = AsyncMock(return_value=True)

    lr3 = MagicMock(spec=LitterRobot3)
    lr3.name = "Basement"
    lr3.id = "lr3-basement-id"
    lr3.model = "Litter-Robot 3"
    lr3.serial = "LR3B001"
    lr3.is_online = True
    lr3.power_status = "AC"
    lr3.status = LitterBoxStatus.READY
    lr3.start_cleaning = AsyncMock(return_value=True)
    lr3.set_power_status = AsyncMock(return_value=True)

    lr5 = MagicMock(spec=LitterRobot5)
    lr5.name = "Living Room"
    lr5.id = "lr5-living-id"
    lr5.model = "Litter-Robot 5"
    lr5.serial = "LR5L001"
    lr5.is_online = True
    lr5.power_status = "AC"
    lr5.status = LitterBoxStatus.READY
    lr5.start_cleaning = AsyncMock(return_value=True)
    lr5.reset = AsyncMock(return_value=True)
    lr5.set_power_status = AsyncMock(return_value=True)

    feeder = MagicMock(spec=FeederRobot)
    feeder.name = "Feeder"
    feeder.id = "feeder-id"
    feeder.model = "Feeder-Robot"
    feeder.serial = "FR001"
    feeder.is_online = True
    feeder.power_status = "AC"
    feeder.give_snack = AsyncMock(return_value=True)

    account.robots = [lr4, lr3, lr5, feeder]
    return account


class TestStartCleaning:
    """Tests for the start_cleaning tool."""

    @pytest.mark.asyncio()
    async def test_starts_cleaning_on_litter_robot(
        self, mock_account: MagicMock
    ) -> None:
        """start_cleaning calls start_cleaning on the resolved LitterRobot."""
        from pylitterbot.mcp.tools.commands import start_cleaning

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await start_cleaning(robot="Kitchen")
        mock_account.robots[0].start_cleaning.assert_awaited_once()
        assert result == "Started cleaning cycle on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_rejects_feeder_robot(self, mock_account: MagicMock) -> None:
        """start_cleaning raises ValueError for a FeederRobot."""
        from pylitterbot.mcp.tools.commands import start_cleaning

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Litter-Robot"),
        ):
            await start_cleaning(robot="Feeder")


class TestResetRobot:
    """Tests for the reset_robot tool."""

    @pytest.mark.asyncio()
    async def test_resets_lr4(self, mock_account: MagicMock) -> None:
        """reset_robot calls reset on an LR4."""
        from pylitterbot.mcp.tools.commands import reset_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await reset_robot(robot="Kitchen")
        mock_account.robots[0].reset.assert_awaited_once()
        assert result == "Reset 'Kitchen' successfully."

    @pytest.mark.asyncio()
    async def test_resets_lr5(self, mock_account: MagicMock) -> None:
        """reset_robot calls reset on an LR5."""
        from pylitterbot.mcp.tools.commands import reset_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await reset_robot(robot="Living Room")
        mock_account.robots[2].reset.assert_awaited_once()
        assert result == "Reset 'Living Room' successfully."

    @pytest.mark.asyncio()
    async def test_rejects_lr3(self, mock_account: MagicMock) -> None:
        """reset_robot raises ValueError for LR3 (no remote reset)."""
        from pylitterbot.mcp.tools.commands import reset_robot

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="does not support remote reset"),
        ):
            await reset_robot(robot="Basement")


class TestGiveSnack:
    """Tests for the give_snack tool."""

    @pytest.mark.asyncio()
    async def test_gives_snack(self, mock_account: MagicMock) -> None:
        """give_snack calls give_snack on the resolved FeederRobot."""
        from pylitterbot.mcp.tools.commands import give_snack

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await give_snack(robot="Feeder")
        mock_account.robots[3].give_snack.assert_awaited_once()
        assert result == "Dispensed snack from 'Feeder'."

    @pytest.mark.asyncio()
    async def test_rejects_litter_robot(self, mock_account: MagicMock) -> None:
        """give_snack raises ValueError for a LitterRobot."""
        from pylitterbot.mcp.tools.commands import give_snack

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Feeder-Robot"),
        ):
            await give_snack(robot="Kitchen")


class TestSetPowerStatus:
    """Tests for the set_power_status tool."""

    @pytest.mark.asyncio()
    async def test_turns_off_robot(self, mock_account: MagicMock) -> None:
        """set_power_status calls set_power_status(False) on the robot."""
        from pylitterbot.mcp.tools.commands import set_power_status

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_power_status(robot="Kitchen", enabled=False)
        mock_account.robots[0].set_power_status.assert_awaited_once_with(False)
        assert result == "Turned 'Kitchen' off."

    @pytest.mark.asyncio()
    async def test_turns_on_robot(self, mock_account: MagicMock) -> None:
        """set_power_status calls set_power_status(True) on the robot."""
        from pylitterbot.mcp.tools.commands import set_power_status

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_power_status(robot="Kitchen", enabled=True)
        mock_account.robots[0].set_power_status.assert_awaited_once_with(True)
        assert result == "Turned 'Kitchen' on."
