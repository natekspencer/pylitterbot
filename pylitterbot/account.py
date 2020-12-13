"""Account access and data handling for Litter-Robot endpoint."""

import logging

from .exceptions import LitterRobotException
from .litterrobot import LitterRobot
from .robot import Robot
from .session import OAuthSession

_LOGGER = logging.getLogger(__name__)


class Account:
    """
    Class with data and methods for interacting with a user's Litter-Robots.
    """

    def __init__(self, username: str, password: str):
        """Initialize the account data."""
        self._session = OAuthSession(
            vendor=LitterRobot(), username=username, password=password
        )
        self._robots = set()

    @property
    def robots(self):
        """
        Return set of robots for logged in account.

        :return:
        """
        if not self._robots:
            self.refresh_robots()

        return self._robots

    def refresh_robots(self):
        """
        Get information about robots connected to account.

        :return:
        """
        robots = set()
        try:
            resp = self._session.get("users")

            for robot in resp.json()["litterRobots"]:
                try:
                    robot_object = [
                        r for r in self._robots if r.id == robot["litterRobotId"]
                    ].pop()
                except:
                    robot_object = Robot(
                        id=robot["litterRobotId"],
                        serial=robot["litterRobotSerial"],
                        user_id=robot["userId"],
                        name=robot["litterRobotNickname"],
                        session=self._session,
                    )
                robots.add(robot_object)

            self._robots = robots
        except LitterRobotException:
            _LOGGER.warning("Unable to retrieve your robots")
