"""Tests for MCP helpers: robot resolution and formatting."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import (
    Account,
    FeederRobot,
    LitterRobot3,
    LitterRobot4,
    LitterRobot5,
    Pet,
)
from pylitterbot.enums import (
    BrightnessLevel,
    GlobeMotorFaultStatus,
    HopperStatus,
    LitterBoxStatus,
    LitterLevelState,
    NightLightMode,
)


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with two LR4s and one FeederRobot."""
    account = MagicMock(spec=Account)

    lr4_kitchen = MagicMock(spec=LitterRobot4)
    lr4_kitchen.name = "Kitchen"
    lr4_kitchen.id = "lr4-kitchen-id"
    lr4_kitchen.model = "Litter-Robot 4"
    lr4_kitchen.serial = "LR4K001"
    lr4_kitchen.is_online = True
    lr4_kitchen.power_status = "AC"
    lr4_kitchen.status = LitterBoxStatus.READY
    lr4_kitchen.waste_drawer_level = 45.0
    lr4_kitchen.cycle_count = 12
    lr4_kitchen.cycle_capacity = 30
    lr4_kitchen.is_sleeping = False
    lr4_kitchen.clean_cycle_wait_time_minutes = 7
    lr4_kitchen.litter_level = 80.0
    lr4_kitchen.night_light_mode = NightLightMode.AUTO
    lr4_kitchen.pet_weight = 10.5
    lr4_kitchen.firmware = "ESP: 1.0 / PIC: 2.0 / TOF: 3.0"
    lr4_kitchen.sleep_mode_enabled = True
    lr4_kitchen.sleep_schedule = MagicMock()
    lr4_kitchen.sleep_schedule.days = []
    lr4_kitchen.panel_brightness = BrightnessLevel.MEDIUM
    lr4_kitchen.night_light_brightness = 50
    lr4_kitchen.globe_motor_fault_status = GlobeMotorFaultStatus.NONE
    lr4_kitchen.hopper_status = HopperStatus.ENABLED
    lr4_kitchen.litter_level_state = LitterLevelState.OPTIMAL
    lr4_kitchen.refresh = AsyncMock()

    lr4_bedroom = MagicMock(spec=LitterRobot4)
    lr4_bedroom.name = "Bedroom"
    lr4_bedroom.id = "lr4-bedroom-id"
    lr4_bedroom.model = "Litter-Robot 4"
    lr4_bedroom.serial = "LR4B001"
    lr4_bedroom.is_online = True
    lr4_bedroom.power_status = "AC"
    lr4_bedroom.status = LitterBoxStatus.READY
    lr4_bedroom.waste_drawer_level = 20.0
    lr4_bedroom.cycle_count = 5
    lr4_bedroom.cycle_capacity = 30
    lr4_bedroom.is_sleeping = False
    lr4_bedroom.clean_cycle_wait_time_minutes = 7
    lr4_bedroom.litter_level = 90.0
    lr4_bedroom.night_light_mode = NightLightMode.ON
    lr4_bedroom.pet_weight = 8.0
    lr4_bedroom.refresh = AsyncMock()

    lr3 = MagicMock(spec=LitterRobot3)
    lr3.name = "Basement"
    lr3.id = "lr3-basement-id"
    lr3.model = "Litter-Robot 3"
    lr3.serial = "LR3B001"
    lr3.is_online = True
    lr3.power_status = "AC"
    lr3.status = LitterBoxStatus.READY
    lr3.waste_drawer_level = 10.0
    lr3.cycle_count = 3
    lr3.cycle_capacity = 30
    lr3.is_sleeping = False
    lr3.clean_cycle_wait_time_minutes = 7
    lr3.firmware = "1.0.0"
    lr3.sleep_mode_enabled = False
    lr3.sleep_schedule = None
    lr3.refresh = AsyncMock()

    lr5 = MagicMock(spec=LitterRobot5)
    lr5.name = "Living Room"
    lr5.id = "lr5-living-id"
    lr5.model = "Litter-Robot 5"
    lr5.serial = "LR5L001"
    lr5.is_online = True
    lr5.power_status = "AC"
    lr5.status = LitterBoxStatus.READY
    lr5.waste_drawer_level = 30.0
    lr5.cycle_count = 8
    lr5.cycle_capacity = 30
    lr5.is_sleeping = False
    lr5.clean_cycle_wait_time_minutes = 7
    lr5.litter_level = 75.0
    lr5.night_light_mode = NightLightMode.AUTO
    lr5.pet_weight = 11.0
    lr5.firmware = "ESP: 1.2.3 / MCU: 4.5.6"
    lr5.sleep_mode_enabled = True
    lr5.sleep_schedule = MagicMock()
    lr5.sleep_schedule.days = []
    lr5.panel_brightness = BrightnessLevel.HIGH
    lr5.night_light_brightness = 75
    lr5.globe_motor_fault_status = GlobeMotorFaultStatus.NONE
    lr5.is_pro = True
    lr5.privacy_mode = "Normal"
    lr5.sound_volume = 50
    lr5.camera_audio_enabled = True
    lr5.wifi_rssi = -45
    lr5.is_laser_dirty = False
    lr5.is_gas_sensor_fault_detected = False
    lr5.night_light_color = "#FF8800"
    lr5.next_filter_replacement_date = None
    lr5.odometer_empty_cycles = 100
    lr5.odometer_filter_cycles = 50
    lr5.odometer_power_cycles = 200
    lr5.refresh = AsyncMock()

    feeder = MagicMock(spec=FeederRobot)
    feeder.name = "Feeder"
    feeder.id = "feeder-id"
    feeder.model = "Feeder-Robot"
    feeder.serial = "FR001"
    feeder.is_online = True
    feeder.power_status = "AC"
    feeder.food_level = 70
    feeder.meal_insert_size = 0.25
    feeder.last_feeding = {
        "timestamp": datetime(2024, 1, 1, 12, 0, 0),
        "amount": 0.25,
        "name": "snack",
    }
    feeder.gravity_mode_enabled = False
    feeder.next_feeding = None
    feeder.refresh = AsyncMock()

    account.robots = [lr4_kitchen, lr4_bedroom, lr3, lr5, feeder]
    return account


