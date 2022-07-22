"""Account access and data handling for Litter-Robot endpoint."""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin

from aiohttp import ClientConnectorError, ClientResponseError, ClientSession

from .exceptions import LitterRobotException, LitterRobotLoginException
from .models import LITTER_ROBOT_4_MODEL
from .robot import (
    DEFAULT_ENDPOINT,
    DEFAULT_ENDPOINT_KEY,
    LR4_ENDPOINT,
    LitterRobot3,
    LitterRobot4,
    Robot,
)
from .session import LitterRobotSession
from .utils import decode

_LOGGER = logging.getLogger(__name__)


class Account:
    """Class with data and methods for interacting with a user's Litter-Robots."""

    def __init__(
        self, token: dict | None = None, websession: ClientSession | None = None
    ) -> None:
        """Initialize the account data."""
        self._session = LitterRobotSession(token=token, websession=websession)
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
        """Connect to the Litter-Robot API."""
        try:
            if not self._session.is_token_valid():
                if username and password:
                    await self._session.login(username=username, password=password)
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
            raise LitterRobotException("Unable to login to Litter-Robot.") from ex
        except ClientConnectorError as ex:
            raise LitterRobotException("Unable to reach the Litter-Robot api.") from ex

    async def disconnect(self) -> None:
        """Close the underlying session."""
        await self._session.close()

    async def refresh_user(self) -> None:
        """Refresh the logged in user's info."""
        data = await self._session.get(
            urljoin(DEFAULT_ENDPOINT, "users"),
        )
        assert isinstance(data, dict)
        self._user.update(data.get("user", {}))

    async def refresh_robots(self) -> None:
        """Get information about robots connected to the account."""
        robots: set[Robot] = set()
        try:
            all_robots = [
                self._session.get(f"{DEFAULT_ENDPOINT}/users/{self.user_id}/robots"),
                self._session.post(
                    LR4_ENDPOINT,
                    json={
                        "query": f"""
                        query GetLR4($userId: String!) {{
                            getLitterRobot4ByUser(userId: $userId) {LITTER_ROBOT_4_MODEL}
                        }}
                        """,
                        "variables": {"userId": self.user_id},
                    },
                ),
            ]
            resp = await asyncio.gather(*all_robots)

            def update_or_create_robot(robot_data: dict, cls: type[Robot]) -> None:
                # pylint: disable=protected-access
                robot_object = next(
                    filter(
                        lambda robot: (robot.id == robot_data.get(cls._data_id)),
                        self._robots,
                    ),
                    None,
                )
                if robot_object:
                    robot_object._update_data(robot_data)
                else:
                    robot_object = cls(
                        user_id=self.user_id,
                        session=self._session,
                        data=robot_data,
                    )
                robots.add(robot_object)

            for robot_data in resp[0]:
                update_or_create_robot(robot_data, LitterRobot3)
            for robot_data in resp[1].get("data").get("getLitterRobot4ByUser") or []:
                update_or_create_robot(robot_data, LitterRobot4)

            self._robots = robots
        except (LitterRobotException, ClientResponseError, ClientConnectorError):
            _LOGGER.exception("Unable to retrieve your robots")
