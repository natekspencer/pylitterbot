"""Session handling for litter-robot endpoint."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from asyncio import Lock
from types import TracebackType
from typing import Any, TypeVar, cast

import jwt
from aiohttp import ClientSession

from .event import EVENT_UPDATE, Event
from .exceptions import InvalidCommandException
from .utils import decode, first_value, redact, utcnow

T = TypeVar("T", bound="Session")

_LOGGER = logging.getLogger(__name__)


class Session(Event, ABC):
    """Abstract session class."""

    _token: dict | None = None
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
    def tokens(self) -> dict[str, str | None] | None:
        """Return the tokens."""
        if not self._token:
            return None
        return {
            "id_token": first_value(self._token, ("id_token", "idToken")),
            "refresh_token": first_value(
                self._token, ("refresh_token", "refreshToken")
            ),
        }

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
    async def async_get_access_token(self, **kwargs: Any) -> str | None:
        """Return a valid access token."""

    @abstractmethod
    def is_token_valid(self) -> bool:
        """Return `True` if the token is stills valid."""

    async def refresh_token(self, ignore_unexpired: bool = False) -> None:
        """Refresh the access token."""
        if self._token is None:
            return None
        async with self._lock:
            if not ignore_unexpired and self.is_token_valid():
                return
            self._token = await self._refresh_token()
        self.emit(EVENT_UPDATE)

    @abstractmethod
    async def _refresh_token(self) -> dict:
        """Actual implementation to refresh the access token."""

    async def get_bearer_authorization(self) -> str | None:
        """Get the bearer authorization."""
        if (access_token := await self.async_get_access_token()) is None:
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

    AUTH_ENDPOINT = "https://42nk7qrhdg.execute-api.us-east-1.amazonaws.com/prod/login"
    AUTH_ENDPOINT_KEY = "dzJ0UEZiamxQMTNHVW1iOGRNalVMNUIyWXlQVkQzcEo3RXk2Zno4dg=="
    TOKEN_EXCHANGE_ENDPOINT = (
        "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken"
    )
    TOKEN_REFRESH_ENDPOINT = "https://securetoken.googleapis.com/v1/token"
    TOKEN_KEY = "QUl6YVN5Q3Y4NGplbDdKa0NRbHNncXJfc2xYZjNmM3gtY01HMTVR"

    def __init__(
        self, token: dict | None = None, websession: ClientSession | None = None
    ) -> None:
        """Initialize the session."""
        super().__init__(websession=websession)

        self._token = token
        self._custom_args: dict = {}

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
        if self._token is None:
            return False
        try:
            jwt.decode(
                first_value(self._token, ("id_token", "idToken")),
                options={"verify_signature": False, "verify_exp": True},
                leeway=-30,
            )
        except jwt.ExpiredSignatureError:
            return False
        return True

    async def async_get_access_token(self, **kwargs: Any) -> str | None:
        """Return a valid access token."""
        if self._token is None or not self.is_token_valid():
            return None
        return first_value(self._token, ("id_token", "idToken"))

    async def login(self, username: str, password: str) -> None:
        """Login to the Litter-Robot api and generate a new token."""
        token = await self.post(
            self.AUTH_ENDPOINT,
            skip_auth=True,
            headers={"x-api-key": decode(self.AUTH_ENDPOINT_KEY)},
            json={"email": username, "password": password},
        )

        data = await self.post(
            self.TOKEN_EXCHANGE_ENDPOINT,
            skip_auth=True,
            headers={"x-ios-bundle-identifier": "com.whisker.ios"},
            params={"key": decode(self.TOKEN_KEY)},
            json={"returnSecureToken": True, "token": cast(dict, token)["token"]},
        )
        self._token = cast(dict, data)

    async def _refresh_token(self) -> dict:
        """Refresh the access token."""
        data = await self.post(
            self.TOKEN_REFRESH_ENDPOINT,
            skip_auth=True,
            headers={"x-ios-bundle-identifier": "com.whisker.ios"},
            params={"key": decode(self.TOKEN_KEY)},
            json={
                "grantType": "refresh_token",
                "refreshToken": first_value(
                    self._token, ("refresh_token", "refreshToken")
                ),
            },
        )
        return cast(dict, data)

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> dict | list[dict] | None:
        """Make a request."""
        kwargs = self.generate_args(url, **kwargs)
        if not kwargs.pop("skip_auth", False) and not self.is_token_valid():
            await self.refresh_token()
        return await super().request(method, url, **kwargs)

    def get_user_id(self) -> str | None:
        """Get the user id from the session."""
        if self._token is None:
            return None
        user_id = jwt.decode(
            first_value(self._token, ("id_token", "idToken")),
            options={"verify_signature": False, "verify_exp": False},
        )["mid"]
        return cast(str, user_id)

    def has_refresh_token(self) -> bool:
        """Return `True` if the session has a refresh token."""
        return first_value(self._token, ("refresh_token", "refreshToken")) is not None
