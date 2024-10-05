"""Session handling for litter-robot endpoint."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Lock
from functools import partial
from types import TracebackType
from typing import Any, Final, TypeVar, cast

import jwt
from aiohttp import ClientSession
from botocore.exceptions import ClientError, ParamValidationError
from pycognito import Cognito

from .event import EVENT_UPDATE, Event
from .exceptions import InvalidCommandException
from .utils import decode, redact, utcnow

T = TypeVar("T", bound="Session")

_LOGGER = logging.getLogger(__name__)


class Session(Event, ABC):
    """Abstract session class."""

    _lock = Lock()

    def __init__(self, websession: ClientSession | None = None) -> None:
        """Initialize the session."""
        super().__init__()
        self._websession_provided = websession is not None
        self._websession = websession

    @property
    def websession(self) -> ClientSession:
        """Get websession."""
        if self._websession is None:
            self._websession = ClientSession()
        return self._websession

    @property
    @abstractmethod
    def tokens(self) -> dict[str, str] | None:
        """Return the tokens."""

    async def close(self) -> None:
        """Close the session."""
        if not self._websession_provided and self.websession is not None:
            await self.websession.close()

    async def get(self, path: str, **kwargs: Any) -> dict | list[dict] | None:
        """Send a GET request to the specified path."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict | list[dict] | None:
        """Send a POST request to the specified path."""
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> dict | list[dict] | None:
        """Send a PATCH request to the specified path."""
        return await self.request("PATCH", path, **kwargs)

    @abstractmethod
    async def async_get_id_token(self, **kwargs: Any) -> str | None:
        """Return a valid access token."""

    @abstractmethod
    def is_token_valid(self) -> bool:
        """Return `True` if the token is stills valid."""

    async def refresh_tokens(self, ignore_unexpired: bool = False) -> None:
        """Refresh the access token."""
        if self.tokens is None:
            return None
        async with self._lock:
            if not ignore_unexpired and self.is_token_valid():
                return
            await self._refresh_tokens()
        self.emit(EVENT_UPDATE)

    @abstractmethod
    async def _refresh_tokens(self) -> None:
        """Actual implementation to refresh the tokens."""

    async def get_bearer_authorization(self) -> str | None:
        """Get the bearer authorization."""
        if (access_token := await self.async_get_id_token()) is None:
            return None
        return f"Bearer {access_token}"

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Make a request."""
        _LOGGER.debug("Making %s request to %s", method, url)

        if "headers" not in kwargs:
            kwargs["headers"] = {}

        if (authorization := await self.get_bearer_authorization()) is not None:
            kwargs["headers"]["authorization"] = authorization

        async with self.websession.request(method, url, **kwargs) as resp:
            if resp.status == 500:
                if (data := await resp.json()).get("type") == "InvalidCommandException":
                    raise InvalidCommandException(data.get("developerMessage", data))
                raise InvalidCommandException(data)
            if resp.status == 401:
                if authorization is not None:
                    _LOGGER.error(
                        "Now: %s, Expiration: %s, Difference: %s",
                        (now := utcnow().timestamp()),
                        (
                            expires := jwt.decode(
                                authorization.replace("Bearer ", ""),
                                options={"verify_signature": False},
                            )["exp"]
                        ),
                        expires - now,
                    )
                _LOGGER.error("Unauthorized")

            resp.raise_for_status()
            data = await resp.json()
            _LOGGER.debug(
                "Received %s response from %s: %s", resp.status, url, redact(data)
            )
            return data  # type: ignore

    async def __aenter__(self: T) -> T:
        """Async enter."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async exit."""
        await self.close()


