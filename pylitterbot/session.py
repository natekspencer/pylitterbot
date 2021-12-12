"""Session handling for litter-robot endpoint."""
from typing import Awaitable, Callable, Dict, Optional
from urllib.parse import urljoin

from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx import (
    ConnectError,
    ConnectTimeout,
    HTTPError,
    HTTPStatusError,
    ReadTimeout,
    Response,
)

from .exceptions import InvalidCommandException, LitterRobotException
from .litterrobot import LitterRobot, Vendor


class Session:
    def __init__(self, vendor: Vendor):
        """Initialize the session."""
        self.vendor = vendor
        self.endpoint = vendor.endpoint
        self.headers = {"x-api-key": vendor.x_api_key}

    async def close(self):
        """Close the session."""
        raise NotImplementedError

    async def get(self, path, **kwargs):
        """Send a GET request to the specified path."""
        raise NotImplementedError

    async def post(self, path, **kwargs):
        """Send a POST request to the specified path."""
        raise NotImplementedError

    async def patch(self, path, **kwargs):
        """Send a PATCH request to the specified path."""
        raise NotImplementedError

    def urljoin(self, path):
        return urljoin(self.endpoint, path)

    def generate_headers(
        self, custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Merge self.headers with custom headers if necessary."""
        if not custom_headers:
            return self.headers

        return {**self.headers, **custom_headers}


class OAuth2Session(Session):
    """
    Class with methods for interacting with a Litter-Robot cloud session.

    :param email: Email for Litter-Robot account
    :param password: Password for Litter-Robot account
    """

    def __init__(self, vendor: Vendor = LitterRobot(), token: dict = None):
        super().__init__(vendor=vendor)

        def raise_on_error(response):  # pragma: no cover
            response.raise_for_status()
            return response

        self._client = AsyncOAuth2Client(
            token_endpoint=vendor.token_endpoint,
            client_id=vendor.client_id,
            client_secret=vendor.client_secret,
            token_endpoint_auth_method="client_secret_post",
            token=token,
        )

        self._client.register_compliance_hook("access_token_response", raise_on_error)
        self._client.register_compliance_hook("refresh_token_response", raise_on_error)

    async def close(self) -> None:
        """Close the session."""
        return await self._client.aclose()

    async def fetch_token(self, username: str, password: str) -> Dict[str, str]:
        """Fetch an access token via oauth2."""
        return await self._client.fetch_token(username=username, password=password)

    async def get(self, path: str, **kwargs) -> Response:
        """Make a get request."""
        return await self.call(self._client.get, path, **kwargs)

    async def post(self, path: str, **kwargs) -> Response:
        """Make a post request."""
        return await self.call(self._client.post, path, **kwargs)

    async def patch(self, path: str, **kwargs) -> Response:
        """Make a patch request."""
        return await self.call(self._client.patch, path, **kwargs)

    async def call(
        self, method: Callable[..., Awaitable[Response]], path: str, **kwargs
    ) -> Response:
        """Make a request, token will be updated automatically as needed."""
        url = self.urljoin(path)
        headers = self.generate_headers(kwargs.pop("headers", None))
        try:
            response = await method(url, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except (
            HTTPStatusError,
            HTTPError,
            ConnectTimeout,
            ConnectError,
            ReadTimeout,
        ) as ex:
            if isinstance(ex, HTTPStatusError) and ex.response.status_code == 500:
                raise InvalidCommandException(
                    f"{(message:=ex.response.json()).get('developerMessage',message)}"
                ) from ex
            raise LitterRobotException(
                "Unable to connect to the Litter-Robot API."
            ) from ex
