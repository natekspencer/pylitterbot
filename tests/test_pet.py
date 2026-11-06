"""Test pet module."""

import logging
import re
from datetime import date, datetime, timezone

import pytest
from aiointercept import aiointercept

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


async def test_pet_setup(mock_aiointercept: aiointercept) -> None:
    """Tests that pet setup is successful and parses as expected."""
    pet = await get_pet()
    assert pet.id == PET_ID
    assert pet.name == "Cat"
    assert pet.pet_type == PetType.CAT
    assert pet.gender == PetGender.FEMALE
    assert pet.estimated_weight == 8.5
    assert pet.last_weight_reading == 8.6
    assert pet.weight == 8.6
    assert pet.breed == "Sphynx"
    assert pet.breeds == ["sphynx"]
    assert pet.age == 0
    assert pet.birthday == date(2016, 7, 2)
    assert pet.adoption_date is None
    assert pet.deceased_date is None
    assert pet.diet == PetDiet.BOTH
    assert pet.environment_type == PetEnvironment.INDOOR
    assert pet.health_concerns == []
    assert pet.image_url == "s3ImageURL"
    query = list(mock_aiointercept.requests.items())[-1][-1][-1].kwargs["json"]["query"]
    assert re.search(r"profileImage\s*{[^}]*s3ImageURL", query)
    assert pet.is_active
    assert not pet.is_deceased
    assert pet.is_fixed
    assert pet.is_healthy
    assert pet.personality == []
    assert re.search(r"\bpersonality\b", query)
    assert re.search(r"\bisDeceased\b", query)
    assert re.search(r"\bdateOfDeath\b", query)
    assert pet.pet_tag_id is None
    assert pet.weight_id_feature_enabled
    assert len(pet.weight_history) == 2
    assert pet.weight_history[0].timestamp == datetime(
        2024, 4, 17, 12, 35, 42, tzinfo=timezone.utc
    )
    assert pet.weight_history[0].weight == 8.68
    assert pet.get_visits_since(datetime(2024, 4, 17, 9, tzinfo=timezone.utc)) == 1


@pytest.mark.parametrize(
    "traits,personality",
    [
        (None, []),
        ([], []),
        (["AFFECTIONATE"], ["affectionate"]),
        (["FRIENDLY", "LAID_BACK"], ["friendly with other pets", "laid-back"]),
        (["PLAYFUL", None, "NEW_TRAIT"], ["playful", "NEW_TRAIT"]),
    ],
)
async def test_pet_personality(
    mock_aiointercept: aiointercept,
    traits: list[str | None] | None,
    personality: list[str],
) -> None:
    """Tests that personality traits are readable and tolerate unknown values."""
    pet = await get_pet()
    pet._data["personality"] = traits
    assert pet.personality == personality


@pytest.mark.parametrize(
    "is_deceased,date_of_death,deceased,deceased_date",
    [
        (None, None, False, None),
        (False, None, False, None),
        (True, None, True, None),
        (True, "2024-03-01", True, date(2024, 3, 1)),
        (True, "2024-03-01T12:00:00.000Z", True, date(2024, 3, 1)),
    ],
)
async def test_pet_deceased(
    mock_aiointercept: aiointercept,
    is_deceased: bool | None,
    date_of_death: str | None,
    deceased: bool,
    deceased_date: date | None,
) -> None:
    """Tests the deceased status and date."""
    pet = await get_pet()
    pet._data |= {"isDeceased": is_deceased, "dateOfDeath": date_of_death}
    assert pet.is_deceased is deceased
    assert pet.deceased_date == deceased_date


@pytest.mark.parametrize(
    "breeds,breed",
    [
        (["sphynx"], "Sphynx"),
        (["british_shorthair"], "British Shorthair"),
        (["british_shorthair", "siamese"], "Mixed-breed"),
        (["british_shorthair", "siamese", "other"], "Mixed-breed"),
        ([], "Unknown"),
        (None, "Unknown"),
    ],
)
async def test_pet_breeds(
    mock_aiointercept: aiointercept,
    caplog: pytest.LogCaptureFixture,
    breeds: list[str] | None,
    breed: str,
) -> None:
    """Tests expected pet breed values."""
    pet = await get_pet()

    pet._data |= {"breeds": breeds}
    assert pet.breeds == breeds
    assert pet.breed == breed


async def test_pet_without_profile_image(mock_aiointercept: aiointercept) -> None:
    """Tests that a pet with no profile image has no image url."""
    pet = await get_pet()
    pet._data["profileImage"] = None
    assert pet.image_url is None


async def test_pet_update_does_not_log_profile_image(
    mock_aiointercept: aiointercept, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that profile image values are kept out of the debug update log."""
    pet = await get_pet()
    profile_image = {"imagePath": "newPath", "s3ImageURL": "newUrl"}
    with caplog.at_level(logging.DEBUG, logger="pylitterbot.pet"):
        pet._update_data({"name": "New name", "profileImage": profile_image}, True)

    assert "New name" in caplog.text
    assert "newPath" not in caplog.text
    assert "newUrl" not in caplog.text
    assert pet.image_url == "newUrl"


async def test_pet_with_unexpected_values(
    mock_aiointercept: aiointercept, caplog: pytest.LogCaptureFixture
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


async def test_pet_weight_history(mock_aiointercept: aiointercept) -> None:
    """Tests expected error logs for unexpected values."""
    pet = await get_pet()
    mock_aiointercept.post(
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

    mock_aiointercept.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getWeightHistoryByPetId": []}},
    )
    weight_history = await pet.fetch_weight_history()
    assert len(weight_history) == 0


async def test_fetch_pet_by_id(mock_aiointercept: aiointercept) -> None:
    """Tests fetching a pet by id."""
    pet = await get_pet()

    mock_aiointercept.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getPetByPetId": PET_DATA}},
    )
    new_pet = await Pet.fetch_pet_by_id(pet._session, PET_ID)
    assert new_pet


async def test_pet_refresh(mock_aiointercept: aiointercept) -> None:
    """Tests refreshing a pet."""
    pet = await get_pet()

    new_data = {"lastWeightReading": 8.1}
    mock_aiointercept.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": {"getPetByPetId": PET_DATA | new_data}},
    )
    await pet.refresh()
    assert pet.weight == 8.1


async def test_pet_refresh_no_data(mock_aiointercept: aiointercept) -> None:
    """Tests refreshing a pet when data returned is null."""
    pet = await get_pet()

    mock_aiointercept.post(
        PET_PROFILE_ENDPOINT,
        payload={"data": None},
    )
    await pet.refresh()
    assert pet.weight == 8.6
