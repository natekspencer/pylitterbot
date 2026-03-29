"""Tests for MCP pet tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pylitterbot import Account, LitterRobot4, LitterRobot5, Pet
from pylitterbot.enums import LitterBoxStatus


@pytest.fixture()
def mock_account() -> MagicMock:
    """Create a mock Account with pets and robots."""
    account = MagicMock(spec=Account)
    account.load_pets = AsyncMock()

    pet_luna = MagicMock(spec=Pet)
    pet_luna.name = "Luna"
    pet_luna.id = "pet-luna-id"
    pet_luna.pet_type = MagicMock()
    pet_luna.pet_type.name = "CAT"
    pet_luna.gender = MagicMock()
    pet_luna.gender.name = "FEMALE"
    pet_luna.weight = 10.5
    pet_luna.breeds = ["Domestic Shorthair"]
    pet_luna.is_active = True

    pet_milo = MagicMock(spec=Pet)
    pet_milo.name = "Milo"
    pet_milo.id = "pet-milo-id"
    pet_milo.pet_type = MagicMock()
    pet_milo.pet_type.name = "CAT"
    pet_milo.gender = MagicMock()
    pet_milo.gender.name = "MALE"
    pet_milo.weight = 12.0
    pet_milo.breeds = ["Maine Coon"]
    pet_milo.is_active = True

    account.pets = [pet_luna, pet_milo]

    lr5 = MagicMock(spec=LitterRobot5)
    lr5.name = "Living Room"
    lr5.id = "lr5-living-id"
    lr5.model = "Litter-Robot 5"
    lr5.serial = "LR5L001"
    lr5.is_online = True
    lr5.power_status = "AC"
    lr5.status = LitterBoxStatus.READY
    lr5.reassign_pet_visit = AsyncMock(return_value={"eventId": "evt-123"})

    lr4 = MagicMock(spec=LitterRobot4)
    lr4.name = "Kitchen"
    lr4.id = "lr4-kitchen-id"
    lr4.model = "Litter-Robot 4"
    lr4.serial = "LR4K001"
    lr4.is_online = True
    lr4.power_status = "AC"
    lr4.status = LitterBoxStatus.READY

    account.robots = [lr5, lr4]
    return account


class TestGetPets:
    """Tests for the get_pets tool."""

    @pytest.mark.asyncio()
    async def test_returns_formatted_pet_list(self, mock_account: MagicMock) -> None:
        """get_pets returns a list of formatted pet summaries."""
        from pylitterbot.mcp.tools.pets import get_pets

        with patch("pylitterbot.mcp.tools.pets.get_account", return_value=mock_account):
            result = await get_pets()
        assert len(result) == 2
        assert result[0]["name"] == "Luna"
        assert result[1]["name"] == "Milo"

    @pytest.mark.asyncio()
    async def test_loads_pets_before_returning(self, mock_account: MagicMock) -> None:
        """get_pets calls load_pets on the account."""
        from pylitterbot.mcp.tools.pets import get_pets

        with patch("pylitterbot.mcp.tools.pets.get_account", return_value=mock_account):
            await get_pets()
        mock_account.load_pets.assert_awaited_once()


class TestReassignPetVisit:
    """Tests for the reassign_pet_visit tool."""

    @pytest.mark.asyncio()
    async def test_reassigns_visit_on_lr5(self, mock_account: MagicMock) -> None:
        """reassign_pet_visit calls reassign on LR5 with resolved pet IDs."""
        from pylitterbot.mcp.tools.pets import reassign_pet_visit

        with patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account):
            with patch(
                "pylitterbot.mcp.tools.pets.get_account", return_value=mock_account
            ):
                result = await reassign_pet_visit(
                    robot="Living Room",
                    event_id="evt-123",
                    from_pet="Luna",
                    to_pet="Milo",
                )
        lr5 = mock_account.robots[0]
        lr5.reassign_pet_visit.assert_awaited_once_with(
            "evt-123", from_pet_id="pet-luna-id", to_pet_id="pet-milo-id"
        )
        assert "reassigned" in result.lower()

    @pytest.mark.asyncio()
    async def test_rejects_non_lr5(self, mock_account: MagicMock) -> None:
        """reassign_pet_visit raises ValueError for non-LR5 robots."""
        from pylitterbot.mcp.tools.pets import reassign_pet_visit

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            patch(
                "pylitterbot.mcp.tools.pets.get_account", return_value=mock_account
            ),
            pytest.raises(ValueError, match="only supported on Litter-Robot 5"),
        ):
            await reassign_pet_visit(
                robot="Kitchen",
                event_id="evt-456",
                from_pet="Luna",
                to_pet="Milo",
            )

    @pytest.mark.asyncio()
    async def test_raises_for_unknown_pet(self, mock_account: MagicMock) -> None:
        """reassign_pet_visit raises ValueError for an unknown pet name."""
        from pylitterbot.mcp.tools.pets import reassign_pet_visit

        with (
            patch("pylitterbot.mcp.helpers.get_account", return_value=mock_account),
            patch(
                "pylitterbot.mcp.tools.pets.get_account", return_value=mock_account
            ),
            pytest.raises(ValueError, match="No pet found"),
        ):
            await reassign_pet_visit(
                robot="Living Room",
                event_id="evt-789",
                from_pet="Unknown Cat",
                to_pet="Milo",
            )
