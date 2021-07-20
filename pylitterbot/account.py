"""Account access and data handling for Litter-Robot endpoint."""
import logging
from typing import Optional, Set

from httpx import ConnectError, ConnectTimeout, HTTPStatusError

from .enums import LitterBoxStatus
from .exceptions import LitterRobotException, LitterRobotLoginException
from .litterrobot import LitterRobot
from .robot import LITTER_ROBOT_ID, Robot
from .session import OAuth2Session

_LOGGER = logging.getLogger(__name__)


class Account:
    """Class with data and methods for interacting with a user's Litter-Robots."""

    def __init__(self, token: dict = None) -> None:
        """Initialize the account data."""
        self._session = OAuth2Session(vendor=LitterRobot(), token=token)
        self._user = dict()
        self._robots: Set[Robot] = set()

    @property
    def user_id(self) -> Optional[str]:
        """Returns the logged in user's id."""
        return self._user.get("userId")

    @property
    def robots(self) -> Set[Robot]:
        """Returns the set of robots for the logged in account."""
        return self._robots

    async def connect(
        self, username: str = None, password: str = None, load_robots: bool = False
    ) -> None:
        """Authenticates with the Litter-Robot API."""
        try:
            if not self._session._client.token:
                if username and password:
                    await self._session.fetch_token(
                        username=username, password=password
                    )
                else:
                    raise LitterRobotLoginException(
                        "Username and password are required to login to Litter-Robot."
                    )

            if load_robots:
                await self.refresh_user()
                await self.refresh_robots()
        except HTTPStatusError as ex:
            if ex.response.status_code == 401:
                raise LitterRobotLoginException(
                    "Unable to login to Litter-Robot with the supplied credentials."
                ) from ex
            else:
                raise LitterRobotException("Unable to login to Litter-Robot.") from ex
        except (ConnectError, ConnectTimeout) as ex:
            raise LitterRobotException(
                "Unable to communicate with the Litter-Robot API."
            ) from ex

    async def refresh_user(self) -> None:
        """Refresh the logged in user's info."""
        self._user.update((await self._session.get("users")).json().get("user"))

    async def refresh_robots(self) -> None:
        """Get information about robots connected to the account."""
        robots: Set[Robot] = set()
        try:
            resp = await self._session.get(f"users/{self.user_id}/robots")

            for robot_data in resp.json():
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
                    robot_object = Robot(
                        user_id=self.user_id,
                        session=self._session,
                        data=robot_data,
                    )

                robots.add(robot_object)

            self._robots = robots
        except LitterRobotException:
            _LOGGER.error("Unable to retrieve your robots")
