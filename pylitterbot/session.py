"""Session handling for litter-robot endpoint."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urljoin

import jwt
from aiohttp import ClientResponse, ClientResponseError, ClientSession
from aiohttp.typedefs import StrOrURL

from .exceptions import InvalidCommandException, LitterRobotException
from .utils import decode


class Session(ABC):
    def __init__(self, websession: ClientSession | None = None) -> None:
        """Initialize the session."""
        self.websession = websession if websession is not None else ClientSession()

    async def close(self) -> None:
        """Close the session."""
        await self.websession.close()

    async def get(self, path: str, **kwargs) -> ClientResponse:
        """Send a GET request to the specified path."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> ClientResponse:
        """Send a POST request to the specified path."""
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs) -> ClientResponse:
        """Send a PATCH request to the specified path."""
        return await self.request("PATCH", path, **kwargs)

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    async def request(self, method: str, url: StrOrURL, **kwargs) -> ClientResponse:
        """Make a request."""
        headers = kwargs.pop("headers", None)

        if headers is None:
            headers = {}
        else:
            headers = dict(headers)

        if not kwargs.pop("skip_auth", False):
            access_token = await self.async_get_access_token()
            headers["authorization"] = f"Bearer {access_token}"

        resp = await self.websession.request(method, url, **kwargs, headers=headers)
        resp.raise_for_status()
        return resp


AUTH_ENDPOINT = "https://42nk7qrhdg.execute-api.us-east-1.amazonaws.com/prod/login"
AUTH_ENDPOINT_KEY = "dzJ0UEZiamxQMTNHVW1iOGRNalVMNUIyWXlQVkQzcEo3RXk2Zno4dg=="
TOKEN_EXCHANGE_ENDPOINT = (
    "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyCustomToken"
)
TOKEN_REFRESH_ENDPOINT = "https://securetoken.googleapis.com/v1/token"
TOKEN_KEY = "QUl6YVN5Q3Y4NGplbDdKa0NRbHNncXJfc2xYZjNmM3gtY01HMTVR"


class OAuth2Session(Session):
    """Class with methods for interacting with a Litter-Robot cloud session."""

    def __init__(
        self,
        token: dict = None,
        websession: ClientSession | None = None,
    ) -> None:
        """Initialize the session."""
        super().__init__(websession=websession)

        self._token = token
        self._custom_args = {
            AUTH_ENDPOINT: {
                "skip_auth": True,
                "headers": {"x-api-key": decode(AUTH_ENDPOINT_KEY)},
            },
            TOKEN_EXCHANGE_ENDPOINT: {
                "skip_auth": True,
                "headers": {"x-ios-bundle-identifier": "com.whisker.ios"},
                "params": {"key": decode(TOKEN_KEY)},
                "json": {"returnSecureToken": True},
            },
            TOKEN_REFRESH_ENDPOINT: {
                "skip_auth": True,
                "headers": {"x-ios-bundle-identifier": "com.whisker.ios"},
                "params": {"key": decode(TOKEN_KEY)},
                "json": {"grantType": "refresh_token"},
            },
        }

    def generate_args(self, url: StrOrURL, **kwargs) -> dict[str, Any]:
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
        try:
            jwt.decode(
                self._token.get("access_token", self._token.get("idToken")),
                options={"verify_signature": False, "verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            return False
        return True

    async def async_get_access_token(self, **kwargs) -> str:
        """Return a valid access token."""
        if not self._token:
            resp = await self.post(
                AUTH_ENDPOINT,
                json={
                    "email": kwargs.get("username"),
                    "password": kwargs.get("password"),
                },
            )
            async with resp:
                token = await resp.json()

            resp = await self.post(
                TOKEN_EXCHANGE_ENDPOINT, json={"token": token.get("token")}
            )
            async with resp:
                self._token = await resp.json()
        elif not self.is_token_valid():
            resp = await self.post(
                TOKEN_REFRESH_ENDPOINT,
                json={
                    "refreshToken": self._token.get(
                        "refresh_token", self._token.get("refreshToken")
                    )
                },
            )
            async with resp:
                self._token = await resp.json()
        return self._token.get("access_token", self._token.get("idToken"))

    async def request(self, method: str, url: StrOrURL, **kwargs) -> ClientResponse:
        """Make a request."""
        kwargs = self.generate_args(url, **kwargs)
        return await super().request(method, url, **kwargs)
