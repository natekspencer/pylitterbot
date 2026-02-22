"""Robot base class."""

from __future__ import annotations

import logging
from abc import abstractmethod
from collections.abc import Callable
from datetime import datetime
from enum import IntFlag
from typing import TYPE_CHECKING, Any, cast

from deepdiff import DeepDiff

from ..event import EVENT_UPDATE, Event
from ..transport import Transport
from ..utils import to_timestamp, urljoin

if TYPE_CHECKING:
    from ..account import Account

_LOGGER = logging.getLogger(__name__)


class Robot(Event):
    """Robot base class."""

    _attr_model: str

    _data_id: str
    _data_name: str
    _data_serial: str
    _data_setup_date: str

    _path: str

    _transport: Transport | None = None
    _subscribed: bool = False

    def __init__(self, data: dict, account: Account) -> None:
        """Initialize a robot."""
        super().__init__()
        self._data: dict = {}
        self._account = account

        self._is_loaded = False

        if data:
            if data.get(self._data_serial) is None:
                raise ValueError("Robot data must include a serial number")
            self._update_data(data)

    def __str__(self) -> str:
        """Return str(self)."""
        return f"Name: {self.name}, Model: {self.model}, Serial: {self.serial}, id: {self.id}"

    def to_dict(self) -> dict[str, Any]:
        """Return the robot data dict."""
        return self._data

    @property
    @abstractmethod
    def capabilities(self) -> IntFlag:
        """Return the capabilities of this robot."""

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Return the id of the robot."""
        return str(self._data[self._data_id])

    @property
    @abstractmethod
    def is_online(self) -> bool:
        """Return `True` if the robot is online."""

    @property
    def model(self) -> str:
        """Return the robot model."""
        return self._attr_model

    @property
    def name(self) -> str:
        """Return the name of the robot, if any."""
        return cast(str, self._data.get(self._data_name, ""))

    @property
    @abstractmethod
    def night_light_mode_enabled(self) -> bool:
        """Return `True` if night light mode is enabled."""

    @property
    @abstractmethod
    def panel_lock_enabled(self) -> bool:
        """Return `True` if the buttons on the robot are disabled."""

    @property
    @abstractmethod
    def power_status(self) -> str:
        """Return the power type.

        `AC` = normal/mains
        `DC` = battery backup
        `NC` = unknown, not connected or off
        """

    @property
    def serial(self) -> str:
        """Return the serial of the robot, if any."""
        return cast(str, self._data.get(self._data_serial, ""))

    @property
    def setup_date(self) -> datetime | None:
        """Return the datetime the robot was onboarded, if any."""
        return to_timestamp(self._data.get(self._data_setup_date))

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh the robot data from the API."""

    @abstractmethod
    async def set_name(self, name: str) -> bool:
        """Set the name."""

    @abstractmethod
    async def set_night_light(self, value: bool) -> bool:
        """Turn the night light mode on or off."""

    @abstractmethod
    async def set_panel_lockout(self, value: bool) -> bool:
        """Turn the panel lock on or off."""

    def _update_data(
        self,
        data: dict,
        partial: bool = False,
        callback: Callable[[], Any] | None = None,
    ) -> None:
        """Save the robot info from a data dictionary."""
        if self._is_loaded:
            if diff := DeepDiff(
                self._data,
                {**self._data, **data} if partial else data,
                ignore_order=True,
                report_repetition=True,
                verbose_level=2,
            ):
                _LOGGER.debug("%s updated: %s", self.name, diff)

        self._data.update(data)
        if callback:
            callback()
        self._is_loaded = True
        self.emit(EVENT_UPDATE)

    async def _get(
        self, subpath: str | None = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a GET request to the Litter-Robot API."""
        return await self._account.session.get(urljoin(self._path, subpath), **kwargs)

    async def _patch(
        self, subpath: str | None = None, json: Any | None = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a PATCH request to the Litter-Robot API."""
        return await self._account.session.patch(
            urljoin(self._path, subpath), json=json, **kwargs
        )

    async def _post(
        self, subpath: str | None = None, json: Any | None = None, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Send a POST request to the Litter-Robot API."""
        return await self._account.session.post(
            urljoin(self._path, subpath), json=json, **kwargs
        )

    @classmethod
    async def fetch_for_account(cls, account: Account) -> list[dict[str, object]]:
        """Fetch robot data for account."""
        raise NotImplementedError()

    def _build_transport(self) -> Transport:
        """Return the Transport instance for this robot.

        Override in subclasses:
          - WebSocket robots → return self._account.get_monitor_for(type(self), self._WS_PROTOCOL)
          - Polling robots  → return PollingTransport(interval=30)
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement _build_transport() "
            "or override subscribe()/unsubscribe() directly."
        )

    async def subscribe(self) -> None:
        """Start receiving updates (WebSocket or polling)."""
        if self._subscribed:
            _LOGGER.debug("%s already subscribed", self.name)
            return
        if self._transport is None:
            self._transport = self._build_transport()
        await self._transport.start(self)
        self._subscribed = True
        _LOGGER.debug("%s subscribed to updates", self.name)

    async def unsubscribe(self) -> None:
        """Stop receiving updates."""
        if self._transport is not None:
            await self._transport.stop(self)
            self._subscribed = False
            _LOGGER.debug("%s unsubscribed from updates", self.name)
