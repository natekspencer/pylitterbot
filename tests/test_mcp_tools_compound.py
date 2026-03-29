"""Tests for MCP compound tools."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot3, LitterRobot4, Pet
from pylitterbot.activity import Activity, Insight
from pylitterbot.enums import LitterBoxStatus, NightLightMode


def _make_lr4(
    name: str,
    robot_id: str,
    status: LitterBoxStatus = LitterBoxStatus.READY,
    waste_drawer_level: float = 30.0,
    cycle_count: int = 10,
    cycle_capacity: int = 30,
    is_waste_drawer_full: bool = False,
    is_online: bool = True,
    wait_time: int = 7,
    night_light_mode: NightLightMode = NightLightMode.AUTO,
    night_light_brightness: int = 50,
    panel_lock_enabled: bool = False,
    sleep_mode_enabled: bool = False,
    litter_level: float = 80.0,
    pet_weight: float = 10.0,
) -> MagicMock:
    """Create a mock LR4."""
    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = name
    lr4.id = robot_id
    lr4.model = "Litter-Robot 4"
    lr4.serial = f"LR4-{robot_id}"
    lr4.is_online = is_online
    lr4.power_status = "AC"
    lr4.status = status
    lr4.waste_drawer_level = waste_drawer_level
    lr4.cycle_count = cycle_count
    lr4.cycle_capacity = cycle_capacity
    lr4.is_waste_drawer_full = is_waste_drawer_full
    lr4.is_sleeping = False
    lr4.clean_cycle_wait_time_minutes = wait_time
    lr4.night_light_mode = night_light_mode
    lr4.night_light_brightness = night_light_brightness
    lr4.night_light_mode_enabled = night_light_mode != NightLightMode.OFF
    lr4.panel_lock_enabled = panel_lock_enabled
    lr4.sleep_mode_enabled = sleep_mode_enabled
    lr4.litter_level = litter_level
    lr4.pet_weight = pet_weight
    lr4.refresh = AsyncMock()
    lr4.start_cleaning = AsyncMock(return_value=True)
    lr4.set_wait_time = AsyncMock(return_value=True)
    lr4.set_night_light = AsyncMock(return_value=True)
    lr4.set_night_light_brightness = AsyncMock(return_value=True)
    lr4.set_night_light_mode = AsyncMock(return_value=True)
    lr4.set_panel_lockout = AsyncMock(return_value=True)
    lr4.set_sleep_mode = AsyncMock(return_value=True)
    lr4.get_activity_history = AsyncMock(return_value=[])
    lr4.get_insight = AsyncMock(
        return_value=Insight(
            total_cycles=30,
            average_cycles=1.5,
            cycle_history=[(date(2024, 1, i), 2) for i in range(1, 8)],
        )
    )
    lr4.get_firmware_details = AsyncMock(return_value=None)
    lr4.firmware = "ESP: 1.0 / PIC: 2.0 / TOF: 3.0"
    lr4.globe_motor_fault_status = MagicMock()
    lr4.globe_motor_fault_status.name = "NONE"
    lr4.usb_fault_status = MagicMock()
    lr4.usb_fault_status.name = "NONE"
    lr4.status_code = "RDY"
    return lr4


def _make_feeder(name: str, robot_id: str) -> MagicMock:
    """Create a mock FeederRobot."""
    feeder = MagicMock(spec=FeederRobot)
    feeder.name = name
    feeder.id = robot_id
    feeder.model = "Feeder-Robot"
    feeder.serial = f"FR-{robot_id}"
    feeder.is_online = True
    feeder.power_status = "AC"
    feeder.food_level = 70
    feeder.meal_insert_size = 0.25
    feeder.last_feeding = None
    feeder.refresh = AsyncMock()
    return feeder


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with two LR4s and a feeder."""
    account = MagicMock(spec=Account)
    account.refresh_robots = AsyncMock()
    account.load_pets = AsyncMock()

    lr4_kitchen = _make_lr4(
        "Kitchen",
        "lr4-kitchen",
        waste_drawer_level=80.0,
        cycle_count=25,
        is_waste_drawer_full=True,
        status=LitterBoxStatus.DRAWER_FULL,
    )
    lr4_bedroom = _make_lr4(
        "Bedroom", "lr4-bedroom", waste_drawer_level=20.0, cycle_count=5
    )
    feeder = _make_feeder("Feeder", "feeder-1")

    account.robots = [lr4_kitchen, lr4_bedroom, feeder]

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
    account.pets = [pet]

    return account


