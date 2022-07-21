"""Session handling for litter-robot endpoint."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urljoin

import jwt
from aiohttp import ClientResponse, ClientResponseError, ClientSession
from typing_extensions import ParamSpec

from .exceptions import InvalidCommandException, LitterRobotException
from .utils import decode

_P = ParamSpec("P")


class Session(ABC):
    def __init__(self, websession: ClientSession | None = None) -> None:
        """Initialize the session."""
        self._websession = websession
        self._websession_provided = websession is not None

    async def close(self) -> None:
        """Close the session."""
        if not self._websession_provided and self._websession is not None:
            await self._websession.close()

    async def get(self, path: str, **kwargs: _P.kwargs) -> dict | list[dict]:
        """Send a GET request to the specified path."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: _P.kwargs) -> dict | list[dict]:
        """Send a POST request to the specified path."""
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: _P.kwargs) -> dict | list[dict]:
        """Send a PATCH request to the specified path."""
        return await self.request("PATCH", path, **kwargs)

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    async def request(
        self, method: str, url: str, **kwargs: _P.kwargs
    ) -> dict | list[dict]:
        """Make a request."""
        if self._websession is None:
            self._websession = ClientSession()

        if "headers" not in kwargs:
            kwargs["headers"] = {}

        if (access_token := await self.async_get_access_token()) is not None:
            kwargs["headers"]["authorization"] = f"Bearer {access_token}"

        async with self._websession.request(method, url, **kwargs) as resp:
            if resp.status == 500:
                if (data := await resp.json()).get("type") == "InvalidCommandException":
                    raise InvalidCommandException(data.get("developerMessage", data))
                raise InvalidCommandException(data)
            resp.raise_for_status()
            data = await resp.json()
            return data


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
        self,
        token: dict = None,
        websession: ClientSession | None = None,
    ) -> None:
        """Initialize the session."""
        super().__init__(websession=websession)

        self._token = token
        self._custom_args = {}

    def generate_args(self, url: str, **kwargs: _P.kwargs) -> dict[str, Any]:
        """Generate args."""
        for k, v in next(
            (v for k, v in self._custom_args.items() if url.startswith(k)), {}
        ).items():
            if (orig := kwargs.get(k)) is not None:
                v = {**v, **orig} if isinstance(v, dict) else orig
            kwargs[k] = v
        return kwargs

    def is_token_valid(self) -> bool:
        """Return `True` if the token is stills valid."""
        if self._token is None:
            return False
        try:
            jwt.decode(
                self._token.get("access_token", self._token.get("idToken")),
                options={"verify_signature": False, "verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            return False
        return True

    async def async_get_access_token(self, **kwargs: _P.kwargs) -> str | None:
        """Return a valid access token."""
        if self._token is None or not self.is_token_valid():
            return None
        return self._token.get("access_token", self._token.get("idToken"))

    async def login(self, username: str, password: str) -> None:
        """Login to the Litter-Robot api and generate a new token."""
        token = await self.post(
            self.AUTH_ENDPOINT,
            skip_auth=True,
            headers={"x-api-key": decode(self.AUTH_ENDPOINT_KEY)},
            json={"email": username, "password": password},
        )

        self._token = await self.post(
            self.TOKEN_EXCHANGE_ENDPOINT,
            skip_auth=True,
            headers={"x-ios-bundle-identifier": "com.whisker.ios"},
            params={"key": decode(self.TOKEN_KEY)},
            json={"returnSecureToken": True, "token": token.get("token")},
        )

    async def refresh_token(self) -> None:
        """Refresh the access token."""
        if self._token is None:
            return None
        self._token = await self.post(
            self.TOKEN_REFRESH_ENDPOINT,
            skip_auth=True,
            headers={"x-ios-bundle-identifier": "com.whisker.ios"},
            params={"key": decode(self.TOKEN_KEY)},
            json={
                "grantType": "refresh_token",
                "refreshToken": self._token.get(
                    "refresh_token", self._token.get("refreshToken")
                ),
            },
        )

    async def request(
        self, method: str, url: str, **kwargs: _P.kwargs
    ) -> dict | list[dict]:
        """Make a request."""
        kwargs = self.generate_args(url, **kwargs)
        if not kwargs.pop("skip_auth", False) and not self.is_token_valid():
            await self.refresh_token()
        return await super().request(method, url, **kwargs)
