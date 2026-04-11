"""Tests for MCP settings tools."""

from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot3, LitterRobot4, LitterRobot5
from pylitterbot.enums import BrightnessLevel, LitterBoxStatus, NightLightMode


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
    lr4.VALID_WAIT_TIMES = [3, 7, 15, 25, 30]

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
    lr3.VALID_WAIT_TIMES = [3, 7, 15]

    lr5 = MagicMock(spec=LitterRobot5)
    lr5.name = "Living Room"
    lr5.id = "lr5-living-id"
    lr5.model = "Litter-Robot 5 Pro"
    lr5.serial = "LR5L001"
    lr5.is_online = True
    lr5.power_status = "AC"
    lr5.status = LitterBoxStatus.READY
    lr5.is_pro = True
    lr5.set_panel_brightness = AsyncMock(return_value=True)
    lr5.set_volume = AsyncMock(return_value=True)
    lr5.set_privacy_mode = AsyncMock(return_value=True)
    lr5.set_camera_audio = AsyncMock(return_value=True)
    lr5.set_night_light_brightness = AsyncMock(return_value=True)
    lr5.set_night_light_mode = AsyncMock(return_value=True)

    feeder = MagicMock(spec=FeederRobot)
    feeder.name = "Feeder"
    feeder.id = "feeder-id"
    feeder.model = "Feeder-Robot"
    feeder.serial = "FR001"
    feeder.is_online = True
    feeder.power_status = "AC"
    feeder.set_gravity_mode = AsyncMock(return_value=True)

    account.robots = [lr4, lr3, lr5, feeder]
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
        assert result == "Renamed robot to 'New Kitchen'."

    @pytest.mark.asyncio()
    async def test_rejects_empty_name(self, mock_account: MagicMock) -> None:
        """set_name raises ValueError for empty string."""
        from pylitterbot.mcp.tools.settings import set_name

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="name must be a non-empty string"),
        ):
            await set_name(robot="Kitchen", name="")
        mock_account.robots[0].set_name.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_rejects_whitespace_only_name(self, mock_account: MagicMock) -> None:
        """set_name raises ValueError for whitespace-only names."""
        from pylitterbot.mcp.tools.settings import set_name

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="name must be a non-empty string"),
        ):
            await set_name(robot="Kitchen", name="   \t\n  ")
        mock_account.robots[0].set_name.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_strips_surrounding_whitespace(self, mock_account: MagicMock) -> None:
        """set_name strips whitespace before sending to the device."""
        from pylitterbot.mcp.tools.settings import set_name

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_name(robot="Kitchen", name="  New Kitchen  ")
        mock_account.robots[0].set_name.assert_awaited_once_with("New Kitchen")
        assert result == "Renamed robot to 'New Kitchen'."


class TestSetNightLight:
    """Tests for set_night_light tool."""

    @pytest.mark.asyncio()
    async def test_enables_night_light(self, mock_account: MagicMock) -> None:
        """set_night_light calls robot.set_night_light(True)."""
        from pylitterbot.mcp.tools.settings import set_night_light

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light(robot="Kitchen", enabled=True)
        mock_account.robots[0].set_night_light.assert_awaited_once_with(True)
        assert result == "Night light enabled on 'Kitchen'."


