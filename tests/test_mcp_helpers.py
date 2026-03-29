"""Tests for MCP helpers: robot resolution and formatting."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot4, Pet
from pylitterbot.enums import LitterBoxStatus, NightLightMode


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
        "timestamp": "2024-01-01T12:00:00",
        "amount": 0.25,
        "name": "snack",
    }
    feeder.refresh = AsyncMock()

    account.robots = [lr4_kitchen, lr4_bedroom, feeder]
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

        feeder = mock_account.robots[2]
        summary = format_robot_summary(feeder)
        assert summary["name"] == "Feeder"
        assert summary["model"] == "Feeder-Robot"
        assert summary["food_level"] == 70
        assert summary["meal_insert_size"] == 0.25


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