@pytest.fixture()
def mock_pet() -> MagicMock:
    """Create a mock Pet."""
    pet = MagicMock(spec=Pet)
    pet.name = "Luna"
    pet.id = "pet-luna-id"
    pet.pet_type = MagicMock()
    pet.pet_type.name = "CAT"
    pet.gender = MagicMock()
    pet.gender.name = "FEMALE"
    pet.weight = 10.5
    pet.breeds = ["Domestic Shorthair"]
    pet.is_active = True
    return pet


class TestResolveRobot:
    """Tests for resolve_robot."""

    @pytest.mark.asyncio()
    async def test_resolves_robot_by_exact_name(self, mock_account: MagicMock) -> None:
        """resolve_robot returns the correct robot when given an exact name."""
        from pylitterbot.mcp.helpers import resolve_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_robot("Kitchen")
        assert robot.id == "lr4-kitchen-id"

    @pytest.mark.asyncio()
    async def test_resolves_robot_by_case_insensitive_name(
        self, mock_account: MagicMock
    ) -> None:
        """resolve_robot matches names case-insensitively."""
        from pylitterbot.mcp.helpers import resolve_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_robot("kitchen")
        assert robot.id == "lr4-kitchen-id"

    @pytest.mark.asyncio()
    async def test_resolves_robot_by_id(self, mock_account: MagicMock) -> None:
        """resolve_robot returns the correct robot when given an ID."""
        from pylitterbot.mcp.helpers import resolve_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_robot("feeder-id")
        assert robot.name == "Feeder"

    @pytest.mark.asyncio()
    async def test_raises_for_unknown_robot(self, mock_account: MagicMock) -> None:
        """resolve_robot raises ValueError for an unknown identifier."""
        from pylitterbot.mcp.helpers import resolve_robot

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="No robot found"),
        ):
            await resolve_robot("Nonexistent")


class TestResolveLitterRobot:
    """Tests for resolve_litter_robot."""

    @pytest.mark.asyncio()
    async def test_resolves_litter_robot(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot returns a LitterRobot when given a valid name."""
        from pylitterbot.mcp.helpers import resolve_litter_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_litter_robot("Kitchen")
        assert robot.id == "lr4-kitchen-id"

    @pytest.mark.asyncio()
    async def test_raises_for_feeder_robot(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot raises ValueError for a FeederRobot."""
        from pylitterbot.mcp.helpers import resolve_litter_robot

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Litter-Robot"),
        ):
            await resolve_litter_robot("Feeder")


class TestResolveFeederRobot:
    """Tests for resolve_feeder_robot."""

    @pytest.mark.asyncio()
    async def test_resolves_feeder_robot(self, mock_account: MagicMock) -> None:
        """resolve_feeder_robot returns a FeederRobot when given a valid name."""
        from pylitterbot.mcp.helpers import resolve_feeder_robot

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_feeder_robot("Feeder")
        assert robot.id == "feeder-id"

    @pytest.mark.asyncio()
    async def test_raises_for_litter_robot(self, mock_account: MagicMock) -> None:
        """resolve_feeder_robot raises ValueError for a LitterRobot."""
        from pylitterbot.mcp.helpers import resolve_feeder_robot

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Feeder-Robot"),
        ):
            await resolve_feeder_robot("Kitchen")


