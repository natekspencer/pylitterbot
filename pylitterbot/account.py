"""Account access and data handling for Litter-Robot endpoint."""

import logging

from .const import ID, NAME
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
        self.user_id = self._session._user_id
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
            resp = self._session.get(f"users/{self.user_id}/robots")

            for robot in resp.json():
                try:
                    robot_object = [r for r in self._robots if r.id == robot[ID]].pop()
                    robot_object.refresh_robot_info(robot)
                except:
                    robot_object = Robot(
                        id=robot[ID],
                        serial=robot["litterRobotSerial"],
                        user_id=self.user_id,
                        name=robot[NAME],
                        session=self._session,
                        data=robot,
                    )
                robots.add(robot_object)

            self._robots = robots
        except LitterRobotException:
            _LOGGER.warning("Unable to retrieve your robots")
