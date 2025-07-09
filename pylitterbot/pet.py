"""Pet profiles."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum, unique
from typing import Any, cast

from deepdiff import DeepDiff

from .event import EVENT_UPDATE, Event
from .exceptions import InvalidCommandException, LitterRobotException
from .session import Session
from .utils import to_timestamp

_LOGGER = logging.getLogger(__name__)

PET_PROFILE_ENDPOINT = "https://pet-profile.iothings.site/graphql/"

PET_MODEL = """
{
    petId
    userId
    createdAt
    name
    type
    gender
    weight
    weightLastUpdated
    lastWeightReading
    breeds
    age
    birthday
    adoptionDate
    s3ImageURL
    diet
    isFixed
    environmentType
    healthConcerns
    isHealthy
    isActive
    whiskerProducts
    petTagId
    weightIdFeatureEnabled
    weightHistory {
        weight
        timestamp
    }
    weightHistoryErrorType
}
"""


@unique
class PetDiet(Enum):
    """Pet diet."""

    WET = "WET_FOOD"
    DRY = "DRY_FOOD"
    BOTH = "BOTH"

    def __str__(self) -> str:
        """Return str(self)."""
        return "wet/dry" if self == PetDiet.BOTH else self.name.lower()


@unique
class PetEnvironment(Enum):
    """Pet environment."""

    INDOOR = "INDOOR"
    OUTDOOR = "OUTDOOR"
    BOTH = "BOTH"

    def __str__(self) -> str:
        """Return str(self)."""
        return "indoor/outdoor" if self == PetEnvironment.BOTH else self.name.lower()


@unique
class PetGender(Enum):
    """Pet gender."""

    FEMALE = "FEMALE"
    MALE = "MALE"

    def __str__(self) -> str:
        """Return str(self)."""
        return self.name.lower()


@unique
class PetType(Enum):
    """Pet type."""

    CAT = "CAT"
    DOG = "DOG"

    def __str__(self) -> str:
        """Return str(self)."""
        return self.name.lower()


@dataclass(frozen=True)
class WeightMeasurement:
    """Weight measurement."""

    timestamp: datetime
    weight: float

    def __str__(self) -> str:
        """Return self(str)."""
        return f"{self.timestamp.isoformat()}: {self.weight} lbs"


def parse_weight_history(
    weight_data: list[dict[str, Any]] | None,
) -> list[WeightMeasurement]:
    """Parse weight history from a list."""
    if not weight_data:
        return []
    return [
        WeightMeasurement(
            cast(datetime, to_timestamp(entry["timestamp"])), entry["weight"]
        )
        for entry in weight_data
        if entry["timestamp"]
    ]


class Pet(Event):
    """Pet profile."""

    def __init__(self, data: dict, session: Session) -> None:
        """Initialize a pet profile."""
        super().__init__()
        self._data: dict = data
        self._session: Session = session
        self._weight_history: list[WeightMeasurement] = []
        if weight_data := data.get("weightHistory"):
            self._weight_history = parse_weight_history(weight_data)

    def __str__(self) -> str:
        """Return str(self)."""
        return f"Name: {self.name}, Gender: {self.gender}, Type: {self.pet_type}, Breed: {self.breeds}, id: {self.id}"

    @property
    def id(self) -> str:
        """Return the id of the pet."""
        return cast(str, self._data.get("petId"))

    @property
    def name(self) -> str:
        """Return the name of the pet."""
        return cast(str, self._data.get("name"))

    @property
    def pet_type(self) -> PetType | None:
        """Return the type of pet."""
        if (pet_type := self._data.get("type")) not in PetType.__members__:
            _LOGGER.error('Unknown pet type "%s"', pet_type)
            return None
        return PetType(pet_type)

    @property
    def gender(self) -> PetGender | None:
        """Return the gender."""
        if (gender := self._data.get("gender")) not in PetGender.__members__:
            _LOGGER.error('Unknown gender "%s"', gender)
            return None
        return PetGender(gender)

    @property
    def estimated_weight(self) -> float:
        """Return the estimated weight in pounds (lbs)."""
        return cast(float, self._data.get("weight"))

    @property
    def last_weight_reading(self) -> float | None:
        """Return the last weight reading in pounds (lbs), if any."""
        return self._data.get("lastWeightReading")

    @property
    def weight(self) -> float:
        """Return the weight in pounds (lbs)."""
        return self.last_weight_reading or self.estimated_weight

    @property
    def breeds(self) -> list[str] | None:
        """Return the breeds, if known."""
        return self._data.get("breeds")

    @property
    def age(self) -> int | None:
        """Return the age, if known."""
        return self._data.get("age")

    @property
    def birthday(self) -> date | None:
        """Return the birthday, if known."""
        birthday_str = self._data.get("birthday")
        return datetime.fromisoformat(birthday_str).date() if birthday_str else None

    @property
    def adoption_date(self) -> date | None:
        """Return the adoption date, if known."""
        adoption_date_str = self._data.get("adoptionDate")
        return (
            datetime.fromisoformat(adoption_date_str).date()
            if adoption_date_str
            else None
        )

    @property
    def diet(self) -> PetDiet | None:
        """Return the diet, if any."""
        if (diet := self._data.get("diet")) not in PetDiet.__members__:
            _LOGGER.error('Unknown diet "%s"', diet)
            return None
        return PetDiet(diet)

    @property
    def environment_type(self) -> PetEnvironment | None:
        """Return the environment type, if any."""
        if (
            environment := self._data.get("environmentType")
        ) not in PetEnvironment.__members__:
            _LOGGER.error('Unknown environment type "%s"', environment)
            return None
        return PetEnvironment(environment)

    @property
    def health_concerns(self) -> list[str] | None:
        """Return a list of health concerns, if any."""
        return self._data.get("healthConcerns")

    @property
    def image_url(self) -> str | None:
        """Return image url, if any."""
        return self._data.get("s3ImageURL")

    @property
    def is_active(self) -> bool | None:
        """Return if the pet profile is active."""
        return cast(bool, self._data.get("isActive", False))

    @property
    def is_fixed(self) -> bool | None:
        """Return `True` if the pet is fixed."""
        return cast(bool, self._data.get("isFixed", False))

    @property
    def is_healthy(self) -> bool | None:
        """Return `True` if the pet is healthy."""
        return cast(bool, self._data.get("isHealthy", False))

    @property
    def pet_tag_id(self) -> str | None:
        """Return the pet tag id, if any."""
        return self._data.get("petTagID")

    @property
    def weight_id_feature_enabled(self) -> bool:
        """Return `True` if the weight id feature is enabled."""
        return cast(bool, self._data.get("weightIdFeatureEnabled", False))

    @property
    def weight_history(self) -> list[WeightMeasurement]:
        """Return the weight history for the pet."""
        return self._weight_history

    def get_visits_since(self, start: datetime) -> int:
        """Return the number of visits (recorded via weight history) since the given datetime."""
        return sum(entry.timestamp >= start for entry in self.weight_history)

    def _update_data(self, data: dict, partial: bool = False) -> None:
        """Save the pet info from a data dictionary."""
        if diff := DeepDiff(
            self._data,
            {**self._data, **data} if partial else data,
            ignore_order=True,
            report_repetition=True,
            verbose_level=2,
        ):
            _LOGGER.debug("%s updated: %s", self.name, diff)

        if weight_data := data.get("weightHistory"):
            self._weight_history = parse_weight_history(weight_data)
        self._data.update(data)
        self.emit(EVENT_UPDATE)

    async def fetch_weight_history(self, limit: int = 50) -> list[WeightMeasurement]:
        """Fetch a pet's weight history."""
        weight_data = await self.query_weight_history(self._session, self.id, limit)
        self._weight_history = parse_weight_history(weight_data)
        return self._weight_history

    async def refresh(self) -> None:
        """Refresh the data for the pet."""
        data = await self.query_by_id(self._session, self.id)
        self._update_data(data)

    @classmethod
    async def fetch_pets_for_user(cls, session: Session, user_id: str) -> list[Pet]:
        """Fetch pets for a user."""
        pets_data = await cls.query_by_user(session, user_id)
        return [cls(pet_data, session) for pet_data in pets_data]

    @classmethod
    async def fetch_pet_by_id(cls, session: Session, pet_id: str) -> Pet:
        """Fetch a pet by id."""
        pet_data = await cls.query_by_id(session, pet_id)
        pet = cls(pet_data, session)
        return pet

    @staticmethod
    async def query_by_user(session: Session, user_id: str) -> list[dict]:
        """Query pets for a user."""
        query = f"""
            query GetPetsByUser($userId: String!) {{
                getPetsByUser(userId: $userId ) {PET_MODEL}
            }}
        """
        vars = {"userId": user_id}

        res = cast(dict, await Pet.query_graphql_api(session, query, vars))
        return cast(list[dict], res.get("data", {}).get("getPetsByUser", []))

    @staticmethod
    async def query_by_id(session: Session, pet_id: str) -> dict:
        """Query a pet by id."""
        query = f"""
            query GetPetByPetId($petId: String!) {{
                getPetByPetId(petId: $petId ) {PET_MODEL}
            }}
        """
        vars = {"petId": pet_id}

        res = cast(dict, await Pet.query_graphql_api(session, query, vars))
        return cast(dict, res.get("data", {}).get("getPetByPetId", {}))

    @staticmethod
    async def query_weight_history(
        session: Session, pet_id: str, limit: int = 50
    ) -> list[dict]:
        """Query a pet's weight history."""
        if limit < 1:
            raise InvalidCommandException(
                f"Invalid range for parameter limit, value: {limit}, valid range: 1-inf"
            )

        query = """
            query GetWeightHistoryByPetId($petId: String!, $limit: Int) {
                getWeightHistoryByPetId(petId: $petId, limit: $limit) {
                    weight
                    timestamp
                }
            }
            """
        vars = {"petId": pet_id, "limit": limit}

        res = cast(dict, await Pet.query_graphql_api(session, query, vars))

        if not (weight_data := res.get("data", {}).get("getWeightHistoryByPetId", [])):
            raise LitterRobotException("Weight history could not be retrieved.")

        return cast(list[dict], weight_data)

    @staticmethod
    async def query_graphql_api(
        session: Session,
        query: str,
        variables: dict | None = None,
        endpoint: str = PET_PROFILE_ENDPOINT,
    ) -> dict | list[dict] | None:
        """Query GraphQL API."""
        return await session.post(
            endpoint, json={"query": query, "variables": variables}
        )
