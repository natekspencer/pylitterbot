"""Tests for MCP activity tools."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import pytest

from pylitterbot import Account, FeederRobot, LitterRobot4
from pylitterbot.activity import Activity, Insight
from pylitterbot.enums import LitterBoxStatus
from pylitterbot.robot.litterrobot5 import LitterRobot5


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

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("bad_limit", [0, -1, 501, 10_000_000])
    async def test_rejects_out_of_range_limit(
        self, mock_account: MagicMock, bad_limit: int
    ) -> None:
        """get_activity_history raises ValueError for limit outside [1, 500]."""
        from pylitterbot.mcp.tools.activity import get_activity_history

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="limit must be between 1 and 500"),
        ):
            await get_activity_history(robot="Kitchen", limit=bad_limit)
        mock_account.robots[0].get_activity_history.assert_not_awaited()


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

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("bad_days", [0, -1, -30])
    async def test_rejects_non_positive_days(
        self, mock_account: MagicMock, bad_days: int
    ) -> None:
        """get_insight raises ValueError for days < 1."""
        from pylitterbot.mcp.tools.activity import get_insight

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="days must be >= 1"),
        ):
            await get_insight(robot="Kitchen", days=bad_days)
        mock_account.robots[0].get_insight.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_rejects_lr5(self) -> None:
        """get_insight raises ValueError for LR5 before calling get_insight on the robot."""
        from pylitterbot.mcp.tools.activity import get_insight

        account = MagicMock(spec=Account)
        lr5 = MagicMock(spec=LitterRobot5)
        lr5.name = "Laundry Room"
        lr5.id = "lr5-laundry-id"
        account.robots = [lr5]

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=account),
            pytest.raises(ValueError, match="not available"),
        ):
            await get_insight(robot="Laundry Room")

        lr5.get_insight.assert_not_awaited()


@pytest.fixture()
def mock_feeder_account() -> MagicMock:
    """Create a mock Account with a Feeder-Robot."""
    account = MagicMock(spec=Account)

    feeder = MagicMock(spec=FeederRobot)
    feeder.name = "Cat Feeder"
    feeder.id = "feeder-001"
    feeder.model = "Feeder-Robot"
    feeder.serial = "FR001"
    feeder.is_online = True
    feeder.power_status = "AC"

    feeder.get_food_dispensed_since.return_value = 2.5

    account.robots = [feeder]
    return account


@pytest.fixture()
def mock_feeder_account_autospec() -> MagicMock:
    """Create a mock Account with a Feeder-Robot using create_autospec.

    Using create_autospec ensures the mock binds to the real signature of
    FeederRobot, so sync methods remain sync and won't silently accept await.
    """
    account = MagicMock(spec=Account)

    feeder = create_autospec(FeederRobot, instance=True)
    feeder.name = "Cat Feeder"
    feeder.id = "feeder-001"
    feeder.get_food_dispensed_since.return_value = 2.5

    account.robots = [feeder]
    return account


class TestGetFoodDispensed:
    """Tests for the get_food_dispensed tool."""

    @pytest.mark.asyncio()
    async def test_returns_food_dispensed(self, mock_feeder_account: MagicMock) -> None:
        """get_food_dispensed returns cups dispensed and the time window."""
        from pylitterbot.mcp.tools.activity import get_food_dispensed

        with patch(
            "pylitterbot.mcp.helpers.get_account", return_value=mock_feeder_account
        ):
            result = await get_food_dispensed(robot="Cat Feeder", hours=24)
        assert result["cups_dispensed"] == 2.5
        assert result["hours"] == 24
        assert result["robot"] == "Cat Feeder"
        mock_feeder_account.robots[0].get_food_dispensed_since.assert_called_once()

    @pytest.mark.asyncio()
    async def test_get_food_dispensed_calls_sync_method_not_coroutine(
        self, mock_feeder_account_autospec: MagicMock
    ) -> None:
        """get_food_dispensed does not await get_food_dispensed_since (it is sync).

        Using create_autospec means get_food_dispensed_since retains its real
        sync signature. If the production code does `await resolved.get_food_dispensed_since(...)`,
        it will get back a MagicMock (the return value of the sync call) and try
        to iterate it as a coroutine, raising TypeError. This test catches that bug.
        """
        from pylitterbot.mcp.tools.activity import get_food_dispensed

        with patch(
            "pylitterbot.mcp.helpers.get_account",
            return_value=mock_feeder_account_autospec,
        ):
            result = await get_food_dispensed(robot="Cat Feeder", hours=24)
        assert result["cups_dispensed"] == 2.5
        assert result["robot"] == "Cat Feeder"
        # The method must have been called (not awaited) exactly once
        mock_feeder_account_autospec.robots[
            0
        ].get_food_dispensed_since.assert_called_once()

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("bad_hours", [0, -1, -24])
    async def test_rejects_non_positive_hours(
        self, mock_feeder_account: MagicMock, bad_hours: int
    ) -> None:
        """get_food_dispensed raises ValueError for hours < 1."""
        from pylitterbot.mcp.tools.activity import get_food_dispensed

        with (
            patch(
                "pylitterbot.mcp.helpers.get_account",
                return_value=mock_feeder_account,
            ),
            pytest.raises(ValueError, match="hours must be >= 1"),
        ):
            await get_food_dispensed(robot="Cat Feeder", hours=bad_hours)
        mock_feeder_account.robots[0].get_food_dispensed_since.assert_not_called()

    @pytest.mark.asyncio()
    async def test_rejects_non_feeder(self, mock_account: MagicMock) -> None:
        """get_food_dispensed raises ValueError for non-Feeder robots."""
        from pylitterbot.mcp.tools.activity import get_food_dispensed

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            pytest.raises(ValueError, match="is not a Feeder-Robot"),
        ):
            await get_food_dispensed(robot="Kitchen", hours=24)