class TestFleetOverview:
    """Tests for fleet_overview."""

    @pytest.mark.asyncio()
    async def test_partitions_robots_by_attention_needed(
        self, mock_account: MagicMock
    ) -> None:
        """fleet_overview separates robots needing attention from healthy ones."""
        from pylitterbot.mcp.tools.compound import fleet_overview

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await fleet_overview()
        assert len(result["needs_attention"]) >= 1
        assert result["total_robots"] == 3
        attention_names = [r["name"] for r in result["needs_attention"]]
        assert "Kitchen" in attention_names

    @pytest.mark.asyncio()
    async def test_healthy_robots_in_healthy_list(
        self, mock_account: MagicMock
    ) -> None:
        """fleet_overview puts healthy robots in the healthy list."""
        from pylitterbot.mcp.tools.compound import fleet_overview

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await fleet_overview()
        healthy_names = [r["name"] for r in result["healthy"]]
        assert "Bedroom" in healthy_names


class TestCleanAllReady:
    """Tests for clean_all_ready."""

    @pytest.mark.asyncio()
    async def test_cleans_ready_robots_skips_others(
        self, mock_account: MagicMock
    ) -> None:
        """clean_all_ready starts cleaning on READY robots and skips non-ready."""
        from pylitterbot.mcp.tools.compound import clean_all_ready

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await clean_all_ready()
        # Bedroom is READY, Kitchen is DRAWER_FULL
        assert len(result["cleaned"]) >= 1
        assert len(result["skipped"]) >= 1
        cleaned_names = [r["name"] for r in result["cleaned"]]
        assert "Bedroom" in cleaned_names

    @pytest.mark.asyncio()
    async def test_skipped_includes_reason(self, mock_account: MagicMock) -> None:
        """clean_all_ready includes a reason for skipped robots."""
        from pylitterbot.mcp.tools.compound import clean_all_ready

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await clean_all_ready()
        skipped = result["skipped"]
        assert any("reason" in s for s in skipped)


class TestSyncSettings:
    """Tests for sync_settings."""

    @pytest.mark.asyncio()
    async def test_syncs_settings_from_source_to_targets(
        self, mock_account: MagicMock
    ) -> None:
        """sync_settings applies source settings to other same-type robots."""
        from pylitterbot.mcp.tools.compound import sync_settings

        # Make bedroom have different wait time
        mock_account.robots[1].clean_cycle_wait_time_minutes = 3

        with (
            patch(
                "pylitterbot.mcp.tools.compound.get_account",
                return_value=mock_account,
            ),
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
        ):
            result = await sync_settings(source_robot="Kitchen")
        assert result["source"] == "Kitchen"
        assert len(result["targets"]) >= 1
        assert result["targets"][0]["name"] == "Bedroom"


class TestMaintenanceForecast:
    """Tests for maintenance_forecast."""

    @pytest.mark.asyncio()
    async def test_returns_sorted_by_urgency(self, mock_account: MagicMock) -> None:
        """maintenance_forecast sorts robots by estimated days remaining."""
        from pylitterbot.mcp.tools.compound import maintenance_forecast

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await maintenance_forecast()
        assert len(result) >= 2
        # Kitchen has fewer cycles remaining (25/30) than Bedroom (5/30)
        assert result[0]["name"] == "Kitchen"
        assert "estimated_days_remaining" in result[0]


class TestHouseholdDigest:
    """Tests for household_digest."""

    @pytest.mark.asyncio()
    async def test_returns_aggregate_data(self, mock_account: MagicMock) -> None:
        """household_digest returns period, total_cycles, robots, and pets."""
        from pylitterbot.mcp.tools.compound import household_digest

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await household_digest(days=7)
        assert result["period_days"] == 7
        assert "total_cycles" in result
        assert "robots" in result
        assert "pets" in result


class TestTroubleshootingReport:
    """Tests for troubleshooting_report."""

    @pytest.mark.asyncio()
    async def test_gathers_diagnostic_data(self, mock_account: MagicMock) -> None:
        """troubleshooting_report includes status, activity, and firmware."""
        from pylitterbot.mcp.tools.compound import troubleshooting_report

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            result = await troubleshooting_report(robot="Kitchen")
        assert result["name"] == "Kitchen"
        assert "status" in result
        assert "recent_activity" in result
        assert "firmware" in result


class TestRobotComparison:
    """Tests for robot_comparison."""

    @pytest.mark.asyncio()
    async def test_groups_by_model_and_finds_inconsistencies(
        self, mock_account: MagicMock
    ) -> None:
        """robot_comparison groups robots and flags setting differences."""
        from pylitterbot.mcp.tools.compound import robot_comparison

        # Give them different wait times to create an inconsistency
        mock_account.robots[1].clean_cycle_wait_time_minutes = 3

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await robot_comparison()
        assert "groups" in result
        lr4_group = next(
            (g for g in result["groups"] if g["model"] == "Litter-Robot 4"), None
        )
        assert lr4_group is not None
        assert len(lr4_group["robots"]) == 2


class TestPetUsageReport:
    """Tests for pet_usage_report."""

    @pytest.mark.asyncio()
    async def test_returns_per_pet_data(self, mock_account: MagicMock) -> None:
        """pet_usage_report returns data organized by pet."""
        from pylitterbot.mcp.tools.compound import pet_usage_report

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await pet_usage_report()
        assert "pets" in result
        assert "robots" in result