class TestFormatRobotSummary:
    """Tests for format_robot_summary."""

    def test_formats_litter_robot_4(self, mock_account: MagicMock) -> None:
        """format_robot_summary includes LR4-specific fields."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr4 = mock_account.robots[0]
        summary = format_robot_summary(lr4)
        assert summary["name"] == "Kitchen"
        assert summary["model"] == "Litter-Robot 4"
        assert summary["is_online"] is True
        assert summary["status"] == "Ready"
        assert summary["waste_drawer_level"] == 45.0
        assert summary["cycle_count"] == 12
        assert summary["litter_level"] == 80.0
        assert summary["night_light_mode"] == "AUTO"
        assert summary["pet_weight"] == 10.5

    def test_formats_feeder_robot(self, mock_account: MagicMock) -> None:
        """format_robot_summary includes FeederRobot-specific fields."""
        from pylitterbot.mcp.helpers import format_robot_summary

        feeder = mock_account.robots[4]
        summary = format_robot_summary(feeder)
        assert summary["name"] == "Feeder"
        assert summary["model"] == "Feeder-Robot"
        assert summary["food_level"] == 70
        assert summary["meal_insert_size"] == 0.25
        assert summary["gravity_mode_enabled"] is False
        assert summary["next_feeding"] is None


class TestResolveLitterRobot4:
    """Tests for resolve_litter_robot_4."""

    @pytest.mark.asyncio()
    async def test_resolves_lr4(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot_4 returns a LitterRobot4 by name."""
        from pylitterbot.mcp.helpers import resolve_litter_robot_4

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_litter_robot_4("Kitchen")
        assert robot.id == "lr4-kitchen-id"

    @pytest.mark.asyncio()
    async def test_rejects_lr5(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot_4 raises ValueError for a LitterRobot5."""
        from pylitterbot.mcp.helpers import resolve_litter_robot_4

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Litter-Robot 4"),
        ):
            await resolve_litter_robot_4("Living Room")

    @pytest.mark.asyncio()
    async def test_rejects_feeder(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot_4 raises ValueError for a FeederRobot."""
        from pylitterbot.mcp.helpers import resolve_litter_robot_4

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Litter-Robot 4"),
        ):
            await resolve_litter_robot_4("Feeder")


