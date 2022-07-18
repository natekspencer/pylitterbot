"""Account access and data handling for Litter-Robot endpoint."""
from __future__ import annotations

import logging

import jwt
from aiohttp import ClientResponseError, ClientSession

from .exceptions import LitterRobotException, LitterRobotLoginException
from .models import LITTER_ROBOT_4_MODEL
from .robot import (
    DEFAULT_ENDPOINT,
    DEFAULT_ENDPOINT_KEY,
    LITTER_ROBOT_ID,
    LR4_ENDPOINT,
    LitterRobot3,
    LitterRobot4,
    Robot,
)
from .session import OAuth2Session, urljoin
from .utils import decode

_LOGGER = logging.getLogger(__name__)


class Account:
    """Class with data and methods for interacting with a user's Litter-Robots."""

    def __init__(
        self, token: dict | None = None, websession: ClientSession | None = None
    ) -> None:
        """Initialize the account data."""
        self._session = OAuth2Session(token=token, websession=websession)
        self._session._custom_args[DEFAULT_ENDPOINT] = {
            "headers": {"x-api-key": decode(DEFAULT_ENDPOINT_KEY)}
        }
        self._user: dict = {}
        self._robots: set[Robot] = set()

    @property
    def user_id(self) -> str | None:
        """Returns the logged in user's id."""
        return self._user.get("userId")

    @property
    def robots(self) -> set[Robot]:
        """Returns the set of robots for the logged in account."""
        return self._robots

    async def connect(
        self, username: str = None, password: str = None, load_robots: bool = False
    ) -> None:
        """Authenticates with the Litter-Robot API."""
        try:
            if not self._session._token:
                if username and password:
                    await self._session.async_get_access_token(
                        username=username, password=password
                    )
                else:
                    raise LitterRobotLoginException(
                        "Username and password are required to login to Litter-Robot."
                    )

            if load_robots:
                await self.refresh_user()
                await self.refresh_robots()
        except ClientResponseError as ex:
            if ex.status == 401:
                raise LitterRobotLoginException(
                    "Unable to login to Litter-Robot with the supplied credentials."
                ) from ex
            else:
                raise LitterRobotException("Unable to login to Litter-Robot.") from ex
        # except OtherExceptions? as ex:
        #     raise LitterRobotException(
        #         "Unable to communicate with the Litter-Robot API."
        #     ) from ex

    async def disconnect(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def refresh_user(self) -> None:
        """Refresh the logged in user's info."""
        resp = await self._session.get(
            urljoin(DEFAULT_ENDPOINT, "users"),
        )
        self._user.update((await resp.json()).get("user"))

    async def refresh_robots(self) -> None:
        """Get information about robots connected to the account."""
        robots: set[Robot] = set()
        try:
            resp = await self._session.get(
                f"{DEFAULT_ENDPOINT}/users/{self.user_id}/robots"
            )

            for robot_data in await resp.json():
                robot_object = next(
                    filter(
                        lambda robot: (robot.id == robot_data.get(LITTER_ROBOT_ID)),
                        self._robots,
                    ),
                    None,
                )
                if robot_object:
                    robot_object._update_data(robot_data)
                else:
                    robot_object = LitterRobot3(
                        user_id=self.user_id,
                        session=self._session,
                        data=robot_data,
                    )

                robots.add(robot_object)

            resp = await self._session.post(
                LR4_ENDPOINT,
                json={
                    "query": f"""
                        query GetLR4($userId: String!) {{
                            getLitterRobot4ByUser(userId: $userId) {LITTER_ROBOT_4_MODEL}
                        }}
                        """,
                    "variables": {"userId": self.user_id},
                },
            )
            for robot_data in (
                (await resp.json()).get("data").get("getLitterRobot4ByUser")
            ):
                robot_object = next(
                    filter(
                        lambda robot: (robot.id == robot_data.get("unitId")),
                        self._robots,
                    ),
                    None,
                )
                if robot_object:
                    robot_object._update_data(robot_data)
                else:
                    robot_object = LitterRobot4(
                        user_id=self.user_id,
                        session=self._session,
                        data=robot_data,
                    )

                robots.add(robot_object)
            self._robots = robots
        except LitterRobotException:
            _LOGGER.error("Unable to retrieve your robots")
        except Exception as e:
            print(e)
