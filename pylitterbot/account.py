"""Account access and data handling for Litter-Robot endpoint."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from aiohttp import (
    ClientConnectorError,
    ClientResponseError,
    ClientSession,
    ClientWebSocketResponse,
)

from .exceptions import LitterRobotException, LitterRobotLoginException
from .robot import Robot
from .robot.feederrobot import FEEDER_ENDPOINT, FEEDER_ROBOT_MODEL, FeederRobot
from .robot.litterrobot3 import DEFAULT_ENDPOINT, DEFAULT_ENDPOINT_KEY, LitterRobot3
from .robot.litterrobot4 import LITTER_ROBOT_4_MODEL, LR4_ENDPOINT, LitterRobot4
from .session import LitterRobotSession
from .utils import decode, urljoin

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
        self._robots: list[Robot] = []
        self._ws_connections: dict[str, tuple[ClientWebSocketResponse, list[str]]] = {}

    @property
    def user_id(self) -> str | None:
        """Return the logged in user's id."""
        return self._user.get("userId")

    @property
    def robots(self) -> list[Robot]:
        """Return the set of robots for the logged in account."""
        return self._robots

    async def connect(
        self,
        username: str = None,
        password: str = None,
        load_robots: bool = False,
        subscribe_for_updates: bool = False,
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
                await self.load_robots(subscribe_for_updates)
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
        for robot in self.robots:
            await robot.unsubscribe_from_updates()
        for websocket, _ in self._ws_connections.values():
            await websocket.close()
        await self._session.close()

    async def refresh_user(self) -> None:
        """Refresh the logged in user's info."""
        data = await self._session.get(urljoin(DEFAULT_ENDPOINT, "users"))
        assert isinstance(data, dict)
        self._user.update(data.get("user", {}))

    async def load_robots(self, subscribe_for_updates: bool = False) -> None:
        """Get information about robots connected to the account."""
        robots: list[Robot] = []
        try:
            all_robots = [
                self._session.get(
                    urljoin(DEFAULT_ENDPOINT, f"users/{self.user_id}/robots")
                ),
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
                self._session.post(
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
                robot_object = next(
                    filter(
                        lambda robot: (robot.id == data.get(robot_cls._data_id)),
                        self._robots,
                    ),
                    None,
                )
                if robot_object:
                    robot_object._update_data(data)
                else:
                    robot_object = robot_cls(
                        user_id=self.user_id,
                        session=self._session,
                        data=data,
                        account=self,
                    )
                    if subscribe_for_updates:
                        await robot_object.subscribe_for_updates()
                robots.append(robot_object)

            for robot_data in resp[0]:
                await update_or_create_robot(LitterRobot3, robot_data)
            for robot_data in resp[1].get("data").get("getLitterRobot4ByUser") or []:
                await update_or_create_robot(LitterRobot4, robot_data)
            for robot_data in resp[2].get("data").get("feeder_unit") or []:
                await update_or_create_robot(FeederRobot, robot_data)

            self._robots = robots
        except (LitterRobotException, ClientResponseError, ClientConnectorError) as ex:
            _LOGGER.error("Unable to retrieve your robots: %s", ex)

    async def refresh_robots(self) -> None:
        """Refresh known robots."""
        try:
            await asyncio.gather(*[robot.refresh() for robot in self.robots])
        except (LitterRobotException, ClientResponseError, ClientConnectorError) as ex:
            _LOGGER.error("Unable to refresh your robots: %s", ex)

    async def ws_connect(
        self,
        url: str,
        params: Mapping[str, str] | None,
        headers: Mapping[str, str],
        subscriber_id: str,
    ) -> ClientWebSocketResponse:
        """Initiate websocket connection."""
        assert self._session.websession

        async def _new_ws_connection() -> ClientWebSocketResponse:
            assert self._session.websession
            return await self._session.websession.ws_connect(
                url=url, params=params, headers=headers
            )

        websocket, subscribers = self._ws_connections.setdefault(
            url, (await _new_ws_connection(), [subscriber_id])
        )
        if websocket.closed:
            websocket = await _new_ws_connection()
            self._ws_connections[url] = (websocket, subscribers)
        if subscriber_id not in subscribers:
            subscribers.append(subscriber_id)
        return websocket

    async def ws_disconnect(self, subscriber_id: str) -> None:
        """Disconnect a subscriber from a websocket.

        Close websocket if no longer used.
        """
        closed_ws_urls: list[str] = []
        for url, (websocket, subscribers) in self._ws_connections.items():
            if subscriber_id in subscribers:
                subscribers.remove(subscriber_id)
            if not subscribers and not websocket.closed:
                await websocket.close()
                closed_ws_urls.append(url)
        for url in closed_ws_urls:
            self._ws_connections.pop(url)
