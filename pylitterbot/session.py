"""Session handling for litter-robot endpoint."""
from typing import Dict, Optional

import jwt
import requests
from oauthlib.oauth2 import LegacyApplicationClient, TokenExpiredError
from requests_oauthlib import OAuth2Session

from .exceptions import (
    InvalidCommandException,
    LitterRobotException,
    LitterRobotLoginException,
)
from .litterrobot import LitterRobot, Vendor

try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin


class Session:
    def __init__(self, vendor: Vendor):
        """Initialize the session."""
        self.vendor = vendor
        self.endpoint = vendor.endpoint
        self.headers = {"x-api-key": vendor.x_api_key}

    def get(self, path, **kwargs):
        """Send a GET request to the specified path."""
        raise NotImplementedError

    def post(self, path, **kwargs):
        """Send a GET request to the specified path."""
        raise NotImplementedError

    def urljoin(self, path):
        return urljoin(self.endpoint, path)

    def generate_headers(
        self, custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """"Merge self.headers with custom headers if necessary."""
        if not custom_headers:
            return self.headers

        return {**self.headers, **custom_headers}


class OAuthSession(Session):
    """
    Class with methods for interacting with a Litter-Robot cloud session.

    :param email: Email for Litter-Robot account
    :param password: Password for Litter-Robot account
    """

    def __init__(self, username: str, password: str, vendor: Vendor = LitterRobot()):
        super().__init__(vendor=vendor)
        try:

            def raise_on_error(response):
                response.raise_for_status()
                return response

            self._oauth = OAuth2Session(
                client=LegacyApplicationClient(client_id=vendor.client_id)
            )
            self._oauth.register_compliance_hook(
                "access_token_response", raise_on_error
            )
            self._oauth.register_compliance_hook(
                "refresh_token_response", raise_on_error
            )

            self._token = self.fetch_token(username, password)
            claims = jwt.decode(
                self._token.get("access_token"),
                options={"verify_signature": False, "verify_exp": True},
            )
            self._user_id = claims.get("userId")

        except (requests.exceptions.HTTPError, Exception) as ex:
            if (
                isinstance(ex, requests.exceptions.HTTPError)
                and ex.response.status_code == 401
            ):
                raise LitterRobotLoginException(
                    "Unable to login to Litter-Robot with the supplied credentials."
                ) from ex
            raise LitterRobotException("Unable to connect to Litter-Robot API.") from ex

    def refresh_tokens(self) -> dict:
        """Refresh and return new tokens."""
        token = self._oauth.refresh_token(
            self.vendor.token_endpoint,
            client_secret=self.vendor.client_secret,
        )

        return token

    def fetch_token(self, username: str, password: str) -> Dict[str, str]:
        """Fetch an access token via oauth2."""
        token = self._oauth.fetch_token(
            self.vendor.token_endpoint,
            include_client_id=True,
            client_secret=self.vendor.client_secret,
            username=username,
            password=password,
        )
        return token

    def get(self, path: str, **kwargs) -> requests.Response:
        """Make a get request."""
        return self.call("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        """Make a post request."""
        return self.call("POST", path, **kwargs)

    def call(self, method: str, path: str, **kwargs) -> requests.Response:
        """Make a get or post request.

        We don't use the built-in token refresh mechanism of OAuth2 session because
        we want to allow overriding the token refresh logic.
        """
        url = self.urljoin(path)
        try:
            response = self._call(method, url, **kwargs)
            response.raise_for_status()
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError,
            requests.exceptions.Timeout,
        ) as ex:
            if (
                isinstance(ex, requests.exceptions.HTTPError)
                and ex.response.status_code == 500
            ):
                raise InvalidCommandException(
                    f"{ex.response.json()['developerMessage']} sent to Litter-Robot"
                ) from ex
            raise LitterRobotException(
                "Unable to connect to the Litter-Robot API."
            ) from ex
        return response

    def _call(self, method: str, path: str, **kwargs) -> requests.Response:
        """Get or post request without error handling.

        Refreshes the token if necessary.
        """
        headers = self.generate_headers(kwargs.pop("headers", None))
        call_function = self._oauth.post if method == "POST" else self._oauth.get
        try:
            return call_function(path, headers=headers, **kwargs)
        except TokenExpiredError:
            self._oauth.token = self.refresh_tokens()

            return call_function(path, headers=self.headers, **kwargs)
