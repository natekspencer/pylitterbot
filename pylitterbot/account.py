"""Account access and data handling for Litter-Robot endpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar, cast

from aiohttp import (
    ClientConnectionError,
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
)
from botocore.exceptions import ClientError

from .event import EVENT_UPDATE
from .exceptions import LitterRobotException, LitterRobotLoginException
from .pet import Pet
from .robot import Robot
from .robot.feederrobot import FeederRobot
from .robot.litterrobot3 import DEFAULT_ENDPOINT, DEFAULT_ENDPOINT_KEY, LitterRobot3
from .robot.litterrobot4 import LitterRobot4
from .robot.litterrobot5 import LitterRobot5
from .session import LitterRobotSession
from .transport import WebSocketMonitor, WebSocketProtocol
from .utils import decode, urljoin

_LOGGER = logging.getLogger(__name__)
_RobotT = TypeVar("_RobotT", bound=Robot)


class Account:
    """Class with data and methods for interacting with a user's Litter-Robots."""

    def __init__(
        self,
        token: dict | None = None,
        websession: ClientSession | None = None,
        token_update_callback: Callable[[dict | None], None] | None = None,
    ) -> None:
        """Initialize the account data."""
        self._session = LitterRobotSession(token=token, websession=websession)
        self._session._custom_args[DEFAULT_ENDPOINT] = {
            "headers": {"x-api-key": decode(DEFAULT_ENDPOINT_KEY)}
        }
        self._user_id = self._session.get_user_id() if token else None
        self._user: dict = {}
        self._robots: list[Robot] = []
        self._pets: list[Pet] = []
        self._monitors: dict[type[Robot], WebSocketMonitor] = {}

        if token_update_callback:
            self._session.on(
                EVENT_UPDATE,
                lambda session=self._session: token_update_callback(session.tokens),
            )

    @property
    def user_id(self) -> str | None:
        """Return the logged in user's id."""
        if not self._user_id and self.session:
            self._user_id = self.session.get_user_id()
        return self._user_id

    @property
    def robots(self) -> list[Robot]:
        """Return the set of robots for the logged in account."""
        return self._robots

    @property
    def pets(self) -> list[Pet]:
        """Return the set of pets for the logged in account."""
        return self._pets

    @property
    def session(self) -> LitterRobotSession:
        """Return the associated session on the account."""
        return self._session

    def get_robot(self, robot_id: str | int | None) -> Robot | None:
        """If found, return the robot with the specified id."""
        return next(
            (robot for robot in self._robots if robot.id == str(robot_id)),
            None,
        )

    def get_robots(self, robot_class: type[_RobotT]) -> list[_RobotT]:
        """If found, return the specified class of robots."""
        return [robot for robot in self._robots if isinstance(robot, robot_class)]

    def get_pet(self, pet_id: str) -> Pet | None:
        """If found, return the pet with the specified id."""
        return next(
            (pet for pet in self._pets if pet.id == pet_id),
            None,
        )

    async def connect(
        self,
        username: str | None = None,
        password: str | None = None,
        load_robots: bool = False,
        subscribe_for_updates: bool = False,
        load_pets: bool = False,
    ) -> None:
        """Connect to the Litter-Robot API."""
        try:
            if not self.session.is_token_valid():
                if self.session.has_refresh_token():
                    await self.session.refresh_tokens()
                elif username and password:
                    await self.session.login(username=username, password=password)
                else:
                    raise LitterRobotLoginException(
                        "Username and password are required to login to Litter-Robot."
                    )

            if load_robots:
                await self.load_robots(subscribe_for_updates)

            if load_pets:
                await self.load_pets()

        except ClientError as err:
            _LOGGER.error(err)
            raise LitterRobotLoginException(
                f"Unable to login to Litter-Robot: {err.response['message']}"
            ) from err
        except ClientResponseError as ex:
            _LOGGER.error(ex)
            if ex.status == 401:
                raise LitterRobotLoginException(
                    "Unable to login to Litter-Robot with the supplied credentials."
                ) from ex
            raise LitterRobotException("Unable to login to Litter-Robot.") from ex
        except ClientConnectorError as ex:
            _LOGGER.error(ex)
            raise LitterRobotException("Unable to reach the Litter-Robot api.") from ex

    async def disconnect(self) -> None:
        """Close the underlying session."""
        unsubscribes = (robot.unsubscribe() for robot in self.robots)
        results = await asyncio.gather(*unsubscribes, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                _LOGGER.warning("Error during unsubscribe: %s", result)
        await self.session.close()

    async def refresh_user(self) -> None:
        """Refresh the logged in user's info."""
        data = cast(
            dict,
            await self.session.get(urljoin(DEFAULT_ENDPOINT, f"users/{self.user_id}")),
        )
        self._user.update(data.get("user", {}))

    async def load_pets(self) -> None:
        """Get information about the pets connected to the account."""
        assert self.user_id
        pets = await Pet.fetch_pets_for_user(self._session, self.user_id)
        if not self._pets:
            self._pets = pets
        else:
            for pet in pets:
                if existing_pet := self.get_pet(pet.id):
                    existing_pet._update_data(pet._data)
                else:
                    self._pets.append(pet)

    async def load_robots(self, subscribe_for_updates: bool = False) -> None:
        """Get information about robots connected to the account."""
        robots: list[Robot] = []
        robot_types: list[type[Robot]] = [
            LitterRobot3,
            LitterRobot4,
            LitterRobot5,
            FeederRobot,
        ]
        try:
            resp = await asyncio.gather(
                *(robot_cls.fetch_for_account(self) for robot_cls in robot_types),
                return_exceptions=True,
            )

            async def update_or_create_robot(
                robot_cls: type[Robot], data: dict
            ) -> None:
                # pylint: disable=protected-access
                if data.get(robot_cls._data_serial) is None:
                    _LOGGER.info(
                        "skipping robot without serial number (id=%s, name=%s)",
                        data.get(robot_cls._data_id),
                        data.get(robot_cls._data_name),
                    )
                    return
                if robot := self.get_robot(data.get(robot_cls._data_id)):
                    robot._update_data(data)
                else:
                    robot = robot_cls(data=data, account=self)
                    if subscribe_for_updates:
                        await robot.subscribe()
                robots.append(robot)

            for robot_cls, result in zip(robot_types, resp):
                if isinstance(result, BaseException):
                    _LOGGER.error("Failed to fetch %s: %s", robot_cls.__name__, result)
                    # Preserve previously-known robots of this type rather than dropping them
                    for existing in self._robots:
                        if type(existing) is robot_cls:
                            robots.append(existing)
                    continue

                for robot_data in result:
                    try:
                        await update_or_create_robot(robot_cls, robot_data)
                    except Exception:
                        _LOGGER.exception("Failed to load %s robot", robot_cls.__name__)

            self._robots = robots
        except (
            LitterRobotException,
            ClientResponseError,
            ClientConnectorError,
            ClientConnectionError,
        ) as ex:
            _LOGGER.error("Unable to retrieve your robots: %s", ex)

    async def refresh_robots(self) -> None:
        """Refresh known robots."""
        try:
            await asyncio.gather(*(robot.refresh() for robot in self.robots))
        except (
            LitterRobotException,
            ClientResponseError,
            ClientConnectorError,
            ClientConnectionError,
        ) as ex:
            _LOGGER.error("Unable to refresh your robots: %s", ex)

    async def get_bearer_authorization(self) -> str | None:
        """Return the authorization token."""
        if not self.session.is_token_valid():
            await self.session.refresh_tokens()
        return await self.session.get_bearer_authorization()

    def get_monitor_for(
        self, robot_cls: type[Robot], protocol: WebSocketProtocol
    ) -> WebSocketMonitor:
        """Return (creating if needed) the WebSocket monitor for this account + robot type."""
        if robot_cls not in self._monitors:
            self._monitors[robot_cls] = WebSocketMonitor(protocol=protocol)
        return self._monitors[robot_cls]
