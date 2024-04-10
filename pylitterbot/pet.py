from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum, unique
from io import BytesIO
from typing import Optional, cast

from aiohttp import ClientSession
from PIL import Image

from .event import Event
from .exceptions import InvalidCommandException, LitterRobotException
from .session import Session
from .utils import to_timestamp

PET_PROFILE_ENDPOINT = "https://pet-profile.iothings.site/graphql/"


@unique
class PetGender(Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


@unique
class PetDiet(Enum):
    WET = "WET"
    DRY = "DRY"
    BOTH = "BOTH"


class PetEnvironmentType(Enum):
    INDOOR = "INDOOR"
    OUTDOOR = "OUTDOOR"
    BOTH = "BOTH"


@dataclass
class WeightMeasurement:
    KG_TO_LBS = 2.20462262185

    timestamp: datetime | date
    weight: float

    def in_kg(self) -> float:
        return self.weight / self.KG_TO_LBS

    def in_lbs(self) -> float:
        return self.weight

    def __str__(self) -> str:
        return f"{self.timestamp.isoformat()}: {self.weight} lbs"


class Pet(Event):
    @classmethod
    async def fetch_pets_for_user(cls, user_id: str, session: Session) -> list["Pet"]:
        query = """
            query GetPetsByUser($userId: String!) {
                getPetsByUser(userId: $userId ) {
                    petId
                    userId
                    name
                    type
                    gender
                    weight
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
                    isActive
                    petTagId
                    weightIdFeatureEnabled
                }
            }
        """
        vars = {"userId": user_id}

        res = await cls.query_graphql_api(session, PET_PROFILE_ENDPOINT, query, vars)

        pets_data = cast(dict, res).get("data", {}).get("getPetsByUser", {})

        return [cls(pet_data, session) for pet_data in pets_data]

    @classmethod
    async def fetch_pet_with_id(
        cls, pet_id: str, session: Session, fetch_weight_history=True
    ) -> "Pet":
        query = """
            query GetPetByPetId($petId: String!) {
                getPetByPetId(petId: $petId ) {
                    petId
                    userId
                    name
                    type
                    gender
                    weight
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
                    isActive
                    petTagId
                    weightIdFeatureEnabled
                }
            }
        """
        vars = {"petId": pet_id}

        res = await cls.query_graphql_api(session, PET_PROFILE_ENDPOINT, query, vars)

        pet_data = cast(dict, res).get("data", {}).get("getPetByPetId", {})

        pet = cls(pet_data, session)

        return pet

    def __init__(self, data: dict, session: Session, fetch_image: bool = False) -> None:
        super().__init__()
        self._data: dict = data
        self._image: Optional[Image.Image] = None
        self._session: Session = session

    @property
    def id(self) -> Optional[str]:
        return self._data.get("petId")

    @property
    def name(self) -> Optional[str]:
        return self._data.get("name")

    @property
    def animal_type(self) -> Optional[str]:
        return self._data.get("type")

    @property
    def gender(self) -> Optional[PetGender]:
        gender_str = self._data.get("gender")
        return PetGender(gender_str) if gender_str else None

    @property
    def manually_recorded_weight(self) -> Optional[float]:
        return self._data.get("weight")

    @property
    def last_weight_reading(self) -> Optional[float]:
        return self._data.get("lastWeightReading")

    @property
    def weight(self) -> Optional[float]:
        return self.last_weight_reading or self.manually_recorded_weight

    @property
    def breeds(self) -> Optional[list[str]]:
        return self._data.get("breeds")

    @property
    def age(self) -> Optional[int]:
        age = self._data.get("age")
        return int(age) if age is not None else None

    @property
    def birthday(self) -> Optional[date]:
        birthday_str = self._data.get("birthday")
        return datetime.fromisoformat(birthday_str).date() if birthday_str else None

    @property
    def adoption_date(self) -> Optional[date]:
        adoption_date_str = self._data.get("adoptionDate")
        return (
            datetime.fromisoformat(adoption_date_str).date()
            if adoption_date_str
            else None
        )

    @property
    def image(self) -> Optional[Image.Image]:
        return self._image

    @property
    def diet(self) -> Optional[PetDiet]:
        diet_str = self._data.get("diet")
        return PetDiet(diet_str) if diet_str else None

    @property
    def neutered(self) -> Optional[bool]:
        return self._data.get("fixed")

    @property
    def environment_type(self) -> Optional[PetEnvironmentType]:
        env_type_str = self._data.get("environmentType")
        return PetEnvironmentType(env_type_str) if env_type_str else None

    @property
    def health_concerns(self) -> Optional[list[str]]:
        return self._data.get("healthConcerns")

    @property
    def is_active(self) -> Optional[bool]:
        return self._data.get("isActive", False)

    @property
    def pet_tag_id(self) -> Optional[str]:
        return self._data.get("petTagID")

    @property
    def weighing_feature_enabled(self) -> bool:
        return self._data.get("weightIdFeatureEnabled", False)

    async def fetch_image(self) -> Optional[Image.Image]:
        img_url = self._data.get("s3ImageURL")
        if not img_url:
            return None

        async with self._session.websession.get(img_url) as res:
            if res.status == 200:
                self._image = Image.open(BytesIO(await res.read()), formats=["jpeg"])
                return self._image
            elif res.status == 403 and "Request has expired" in await res.text():
                pass
                # Access denied, possibly due to expired request
                # "<?xml version="1.0" encoding="UTF-8"?><Error><Code>AccessDenied</Code><Message>Request has expired</Message><X-Amz-Expires>3600</X-Amz-Expires><Expires>2023-12-19T05:07:47Z</Expires><ServerTime>2023-12-19T18:45:49Z</ServerTime><RequestId>AH6DJ93C53S21WNS</RequestId><HostId>74sFJR/IgOHg0yih5GXIR8pjK30D79IMRHBFNe/tRAY3jGvmP+cGKJPXJrGRS1ZGW690gym2AMI=</HostId></Error>"

    async def fetch_weight_history(self, limit: int = 50) -> list[WeightMeasurement]:
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
        vars = {"petId": self.id, "limit": limit}

        res = await self.query_graphql_api(
            self._session, PET_PROFILE_ENDPOINT, query, vars
        )

        weight_data = cast(dict, res).get("data", {}).get("getWeightHistoryByPetId", {})

        if not weight_data:
            raise LitterRobotException("Weight history could not be retrieved.")

        return [
            WeightMeasurement(to_timestamp(entry["timestamp"]), entry["weight"])
            for entry in weight_data
            if entry["timestamp"]
        ]

    @staticmethod
    async def query_graphql_api(session, endpoint, query, variables):
        return await session.post(
            endpoint, json={"query": query, "variables": variables}
        )