class TestResolveLitterRobot5:
    """Tests for resolve_litter_robot_5."""

    @pytest.mark.asyncio()
    async def test_resolves_lr5(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot_5 returns a LitterRobot5 by name."""
        from pylitterbot.mcp.helpers import resolve_litter_robot_5

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_litter_robot_5("Living Room")
        assert robot.id == "lr5-living-id"

    @pytest.mark.asyncio()
    async def test_rejects_lr4(self, mock_account: MagicMock) -> None:
        """resolve_litter_robot_5 raises ValueError for a LitterRobot4."""
        from pylitterbot.mcp.helpers import resolve_litter_robot_5

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="not a Litter-Robot 5"),
        ):
            await resolve_litter_robot_5("Kitchen")


class TestFormatRobotSummaryExpandedFields:
    """Tests for expanded format_robot_summary fields."""

    def test_lr4_includes_firmware_and_sleep(self, mock_account: MagicMock) -> None:
        """format_robot_summary includes firmware and sleep fields for LR4."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr4 = mock_account.robots[0]
        summary = format_robot_summary(lr4)
        assert summary["firmware"] == "ESP: 1.0 / PIC: 2.0 / TOF: 3.0"
        assert summary["sleep_mode_enabled"] is True
        assert "sleep_schedule" in summary

    def test_lr4_includes_panel_and_sensor_fields(
        self, mock_account: MagicMock
    ) -> None:
        """format_robot_summary includes LR4-specific panel/sensor fields."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr4 = mock_account.robots[0]
        summary = format_robot_summary(lr4)
        assert summary["panel_brightness"] == "MEDIUM"
        assert summary["night_light_brightness"] == 50
        assert summary["globe_motor_fault_status"] == "NONE"
        assert summary["hopper_status"] == "ENABLED"
        assert summary["litter_level_state"] == "OPTIMAL"

    def test_lr5_includes_pro_and_sensor_fields(self, mock_account: MagicMock) -> None:
        """format_robot_summary includes LR5-specific fields."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr5 = mock_account.robots[3]
        summary = format_robot_summary(lr5)
        assert summary["firmware"] == "ESP: 1.2.3 / MCU: 4.5.6"
        assert summary["panel_brightness"] == "HIGH"
        assert summary["is_pro"] is True
        assert summary["privacy_mode"] == "Normal"
        assert summary["sound_volume"] == 50
        assert summary["camera_audio_enabled"] is True
        assert summary["wifi_rssi"] == -45
        assert summary["is_laser_dirty"] is False
        assert summary["is_gas_sensor_fault_detected"] is False
        assert summary["night_light_color"] == "#FF8800"
        assert summary["odometer_empty_cycles"] == 100
        assert summary["odometer_filter_cycles"] == 50
        assert summary["odometer_power_cycles"] == 200

    def test_lr4_handles_none_enums(self, mock_account: MagicMock) -> None:
        """format_robot_summary handles None enum values gracefully."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr4 = mock_account.robots[0]
        lr4.panel_brightness = None
        lr4.hopper_status = None
        lr4.litter_level_state = None
        lr4.globe_motor_fault_status = None
        lr4.sleep_schedule = None
        summary = format_robot_summary(lr4)
        assert summary["panel_brightness"] is None
        assert summary["hopper_status"] is None
        assert summary["litter_level_state"] is None
        assert summary["globe_motor_fault_status"] is None
        assert summary["sleep_schedule"] is None

    def test_lr5_handles_none_filter_date(self, mock_account: MagicMock) -> None:
        """format_robot_summary handles None next_filter_replacement_date."""
        from pylitterbot.mcp.helpers import format_robot_summary

        lr5 = mock_account.robots[3]
        lr5.next_filter_replacement_date = None
        summary = format_robot_summary(lr5)
        assert summary["next_filter_replacement_date"] is None

    def test_feeder_handles_datetime_next_feeding(
        self, mock_account: MagicMock
    ) -> None:
        """format_robot_summary serializes next_feeding datetime to isoformat."""
        from datetime import datetime

        from pylitterbot.mcp.helpers import format_robot_summary

        feeder = mock_account.robots[4]
        feeder.next_feeding = datetime(2024, 6, 15, 8, 30)
        summary = format_robot_summary(feeder)
        assert summary["next_feeding"] == "2024-06-15T08:30:00"


class TestResolveRobotCasefoldAndNone:
    """Tests for casefold and None-name safety in resolve_robot."""

    @pytest.mark.asyncio()
    async def test_resolve_robot_casefold(self, mock_account: MagicMock) -> None:
        """resolve_robot matches names using casefold for Unicode correctness.

        German ß casefolded is 'ss'; lower() leaves ß unchanged so 'straße'
        would not match 'strasse' with lower() but does with casefold().
        """
        from pylitterbot.mcp.helpers import resolve_robot

        german_robot = MagicMock(spec=LitterRobot4)
        german_robot.name = "Straße"
        german_robot.id = "de-robot-id"
        mock_account.robots = [german_robot]

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_robot("strasse")
        assert robot.id == "de-robot-id"

    @pytest.mark.asyncio()
    async def test_resolve_robot_handles_none_name(
        self, mock_account: MagicMock
    ) -> None:
        """resolve_robot does not crash when a robot has name=None."""
        from pylitterbot.mcp.helpers import resolve_robot

        nameless_robot = MagicMock(spec=LitterRobot4)
        nameless_robot.name = None
        nameless_robot.id = "nameless-id"
        mock_account.robots = [nameless_robot]

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            robot = await resolve_robot("nameless-id")
        assert robot.id == "nameless-id"


class TestFeederRobotLastFeedingJsonSafe:
    """Tests that format_robot_summary serializes FeederRobot.last_feeding to JSON."""

    def test_last_feeding_with_datetime_is_json_serializable(
        self, mock_account: MagicMock
    ) -> None:
        """format_robot_summary serializes last_feeding timestamp to ISO string."""
        import json
        from datetime import datetime

        from pylitterbot.mcp.helpers import format_robot_summary

        feeder = mock_account.robots[4]
        feeder.last_feeding = {
            "timestamp": datetime(2024, 1, 1, 12, 0, 0),
            "amount": 1.5,
            "name": "Morning",
        }
        summary = format_robot_summary(feeder)
        # Must not raise TypeError
        result = json.dumps(summary)
        loaded = json.loads(result)
        assert loaded["last_feeding"]["timestamp"] == "2024-01-01T12:00:00"
        assert loaded["last_feeding"]["amount"] == 1.5
        assert loaded["last_feeding"]["name"] == "Morning"

    def test_last_feeding_none_is_json_serializable(
        self, mock_account: MagicMock
    ) -> None:
        """format_robot_summary serializes last_feeding=None to null."""
        import json

        from pylitterbot.mcp.helpers import format_robot_summary

        feeder = mock_account.robots[4]
        feeder.last_feeding = None
        summary = format_robot_summary(feeder)
        result = json.dumps(summary)
        loaded = json.loads(result)
        assert loaded["last_feeding"] is None


class TestFormatPetSummary:
    """Tests for format_pet_summary."""

    def test_formats_pet(self, mock_pet: MagicMock) -> None:
        """format_pet_summary returns expected fields."""
        from pylitterbot.mcp.helpers import format_pet_summary

        summary = format_pet_summary(mock_pet)
        assert summary["name"] == "Luna"
        assert summary["id"] == "pet-luna-id"
        assert summary["weight"] == 10.5
        assert summary["is_active"] is True
