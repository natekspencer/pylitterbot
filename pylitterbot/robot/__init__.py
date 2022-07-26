"""Robot base"""
from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Callable

from deepdiff import DeepDiff

from ..exceptions import LitterRobotException
from ..session import Session

_LOGGER = logging.getLogger(__name__)

EVENT_UPDATE = "update"


class Robot:
    """Robot base class."""

    _data_id = "robotId"
    _data_name = "robotName"
    _data_serial = "robotSerial"

    def __init__(
        self,
        id: str = None,  # pylint: disable=invalid-name,redefined-builtin
        serial: str = None,
        user_id: str = None,  # pylint: disable=unused-argument
        name: str = None,
        session: Session = None,
        data: dict = None,
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

        self._is_loaded = False
        self._path: str | None = None
        self._listeners: dict[str, list[Callable]] = {}

        if data:
            self._update_data(data)

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Returns the id of the Litter-Robot."""
        return self._id if self._id else self._data[self._data_id]

    @property
    def name(self) -> str | None:
        """Returns the name of the Litter-Robot, if any."""
        return self._name if self._name else self._data.get(self._data_name)

    @property
    def serial(self) -> str | None:
        """Returns the serial of the Litter-Robot, if any."""
        return self._serial if self._serial else self._data.get(self._data_serial)

    def emit(self, event_name: str, *args, **kwargs) -> None:
        """Run all callbacks for an event."""
        for listener in self._listeners.get(event_name, []):
            try:
                listener(*args, **kwargs)
            except:  # pragma: no cover, pylint: disable=bare-except
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

    def _update_data(self, data: dict) -> None:
        """Saves the robot info from a data dictionary."""
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
