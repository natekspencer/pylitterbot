"""Account access and data handling for Litter-Robot endpoint."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar, cast

from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
    ClientWebSocketResponse,
)
from botocore.exceptions import ClientError

from .event import EVENT_UPDATE
from .exceptions import LitterRobotException, LitterRobotLoginException
from .pet import Pet
from .robot import Robot
from .robot.feederrobot import FEEDER_ENDPOINT, FEEDER_ROBOT_MODEL, FeederRobot
from .robot.litterrobot3 import DEFAULT_ENDPOINT, DEFAULT_ENDPOINT_KEY, LitterRobot3
from .robot.litterrobot4 import LITTER_ROBOT_4_MODEL, LR4_ENDPOINT, LitterRobot4
from .session import LitterRobotSession
from .utils import decode, urljoin
from .ws_monitor import WebSocketMonitor

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
        await asyncio.gather(*(robot.unsubscribe() for robot in self.robots))
        await asyncio.gather(*(monitor.close() for monitor in self._monitors.values()))
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
        try:
            all_robots = [
                self.session.get(
                    urljoin(DEFAULT_ENDPOINT, f"users/{self.user_id}/robots")
                ),
                self.session.post(
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
                self.session.post(
                    FEEDER_ENDPOINT,
                    json={
                        "query": f"""
                            query GetFeeders {{
                                feeder_unit {FEEDER_ROBOT_MODEL}
                            }}
                        """
                    },
                ),
            ]
            resp = await asyncio.gather(*all_robots)

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

            for robot_data in resp[0]:  # type: ignore
                await update_or_create_robot(LitterRobot3, robot_data)
            for robot_data in resp[1].get("data").get("getLitterRobot4ByUser") or []:  # type: ignore
                await update_or_create_robot(LitterRobot4, robot_data)
            for robot_data in resp[2].get("data", {}).get("feeder_unit") or []:  # type: ignore
                await update_or_create_robot(FeederRobot, robot_data)

            self._robots = robots
        except (LitterRobotException, ClientResponseError, ClientConnectorError) as ex:
            _LOGGER.error("Unable to retrieve your robots: %s", ex)

    async def refresh_robots(self) -> None:
        """Refresh known robots."""
        try:
            await asyncio.gather(*(robot.refresh() for robot in self.robots))
        except (LitterRobotException, ClientResponseError, ClientConnectorError) as ex:
            _LOGGER.error("Unable to refresh your robots: %s", ex)

    async def get_bearer_authorization(self) -> str | None:
        """Return the authorization token."""
        if not self.session.is_token_valid():
            await self.session.refresh_tokens()
        return await self.session.get_bearer_authorization()

    async def ws_connect(self, robot: Robot) -> ClientWebSocketResponse:
        """Initiate a websocket connection for a robot."""
        robot_class = type(robot)
        ws_monitor = self._monitors.setdefault(
            robot_class, WebSocketMonitor(self, robot_class)
        )
        if ws_monitor.websocket is None or ws_monitor.websocket.closed:
            await ws_monitor.new_connection(True)
        if ws_monitor.monitor is None or ws_monitor.monitor.done():
            await ws_monitor.start_monitor()
        return ws_monitor.websocket
