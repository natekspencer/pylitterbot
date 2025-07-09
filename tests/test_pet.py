"""Test pet module."""

from datetime import date, datetime, timezone

import pytest
from aioresponses import aioresponses

from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.pet import (
    PET_PROFILE_ENDPOINT,
    Pet,
    PetDiet,
    PetEnvironment,
    PetGender,
    PetType,
)

from .common import PET_DATA, PET_ID, get_pet

pytestmark = pytest.mark.asyncio


async def test_pet_setup(mock_aioresponse: aioresponses) -> None:
    """Tests that pet setup is successful and parses as expected."""
    pet = await get_pet()
    assert pet.id == PET_ID
    assert pet.name == "Cat"
    assert pet.pet_type == PetType.CAT
    assert pet.gender == PetGender.FEMALE
    assert pet.estimated_weight == 8.5
    assert pet.last_weight_reading == 8.6
    assert pet.weight == 8.6
    assert pet.breeds == ["sphynx"]
    assert pet.age == 0
    assert pet.birthday == date(2016, 7, 2)
    assert pet.adoption_date is None
    assert pet.diet == PetDiet.BOTH
    assert pet.environment_type == PetEnvironment.INDOOR
    assert pet.health_concerns == []
    assert pet.image_url is None
    assert pet.is_active
    assert pet.is_fixed
    assert pet.is_healthy
    assert pet.pet_tag_id is None
    assert pet.weight_id_feature_enabled
    assert len(pet.weight_history) == 2
    assert pet.weight_history[0].timestamp == datetime(
        2024, 4, 17, 12, 35, 42, tzinfo=timezone.utc
    )
    assert pet.weight_history[0].weight == 8.68
    assert pet.get_visits_since(datetime(2024, 4, 17, 9, tzinfo=timezone.utc)) == 1


async def test_pet_with_unexpected_values(
    mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests expected error logs for unexpected values."""
    pet = await get_pet()
    pet._data |= {
        "diet": "oops",
        "environmentType": "oops",
        "gender": "oops",
        "type": "oops",
    }
    assert pet.diet is None
    assert 'Unknown diet "oops"' in caplog.messages
    assert pet.environment_type is None
    assert 'Unknown environment type "oops"' in caplog.messages
    assert pet.gender is None
    assert 'Unknown gender "oops"' in caplog.messages
    assert pet.pet_type is None
    assert 'Unknown pet type "oops"' in caplog.messages


async def test_pet_weight_history(mock_aioresponse: aioresponses) -> None:
    """Tests expected error logs for unexpected values."""
    pet = await get_pet()
    mock_aioresponse.post(
        PET_PROFILE_ENDPOINT,
        payload={
            "data": {
                "getWeightHistoryByPetId": [
                    {"timestamp": "2024-04-17T18:30:12.000Z", "weight": 8.6},
                    {"timestamp": "2024-04-17T12:35:42.000Z", "weight": 8.5},
                ]
            }
        },
    )
    weight_history = await pet.fetch_weight_history()
    assert len(weight_history) == 2
    assert str(weight_history[0]) == "2024-04-17T18:30:12+00:00: 8.6 lbs"
    assert pet.get_visits_since(datetime(2024, 4, 17, 13, tzinfo=timezone.utc)) == 1

    with pytest.raises(InvalidCommandException):
        await pet.fetch_weight_history(-1)

    mock_aioresponse.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getWeightHistoryByPetId": []}},
    )
    with pytest.raises(LitterRobotException):
        await pet.fetch_weight_history()


async def test_fetch_pet_by_id(mock_aioresponse: aioresponses) -> None:
    """Tests fetching a pet by id."""
    pet = await get_pet()

    mock_aioresponse.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getPetByPetId": PET_DATA}},
    )
    new_pet = await Pet.fetch_pet_by_id(pet._session, PET_ID)
    assert new_pet


async def test_pet_refresh(mock_aioresponse: aioresponses) -> None:
    """Tests refreshing a pet."""
    pet = await get_pet()

    new_data = {"lastWeightReading": 8.1}
    mock_aioresponse.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getPetByPetId": PET_DATA | new_data}},
    )
    await pet.refresh()
    assert pet.weight == 8.1
