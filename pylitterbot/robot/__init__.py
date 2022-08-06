"""Robot base class."""
from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from deepdiff import DeepDiff

from ..exceptions import LitterRobotException
from ..session import Session
from ..utils import from_litter_robot_timestamp, urljoin

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)

EVENT_UPDATE = "update"


class Robot:
    """Robot base class."""

    _data_id: str
    _data_name: str
    _data_serial: str
    _data_setup_date: str

    _path: str

    def __init__(
        self,
        id: str = None,  # pylint: disable=invalid-name,redefined-builtin
        serial: str = None,
        user_id: str = None,  # pylint: disable=unused-argument
        name: str = None,
        session: Session = None,
        data: dict = None,
        account: Account | None = None,
    ) -> None:
        """Initialize an instance of a robot with individual attributes or a data dictionary.

        :param id: Litter-Robot id (optional)
        :param serial: Litter-Robot serial (optional)
        :param user_id: user id that has access to this Litter-Robot (optional)
        :param name: Litter-Robot name (optional)
        :param session: user's session to interact with this Litter-Robot (optional)
        :param data: optional data to pre-populate Litter-Robot's attributes (optional)
        """
        if not id and not data:
            raise LitterRobotException(
                "An id or data dictionary is required to initilize a Litter-Robot."
            )

        self._data: dict = {}

        self._id = id
        self._name = name
        self._serial = serial
        self._session = session
        self._account = account

        self._is_loaded = False
        self._listeners: dict[str, list[Callable]] = {}

        if data:
            self._update_data(data)

    def __str__(self) -> str:
        """Return str(self)."""
        return f"Name: {self.name}, Model: {self.model}, Serial: {self.serial}, id: {self.id}"

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Return the id of the robot."""
        return self._id if self._id else str(self._data[self._data_id])

    @property
    @abstractmethod
    def model(self) -> str:
        """Return the robot model."""

    @property
    def name(self) -> str | None:
        """Return the name of the robot, if any."""
        return self._name if self._name else self._data.get(self._data_name)

    @property
    @abstractmethod
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""

    @property
    @abstractmethod
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""

    @property
    def serial(self) -> str | None:
        """Return the serial of the robot, if any."""
        return self._serial if self._serial else self._data.get(self._data_serial)

    @property
    def setup_date(self) -> datetime | None:
        """Return the datetime the robot was onboarded, if any."""
        return from_litter_robot_timestamp(self._data.get(self._data_setup_date))

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        """Run all callbacks for an event."""
        for listener in self._listeners.get(event_name, []):
            try:
                listener(*args, **kwargs)
            except:  # pragma: no cover # pylint: disable=bare-except # noqa: E722
                pass

    def on(  # pylint: disable=invalid-name
        self, event_name: str, callback: Callable
    ) -> Callable:
        """Register an event callback."""
        listeners: list = self._listeners.setdefault(event_name, [])
        listeners.append(callback)

        def unsubscribe() -> None:
            """Unsubscribe listeners."""
            if callback in listeners:
                listeners.remove(callback)

        return unsubscribe

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh the robot data from the API."""

    @abstractmethod
    async def subscribe_for_updates(self) -> None:
        """Open a web socket connection to receive updates."""

    @abstractmethod
    async def unsubscribe_from_updates(self) -> None:
        """Stop the web socket."""

    def _update_data(self, data: dict) -> None:
        """Save the robot info from a data dictionary."""
        if self._is_loaded:
            _LOGGER.debug(
                "%s updated: %s",
                self.name,
                DeepDiff(self._data, data, ignore_order=True, report_repetition=True)
                or "no changes detected",
            )

        self._data.update(data)
        self._is_loaded = True
        self.emit(EVENT_UPDATE)

    async def _get(
        self, subpath: str | None = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a GET request to the Litter-Robot API."""
        assert self._session
        return await self._session.get(urljoin(self._path, subpath), **kwargs)

    async def _patch(
        self, subpath: str | None = None, json: Any = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a PATCH request to the Litter-Robot API."""
        assert self._session
        return await self._session.patch(
            urljoin(self._path, subpath), json=json, **kwargs
        )

    async def _post(
        self, subpath: str | None = None, json: Any = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a POST request to the Litter-Robot API."""
        assert self._session
        return await self._session.post(
            urljoin(self._path, subpath), json=json, **kwargs
        )
