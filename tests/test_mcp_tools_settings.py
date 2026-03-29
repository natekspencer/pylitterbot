"""Tests for MCP settings tools."""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, LitterRobot3, LitterRobot4
from pylitterbot.enums import LitterBoxStatus, NightLightMode


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with an LR4 and LR3."""
    account = MagicMock(spec=Account)

    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = "Kitchen"
    lr4.id = "lr4-kitchen-id"
    lr4.model = "Litter-Robot 4"
    lr4.serial = "LR4K001"
    lr4.is_online = True
    lr4.power_status = "AC"
    lr4.status = LitterBoxStatus.READY
    lr4.set_name = AsyncMock(return_value=True)
    lr4.set_night_light = AsyncMock(return_value=True)
    lr4.set_night_light_brightness = AsyncMock(return_value=True)
    lr4.set_night_light_mode = AsyncMock(return_value=True)
    lr4.set_panel_lockout = AsyncMock(return_value=True)
    lr4.set_wait_time = AsyncMock(return_value=True)
    lr4.set_sleep_mode = AsyncMock(return_value=True)

    lr3 = MagicMock(spec=LitterRobot3)
    lr3.name = "Basement"
    lr3.id = "lr3-basement-id"
    lr3.model = "Litter-Robot 3"
    lr3.serial = "LR3B001"
    lr3.is_online = True
    lr3.power_status = "AC"
    lr3.status = LitterBoxStatus.READY
    lr3.set_name = AsyncMock(return_value=True)
    lr3.set_night_light = AsyncMock(return_value=True)
    lr3.set_panel_lockout = AsyncMock(return_value=True)
    lr3.set_wait_time = AsyncMock(return_value=True)
    lr3.set_sleep_mode = AsyncMock(return_value=True)

    account.robots = [lr4, lr3]
    return account


class TestSetName:
    """Tests for set_name tool."""

    @pytest.mark.asyncio()
    async def test_sets_name(self, mock_account: MagicMock) -> None:
        """set_name calls robot.set_name with the new name."""
        from pylitterbot.mcp.tools.settings import set_name

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_name(robot="Kitchen", name="New Kitchen")
        mock_account.robots[0].set_name.assert_awaited_once_with("New Kitchen")
        assert "New Kitchen" in result


class TestSetNightLight:
    """Tests for set_night_light tool."""

    @pytest.mark.asyncio()
    async def test_enables_night_light(self, mock_account: MagicMock) -> None:
        """set_night_light calls robot.set_night_light(True)."""
        from pylitterbot.mcp.tools.settings import set_night_light

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light(robot="Kitchen", enabled=True)
        mock_account.robots[0].set_night_light.assert_awaited_once_with(True)
        assert "enabled" in result.lower()


class TestSetNightLightBrightness:
    """Tests for set_night_light_brightness tool."""

    @pytest.mark.asyncio()
    async def test_sets_brightness(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness calls the LR4 method."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light_brightness(robot="Kitchen", brightness=50)
        mock_account.robots[0].set_night_light_brightness.assert_awaited_once_with(50)
        assert "50" in result

    @pytest.mark.asyncio()
    async def test_rejects_non_lr4(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness raises for non-LR4 robots."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 4"),
        ):
            await set_night_light_brightness(robot="Basement", brightness=50)


class TestSetNightLightMode:
    """Tests for set_night_light_mode tool."""

    @pytest.mark.asyncio()
    async def test_sets_mode_auto(self, mock_account: MagicMock) -> None:
        """set_night_light_mode converts string to NightLightMode enum."""
        from pylitterbot.mcp.tools.settings import set_night_light_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light_mode(robot="Kitchen", mode="auto")
        mock_account.robots[0].set_night_light_mode.assert_awaited_once_with(
            NightLightMode.AUTO
        )
        assert "auto" in result.lower()

    @pytest.mark.asyncio()
    async def test_rejects_invalid_mode(self, mock_account: MagicMock) -> None:
        """set_night_light_mode raises for invalid mode string."""
        from pylitterbot.mcp.tools.settings import set_night_light_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid night light mode"),
        ):
            await set_night_light_mode(robot="Kitchen", mode="blink")


class TestSetPanelLockout:
    """Tests for set_panel_lockout tool."""

    @pytest.mark.asyncio()
    async def test_locks_panel(self, mock_account: MagicMock) -> None:
        """set_panel_lockout calls robot.set_panel_lockout(True)."""
        from pylitterbot.mcp.tools.settings import set_panel_lockout

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_panel_lockout(robot="Kitchen", enabled=True)
        mock_account.robots[0].set_panel_lockout.assert_awaited_once_with(True)
        assert "enabled" in result.lower()


class TestSetWaitTime:
    """Tests for set_wait_time tool."""

    @pytest.mark.asyncio()
    async def test_sets_wait_time(self, mock_account: MagicMock) -> None:
        """set_wait_time calls robot.set_wait_time with minutes."""
        from pylitterbot.mcp.tools.settings import set_wait_time

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_wait_time(robot="Kitchen", minutes=15)
        mock_account.robots[0].set_wait_time.assert_awaited_once_with(15)
        assert "15" in result


class TestSetSleepMode:
    """Tests for set_sleep_mode tool."""

    @pytest.mark.asyncio()
    async def test_enables_sleep_mode_with_time(self, mock_account: MagicMock) -> None:
        """set_sleep_mode parses HH:MM and calls robot.set_sleep_mode."""
        from pylitterbot.mcp.tools.settings import set_sleep_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_sleep_mode(
                robot="Kitchen", enabled=True, start_time="22:30"
            )
        call_args = mock_account.robots[0].set_sleep_mode.call_args
        assert call_args[0][0] is True
        assert call_args[0][1] == time(22, 30)
        assert "enabled" in result.lower()

    @pytest.mark.asyncio()
    async def test_disables_sleep_mode(self, mock_account: MagicMock) -> None:
        """set_sleep_mode with enabled=False disables sleep."""
        from pylitterbot.mcp.tools.settings import set_sleep_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_sleep_mode(robot="Kitchen", enabled=False)
        call_args = mock_account.robots[0].set_sleep_mode.call_args
        assert call_args[0][0] is False
        assert "disabled" in result.lower()

    @pytest.mark.asyncio()
    async def test_raises_when_enabling_without_start_time(
        self, mock_account: MagicMock
    ) -> None:
        """set_sleep_mode raises ValueError when enabled=True but no start_time."""
        from pylitterbot.mcp.tools.settings import set_sleep_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="start_time is required"),
        ):
            await set_sleep_mode(robot="Kitchen", enabled=True)

    @pytest.mark.asyncio()
    async def test_raises_for_malformed_start_time(
        self, mock_account: MagicMock
    ) -> None:
        """set_sleep_mode raises ValueError for unparseable time strings."""
        from pylitterbot.mcp.tools.settings import set_sleep_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid start_time"),
        ):
            await set_sleep_mode(robot="Kitchen", enabled=True, start_time="2230")