class TestSetNightLightBrightness:
    """Tests for set_night_light_brightness tool."""

    @pytest.mark.asyncio()
    async def test_sets_brightness(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness calls the LR4 method."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light_brightness(robot="Kitchen", brightness=50)
        mock_account.robots[0].set_night_light_brightness.assert_awaited_once_with(50)
        assert result == "Night light brightness set to 50 on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_rejects_invalid_brightness(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness raises ValueError for invalid values."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid brightness"),
        ):
            await set_night_light_brightness(robot="Kitchen", brightness=42)

    @pytest.mark.asyncio()
    async def test_rejects_non_lr4_or_lr5(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness raises for non-LR4/LR5 robots."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 4"),
        ):
            await set_night_light_brightness(robot="Basement", brightness=50)

    @pytest.mark.asyncio()
    async def test_sets_brightness_on_lr5(self, mock_account: MagicMock) -> None:
        """set_night_light_brightness accepts 0-100 range on LR5."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light_brightness(
                robot="Living Room", brightness=75
            )
        mock_account.robots[2].set_night_light_brightness.assert_awaited_once_with(75)
        assert result == "Night light brightness set to 75 on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_lr5_brightness_out_of_range(
        self, mock_account: MagicMock
    ) -> None:
        """set_night_light_brightness rejects values outside 0-100 for LR5."""
        from pylitterbot.mcp.tools.settings import set_night_light_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid brightness"),
        ):
            await set_night_light_brightness(robot="Living Room", brightness=150)


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
        assert result == "Night light mode set to 'auto' on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_rejects_invalid_mode(self, mock_account: MagicMock) -> None:
        """set_night_light_mode raises for invalid mode string."""
        from pylitterbot.mcp.tools.settings import set_night_light_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid night light mode"),
        ):
            await set_night_light_mode(robot="Kitchen", mode="blink")

    @pytest.mark.asyncio()
    async def test_sets_mode_on_lr5(self, mock_account: MagicMock) -> None:
        """set_night_light_mode works on LR5."""
        from pylitterbot.mcp.tools.settings import set_night_light_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_night_light_mode(robot="Living Room", mode="on")
        mock_account.robots[2].set_night_light_mode.assert_awaited_once_with(
            NightLightMode.ON
        )
        assert result == "Night light mode set to 'on' on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_lr3_for_mode(self, mock_account: MagicMock) -> None:
        """set_night_light_mode raises for LR3 (no night light mode support)."""
        from pylitterbot.mcp.tools.settings import set_night_light_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 4"),
        ):
            await set_night_light_mode(robot="Basement", mode="auto")


class TestSetPanelBrightness:
    """Tests for set_panel_brightness tool."""

    @pytest.mark.asyncio()
    async def test_sets_brightness_on_lr4(self, mock_account: MagicMock) -> None:
        """set_panel_brightness calls LR4 set_panel_brightness with BrightnessLevel."""
        from pylitterbot.mcp.tools.settings import set_panel_brightness

        lr4 = mock_account.robots[0]
        lr4.set_panel_brightness = AsyncMock(return_value=True)
        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_panel_brightness(robot="Kitchen", brightness=50)
        lr4.set_panel_brightness.assert_awaited_once_with(BrightnessLevel.MEDIUM)
        assert result == "Panel brightness set to 50 on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_sets_brightness_on_lr5(self, mock_account: MagicMock) -> None:
        """set_panel_brightness calls LR5 set_panel_brightness with BrightnessLevel."""
        from pylitterbot.mcp.tools.settings import set_panel_brightness

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_panel_brightness(robot="Living Room", brightness=100)
        mock_account.robots[2].set_panel_brightness.assert_awaited_once_with(
            BrightnessLevel.HIGH
        )
        assert result == "Panel brightness set to 100 on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_invalid_brightness(self, mock_account: MagicMock) -> None:
        """set_panel_brightness raises for invalid brightness values."""
        from pylitterbot.mcp.tools.settings import set_panel_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid brightness"),
        ):
            await set_panel_brightness(robot="Kitchen", brightness=42)

    @pytest.mark.asyncio()
    async def test_rejects_lr3(self, mock_account: MagicMock) -> None:
        """set_panel_brightness raises for LR3."""
        from pylitterbot.mcp.tools.settings import set_panel_brightness

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 4"),
        ):
            await set_panel_brightness(robot="Basement", brightness=50)


class TestSetVolume:
    """Tests for set_volume tool."""

    @pytest.mark.asyncio()
    async def test_sets_volume_on_lr5(self, mock_account: MagicMock) -> None:
        """set_volume calls LR5 set_volume with the given value."""
        from pylitterbot.mcp.tools.settings import set_volume

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_volume(robot="Living Room", volume=75)
        mock_account.robots[2].set_volume.assert_awaited_once_with(75)
        assert result == "Volume set to 75 on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_non_lr5(self, mock_account: MagicMock) -> None:
        """set_volume raises ValueError for non-LR5 robots."""
        from pylitterbot.mcp.tools.settings import set_volume

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 5"),
        ):
            await set_volume(robot="Kitchen", volume=50)

    @pytest.mark.asyncio()
    async def test_rejects_out_of_range(self, mock_account: MagicMock) -> None:
        """set_volume raises ValueError for volume outside 0-100."""
        from pylitterbot.mcp.tools.settings import set_volume

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid volume"),
        ):
            await set_volume(robot="Living Room", volume=101)


class TestSetPrivacyMode:
    """Tests for set_privacy_mode tool."""

    @pytest.mark.asyncio()
    async def test_enables_privacy_mode(self, mock_account: MagicMock) -> None:
        """set_privacy_mode calls LR5 set_privacy_mode(True)."""
        from pylitterbot.mcp.tools.settings import set_privacy_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_privacy_mode(robot="Living Room", enabled=True)
        mock_account.robots[2].set_privacy_mode.assert_awaited_once_with(True)
        assert result == "Privacy mode enabled on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_non_lr5(self, mock_account: MagicMock) -> None:
        """set_privacy_mode raises ValueError for non-LR5 robots."""
        from pylitterbot.mcp.tools.settings import set_privacy_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 5"),
        ):
            await set_privacy_mode(robot="Kitchen", enabled=True)


class TestSetCameraAudio:
    """Tests for set_camera_audio tool."""

    @pytest.mark.asyncio()
    async def test_enables_camera_audio(self, mock_account: MagicMock) -> None:
        """set_camera_audio calls LR5 set_camera_audio(True)."""
        from pylitterbot.mcp.tools.settings import set_camera_audio

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_camera_audio(robot="Living Room", enabled=True)
        mock_account.robots[2].set_camera_audio.assert_awaited_once_with(True)
        assert result == "Camera audio enabled on 'Living Room'."

    @pytest.mark.asyncio()
    async def test_rejects_non_lr5(self, mock_account: MagicMock) -> None:
        """set_camera_audio raises ValueError for non-LR5 robots."""
        from pylitterbot.mcp.tools.settings import set_camera_audio

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="only supported on Litter-Robot 5"),
        ):
            await set_camera_audio(robot="Kitchen", enabled=False)

    @pytest.mark.asyncio()
    async def test_rejects_non_pro_lr5(self, mock_account: MagicMock) -> None:
        """set_camera_audio rejects a standard (non-Pro) Litter-Robot 5.

        Camera audio is a Pro-only feature. Without this guard, standard LR5
        units pass the isinstance check and fail deeper in the device layer
        with a less useful error.
        """
        from pylitterbot.mcp.tools.settings import set_camera_audio

        lr5 = mock_account.robots[2]
        lr5.is_pro = False
        lr5.model = "Litter-Robot 5"

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(
                ValueError, match="only available on Litter-Robot 5 Pro"
            ),
        ):
            await set_camera_audio(robot="Living Room", enabled=True)
        lr5.set_camera_audio.assert_not_awaited()


class TestSetGravityMode:
    """Tests for set_gravity_mode tool."""

    @pytest.mark.asyncio()
    async def test_enables_gravity_mode(self, mock_account: MagicMock) -> None:
        """set_gravity_mode calls FeederRobot set_gravity_mode(True)."""
        from pylitterbot.mcp.tools.settings import set_gravity_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_gravity_mode(robot="Feeder", enabled=True)
        mock_account.robots[3].set_gravity_mode.assert_awaited_once_with(True)
        assert result == "Gravity mode enabled on 'Feeder'."

    @pytest.mark.asyncio()
    async def test_rejects_litter_robot(self, mock_account: MagicMock) -> None:
        """set_gravity_mode raises ValueError for non-Feeder robots."""
        from pylitterbot.mcp.tools.settings import set_gravity_mode

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Feeder-Robot"),
        ):
            await set_gravity_mode(robot="Kitchen", enabled=True)


class TestSetPanelLockout:
    """Tests for set_panel_lockout tool."""

    @pytest.mark.asyncio()
    async def test_locks_panel(self, mock_account: MagicMock) -> None:
        """set_panel_lockout calls robot.set_panel_lockout(True)."""
        from pylitterbot.mcp.tools.settings import set_panel_lockout

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_panel_lockout(robot="Kitchen", enabled=True)
        mock_account.robots[0].set_panel_lockout.assert_awaited_once_with(True)
        assert result == "Panel lockout enabled on 'Kitchen'."


class TestSetWaitTime:
    """Tests for set_wait_time tool."""

    @pytest.mark.asyncio()
    async def test_sets_wait_time(self, mock_account: MagicMock) -> None:
        """set_wait_time calls robot.set_wait_time with minutes."""
        from pylitterbot.mcp.tools.settings import set_wait_time

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_wait_time(robot="Kitchen", minutes=15)
        mock_account.robots[0].set_wait_time.assert_awaited_once_with(15)
        assert result == "Wait time set to 15 minutes on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_rejects_invalid_wait_time(self, mock_account: MagicMock) -> None:
        """set_wait_time raises ValueError for values outside valid set."""
        from pylitterbot.mcp.tools.settings import set_wait_time

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="Invalid wait time"),
        ):
            await set_wait_time(robot="Kitchen", minutes=10)

    @pytest.mark.asyncio()
    async def test_lr3_rejects_lr4_only_wait_time(
        self, mock_account: MagicMock
    ) -> None:
        """LR3 rejects 25 (valid on LR4/LR5 but not LR3) via VALID_WAIT_TIMES.

        Regression: the tool used to hardcode the valid set with a model
        string comparison. It now reads resolved.VALID_WAIT_TIMES so rules
        stay in sync with the robot classes.
        """
        from pylitterbot.mcp.tools.settings import set_wait_time

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match=r"Invalid wait time 25 for Litter-Robot 3"),
        ):
            await set_wait_time(robot="Basement", minutes=25)
        mock_account.robots[1].set_wait_time.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_lr4_accepts_lr4_only_wait_time(
        self, mock_account: MagicMock
    ) -> None:
        """LR4 accepts 25 because it is in LR4.VALID_WAIT_TIMES."""
        from pylitterbot.mcp.tools.settings import set_wait_time

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_wait_time(robot="Kitchen", minutes=25)
        mock_account.robots[0].set_wait_time.assert_awaited_once_with(25)
        assert result == "Wait time set to 25 minutes on 'Kitchen'."


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
        assert result == "Sleep mode enabled on 'Kitchen'."

    @pytest.mark.asyncio()
    async def test_disables_sleep_mode(self, mock_account: MagicMock) -> None:
        """set_sleep_mode with enabled=False disables sleep."""
        from pylitterbot.mcp.tools.settings import set_sleep_mode

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await set_sleep_mode(robot="Kitchen", enabled=False)
        call_args = mock_account.robots[0].set_sleep_mode.call_args
        assert call_args[0][0] is False
        assert result == "Sleep mode disabled on 'Kitchen'."

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