class LitterRobotSession(Session):
    """Class with methods for interacting with a Litter-Robot cloud session."""

    USER_POOL_ID: Final = "dXMtZWFzdC0xX3JqaE5uWlZBbQ=="
    CLIENT_ID: Final = "NDU1MnVqZXUzYWljOTBuZjhxbjUzbGV2bW4="

    _user: Cognito | None = None

    _username: str | None = None
    __access_token: str | None = None
    __id_token: str | None = None
    __refresh_token: str | None = None

    def __init__(
        self, token: dict | None = None, websession: ClientSession | None = None
    ) -> None:
        """Initialize the session."""
        super().__init__(websession=websession)

        if token:
            self.__access_token = token.get("access_token")
            self.__id_token = token.get("id_token")
            self.__refresh_token = token.get("refresh_token")
        self._custom_args: dict = {}

    @property
    def access_token(self) -> str | None:
        """Return the access token, if any."""
        return self._user.access_token if self._user else self.__access_token

    @property
    def id_token(self) -> str | None:
        """Return the id token, if any."""
        return self._user.id_token if self._user else self.__id_token

    @property
    def refresh_token(self) -> str | None:
        """Return the refresh token, if any."""
        return self._user.refresh_token if self._user else self.__refresh_token

    @property
    def tokens(self) -> dict[str, str] | None:
        """Return the tokens."""
        if None in (self.access_token, self.id_token):
            return None
        token = {
            "access_token": self.access_token,
            "id_token": self.id_token,
            "refresh_token": self.refresh_token,
        }
        return cast(dict[str, str], token)

    def generate_args(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Generate args."""
        for key, value in next(
            (value for key, value in self._custom_args.items() if url.startswith(key)),
            {},
        ).items():
            if (orig := kwargs.get(key)) is not None:
                value = {**value, **orig} if isinstance(value, dict) else orig
            kwargs[key] = value
        return kwargs

    def is_token_valid(self) -> bool:
        """Return `True` if the token is stills valid."""
        if self.tokens is None:
            return False
        try:
            jwt.decode(
                self.id_token,
                options={"verify_signature": False, "verify_exp": True},
                leeway=-30,
            )
        except jwt.ExpiredSignatureError:
            return False
        return True

    async def async_get_id_token(self, **kwargs: Any) -> str | None:
        """Return a valid id token."""
        if self.tokens is None or not self.is_token_valid():
            return None
        return self.id_token

    async def login(self, username: str, password: str) -> None:
        """Login to the Litter-Robot api and generate a new token."""
        self._username = username
        user = await self.get_user()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, partial(user.authenticate, password=password))
        self.emit(EVENT_UPDATE)

    async def _refresh_tokens(self) -> None:
        """Refresh the access token."""
        user = await self.get_user()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, user.renew_access_token)

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Make a request."""
        kwargs = self.generate_args(url, **kwargs)
        if not kwargs.pop("skip_auth", False) and not self.is_token_valid():
            await self.refresh_tokens()
        return await super().request(method, url, **kwargs)

    async def get_user(self) -> Cognito:
        """Return the Cognito user."""
        if self._user is None:
            loop = asyncio.get_running_loop()
            self._user = await loop.run_in_executor(
                None,
                partial(
                    Cognito,
                    decode(self.USER_POOL_ID),
                    decode(self.CLIENT_ID),
                    username=self._username,
                    access_token=self.__access_token,
                    id_token=self.__id_token,
                    refresh_token=self.__refresh_token,
                ),
            )
            assert self._user
            if self.__access_token and self.__id_token:
                try:
                    await loop.run_in_executor(None, self._user.check_token)
                    self._user.verify_tokens()
                except ClientError as err:
                    _LOGGER.error(err)
                    raise err
                except ParamValidationError:
                    # tokens are invalid
                    pass
        if self._username and not self._user.username:
            self._user.username = self._username
        return self._user

    def get_user_id(self) -> str | None:
        """Get the user id from the session."""
        if self.tokens is None:
            return None
        user_id = jwt.decode(
            self.id_token,
            options={"verify_signature": False, "verify_exp": False},
        )["mid"]
        return cast(str, user_id)

    def has_refresh_token(self) -> bool:
        """Return `True` if the session has a refresh token."""
        return self.tokens is not None and self.refresh_token is not None
