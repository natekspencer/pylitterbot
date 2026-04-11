"""Tests for MCP compound tools."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot4, Pet
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

    @pytest.mark.asyncio()
    async def test_syncs_sleep_time_when_both_enabled_but_times_differ(
        self, mock_account: MagicMock
    ) -> None:
        """Sync sleep_mode_start_time differences even when both are enabled.

        Regression for a bug where the sleep-mode branch only fired on an
        enabled-flag mismatch, so two robots that were both enabled but had
        different sleep start times stayed out of sync.
        """
        from pylitterbot.mcp.tools.compound import sync_settings

        kitchen = mock_account.robots[0]
        bedroom = mock_account.robots[1]

        # Both enabled, but different start times.
        kitchen.sleep_mode_enabled = True
        bedroom.sleep_mode_enabled = True
        kitchen.sleep_mode_start_time = datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)
        bedroom.sleep_mode_start_time = datetime(
            2026, 1, 1, 23, 30, tzinfo=timezone.utc
        )

        with (
            patch(
                "pylitterbot.mcp.tools.compound.get_account",
                return_value=mock_account,
            ),
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
        ):
            result = await sync_settings(source_robot="Kitchen")

        bedroom.set_sleep_mode.assert_awaited_once_with(
            True, time(22, 0, tzinfo=timezone.utc)
        )
        bedroom_changes = result["targets"][0]["changes"]
        assert any("sleep_mode" in change for change in bedroom_changes)


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
        # Kitchen is 80% full, Bedroom is 20% full, so Kitchen is more urgent.
        assert result[0]["name"] == "Kitchen"
        assert "estimated_days_remaining" in result[0]

    @pytest.mark.asyncio()
    async def test_uses_drawer_level_not_lifetime_odometer(
        self, mock_account: MagicMock
    ) -> None:
        """cycles_remaining is derived from waste_drawer_level, not cycle_count.

        Regression: on LR4/LR5, cycle_count maps to odometerCleanCycles (a
        lifetime odometer). Subtracting it from cycle_capacity pins the
        forecast to 0 for any real-world robot that has done more cycles in
        its lifetime than the drawer capacity. The forecast must derive
        cycles_remaining from the DFI fill level instead.
        """
        from pylitterbot.mcp.tools.compound import maintenance_forecast

        # Bedroom: 20% full with cycle_capacity=30 should have ~24 cycles left,
        # but with a huge lifetime cycle_count (simulating a well-used robot)
        # the old code would compute max(0, 30 - 500) = 0.
        bedroom = mock_account.robots[1]
        bedroom.cycle_count = 500
        bedroom.cycle_capacity = 30
        bedroom.waste_drawer_level = 20.0

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await maintenance_forecast()

        bedroom_forecast = next(f for f in result if f["name"] == "Bedroom")
        # 30 * (1 - 0.20) = 24
        assert bedroom_forecast["cycles_remaining"] == 24


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


class TestSyncSettingsLR4SleepModeCrash:
    """Regression tests for C2-compound: LR4 sleep-mode sync crashing."""

    @pytest.mark.asyncio()
    async def test_sync_settings_completes_when_lr4_target_raises_on_sleep_mode(
        self, mock_account: MagicMock
    ) -> None:
        """sync_settings does not crash when an LR4 target raises NotImplementedError on set_sleep_mode.

        LR4 inherits the raising stub from the base LitterRobot class.
        The call must complete and report the target as skipped with a reason.
        """
        from pylitterbot.mcp.tools.compound import sync_settings

        kitchen = mock_account.robots[0]
        bedroom = mock_account.robots[1]

        # Source has sleep mode enabled; target differs so sync will attempt it.
        kitchen.sleep_mode_enabled = True
        kitchen.sleep_mode_start_time = datetime(2026, 1, 1, 22, 0, tzinfo=timezone.utc)
        bedroom.sleep_mode_enabled = False
        bedroom.sleep_mode_start_time = None

        # Simulate LR4 not overriding set_sleep_mode: it raises NotImplementedError.
        bedroom.set_sleep_mode = AsyncMock(
            side_effect=NotImplementedError("not supported on this model")
        )

        with (
            patch(
                "pylitterbot.mcp.tools.compound.get_account",
                return_value=mock_account,
            ),
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
        ):
            result = await sync_settings(source_robot="Kitchen")

        # The call must NOT raise — it must complete and report the robot as skipped.
        assert "skipped" in result
        skipped_names = [s["target"] for s in result["skipped"]]
        assert "Bedroom" in skipped_names
        skipped_entry = next(s for s in result["skipped"] if s["target"] == "Bedroom")
        assert "sleep_mode" in skipped_entry["skipped"].lower()


class TestSyncSettingsModelComparison:
    """Regression tests for M2: model string comparison filtering valid targets."""

    @pytest.mark.asyncio()
    async def test_sync_settings_includes_lr4_pro_targets_alongside_standard_lr4(
        self,
    ) -> None:
        """sync_settings treats all LitterRobot4 instances as same model regardless of model string.

        Firmware string drift (e.g. "Litter-Robot 4" vs "Litter-Robot 4 Pro")
        must not silently filter out valid same-class targets.
        """
        from pylitterbot.mcp.tools.compound import sync_settings

        source = _make_lr4("Source", "lr4-source")
        source.model = "Litter-Robot 4"
        source.clean_cycle_wait_time_minutes = 7

        target_standard = _make_lr4("Standard", "lr4-standard")
        target_standard.model = "Litter-Robot 4"
        target_standard.clean_cycle_wait_time_minutes = 3  # differs -> triggers sync

        target_pro = _make_lr4("Pro", "lr4-pro")
        target_pro.model = "Litter-Robot 4 Pro"
        target_pro.clean_cycle_wait_time_minutes = 3  # differs -> triggers sync

        account = MagicMock()
        account.refresh_robots = AsyncMock()
        account.robots = [source, target_standard, target_pro]

        with (
            patch(
                "pylitterbot.mcp.tools.compound.get_account", return_value=account
            ),
            patch("pylitterbot.mcp.helpers.get_account", return_value=account),
        ):
            result = await sync_settings(source_robot="Source")

        target_names = [t["name"] for t in result["targets"]]
        assert "Standard" in target_names, "Standard LR4 should be synced"
        assert "Pro" in target_names, "LR4 Pro should be synced (same Python class)"


class TestHouseholdDigestDefensiveAlerts:
    """Regression tests for M3: household_digest alerts resilience."""

    @pytest.mark.asyncio()
    async def test_digest_completes_when_status_text_raises(
        self, mock_account: MagicMock
    ) -> None:
        """household_digest does not crash when robot.status.text raises AttributeError.

        The alerts block accesses robot.status.text outside the get_insight
        try/except. A misbehaving status.text must be handled defensively so
        the whole digest does not tank.
        """
        from pylitterbot.mcp.tools.compound import household_digest

        kitchen = mock_account.robots[0]
        # Make kitchen need attention (is_online=False triggers _needs_attention).
        kitchen.is_online = False

        # Create a real object whose .text property raises AttributeError.
        class BrokenStatus:
            @property
            def text(self):
                raise AttributeError("no text attribute")

        kitchen.status = BrokenStatus()

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            # Must not raise — should return a partial result.
            result = await household_digest(days=7)

        assert "robots" in result
        assert "alerts" in result

    @pytest.mark.asyncio()
    async def test_digest_reports_not_implemented_error_from_lr5_insight(
        self, mock_account: MagicMock
    ) -> None:
        """household_digest reports a model-specific message when get_insight raises NotImplementedError.

        LR5.get_insight always raises NotImplementedError. The error message must
        be distinct from the generic "Could not retrieve insight data" message that
        covers transient API failures.
        """
        from pylitterbot.mcp.tools.compound import household_digest

        kitchen = mock_account.robots[0]
        kitchen.get_insight = AsyncMock(
            side_effect=NotImplementedError("not supported on LR5")
        )

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await household_digest(days=7)

        kitchen_data = next(r for r in result["robots"] if r["name"] == "Kitchen")
        assert "error" in kitchen_data
        assert kitchen_data["error"] != "Could not retrieve insight data"
        assert "not supported" in kitchen_data["error"].lower()


class TestTroubleshootingReportLR5:
    """Regression tests for M4: troubleshooting_report excluding LR5."""

    @pytest.mark.asyncio()
    async def test_lr5_report_includes_firmware_and_motor_fault(self) -> None:
        """troubleshooting_report includes firmware, status_code, globe_motor_fault for LR5.

        Before the fix, LR5 passed isinstance(resolved, LitterRobot4) as False
        so it got an empty/minimal report with none of those fields.
        """
        from pylitterbot.mcp.tools.compound import troubleshooting_report
        from pylitterbot.robot.litterrobot5 import LitterRobot5

        lr5 = MagicMock(spec=LitterRobot5)
        lr5.name = "Upstairs"
        lr5.id = "lr5-upstairs"
        lr5.model = "Litter-Robot 5"
        lr5.serial = "LR5-001"
        lr5.is_online = True
        lr5.power_status = "AC"
        lr5.status = LitterBoxStatus.READY
        lr5.waste_drawer_level = 10.0
        lr5.cycle_count = 5
        lr5.cycle_capacity = 30
        lr5.is_waste_drawer_full = False
        lr5.is_sleeping = False
        lr5.clean_cycle_wait_time_minutes = 7
        lr5.night_light_mode_enabled = True
        lr5.panel_lock_enabled = False
        lr5.sleep_mode_enabled = False
        lr5.litter_level = 80.0
        lr5.pet_weight = 10.0
        lr5.firmware = "ESP: 2.0 / PIC: 3.0"
        globe_fault = MagicMock()
        globe_fault.name = "NONE"
        lr5.globe_motor_fault_status = globe_fault
        lr5.status_code = "RDY"
        lr5.refresh = AsyncMock()
        lr5.get_activity_history = AsyncMock(return_value=[])
        lr5.get_firmware_details = AsyncMock(return_value=None)

        account = MagicMock()
        account.refresh_robots = AsyncMock()
        account.robots = [lr5]

        with patch("pylitterbot.mcp.helpers.get_account", return_value=account):
            result = await troubleshooting_report(robot="Upstairs")

        assert "firmware" in result, "LR5 report should include firmware"
        assert "status_code" in result, "LR5 report should include status_code"
        assert (
            "globe_motor_fault" in result
        ), "LR5 report should include globe_motor_fault"
        # usb_fault is LR4-only, must NOT appear for LR5
        assert "usb_fault" not in result, "LR5 report must not include usb_fault"


class TestCleanAllReadyFalseReturn:
    """Regression tests for the clean_all_ready bool-return minor finding."""

    @pytest.mark.asyncio()
    async def test_robot_returning_false_from_start_cleaning_is_reported_skipped(
        self, mock_account: MagicMock
    ) -> None:
        """clean_all_ready reports a robot as skipped when start_cleaning returns False.

        A False return means a silent device-level failure; the tool must not
        report that robot as cleaned.
        """
        from pylitterbot.mcp.tools.compound import clean_all_ready

        bedroom = mock_account.robots[1]  # READY status
        bedroom.start_cleaning = AsyncMock(return_value=False)

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=mock_account
        ):
            result = await clean_all_ready()

        cleaned_names = [r["name"] for r in result["cleaned"]]
        skipped_names = [r["name"] for r in result["skipped"]]
        assert "Bedroom" not in cleaned_names, "Bedroom must not be in cleaned list"
        assert "Bedroom" in skipped_names, "Bedroom must be reported as skipped"
        bedroom_skip = next(s for s in result["skipped"] if s["name"] == "Bedroom")
        assert "false" in bedroom_skip["reason"].lower() or "failed" in bedroom_skip["reason"].lower()


class TestRobotComparisonLR4LifetimeOdometer:
    """Regression tests for the robot_comparison outlier detection minor finding."""

    @pytest.mark.asyncio()
    async def test_lr4_cycle_count_difference_not_flagged_as_outlier(self) -> None:
        """robot_comparison does not flag LR4 cycle_count differences as outliers.

        LR4/LR5 cycle_count is a lifetime odometer (odometerCleanCycles), not a
        per-drawer counter. Two robots at different stages of their lifecycle must
        not be flagged just because one has more lifetime cycles.
        """
        from pylitterbot.mcp.tools.compound import robot_comparison

        lr4_old = _make_lr4("Old", "lr4-old", cycle_count=2000)
        lr4_new = _make_lr4("New", "lr4-new", cycle_count=500)

        account = MagicMock()
        account.refresh_robots = AsyncMock()
        account.robots = [lr4_old, lr4_new]

        with patch(
            "pylitterbot.mcp.tools.compound.get_account", return_value=account
        ):
            result = await robot_comparison()

        lr4_group = next(
            (g for g in result["groups"] if "Litter-Robot 4" in g["model"]), None
        )
        assert lr4_group is not None
        outliers = lr4_group.get("outliers", [])
        cycle_outliers = [o for o in outliers if o.get("metric") == "cycle_count"]
        assert len(cycle_outliers) == 0, (
            "LR4 lifetime odometer differences must not be flagged as cycle_count outliers"
        )
