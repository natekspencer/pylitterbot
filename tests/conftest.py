from typing import Optional
from unittest.mock import patch

import pytest
from httpx import HTTPStatusError

from pylitterbot.session import AsyncOAuth2Client

from .common import (
    ACTIVITY_FULL_RESPONSE,
    ACTIVITY_RESPONSE,
    COMMAND_RESPONSE,
    INSIGHT_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    ROBOT_DATA,
    ROBOT_FULL_DATA,
    ROBOT_FULL_ID,
    ROBOT_ID,
    TOKEN_RESPONSE,
    USER_RESPONSE,
)


async def fetch_token(self, **kwargs):
    self.parse_response_token(TOKEN_RESPONSE)


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status_code = status_code

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if self.status_code != 200:
            raise HTTPStatusError("Error in request", request=None, response=self)


class MockedResponses:
    def __init__(self, robot_data: Optional[dict] = None) -> None:
        self.robot_data = robot_data if robot_data else {}

    def mocked_requests_get(self, *args, **kwargs):
        if args[0].endswith("/users"):
            return MockResponse(USER_RESPONSE, 200)
        elif args[0].endswith("/robots"):
            return MockResponse([ROBOT_DATA, ROBOT_FULL_DATA], 200)
        elif args[0].endswith(f"/robots/{ROBOT_ID}"):
            return MockResponse({**ROBOT_DATA, **self.robot_data}, 200)
        elif args[0].endswith(f"/robots/{ROBOT_FULL_ID}"):
            return MockResponse({**ROBOT_FULL_DATA, **self.robot_data}, 200)
        elif args[0].endswith(f"/robots/{ROBOT_ID}/activity"):
            return MockResponse(ACTIVITY_RESPONSE, 200)
        elif args[0].endswith(f"/robots/{ROBOT_FULL_ID}/activity"):
            return MockResponse(ACTIVITY_FULL_RESPONSE, 200)
        elif args[0].endswith("/insights"):
            return MockResponse(INSIGHT_RESPONSE, 200)

        return MockResponse(None, 404)

    def mocked_requests_patch(self, *args, **kwargs):
        if args[0].endswith(f"/robots/{ROBOT_ID}"):
            return MockResponse({**ROBOT_DATA, **kwargs.get("json")}, 200)
        elif args[0].endswith(f"/robots/{ROBOT_FULL_ID}"):
            return MockResponse({**ROBOT_FULL_DATA, **kwargs.get("json")}, 200)

        return MockResponse(None, 404)

    def mocked_requests_post(self, *args, **kwargs):
        if args[0].endswith("/dispatch-commands"):
            if (kwargs.get("json") or {}).get("command") == "<W12":
                return MockResponse(
                    INVALID_COMMAND_RESPONSE,
                    int(INVALID_COMMAND_RESPONSE["status_code"]),
                )
            if (kwargs.get("json") or {}).get("command") == "<BAD":
                return MockResponse(
                    {"oops": "no developerMessage"},
                    int(INVALID_COMMAND_RESPONSE["status_code"]),
                )
            return MockResponse(COMMAND_RESPONSE, 200)

        return MockResponse(None, 404)


@pytest.fixture
def mock_client():
    responses = MockedResponses()
    with patch(
        "pylitterbot.session.AsyncOAuth2Client.get",
        side_effect=responses.mocked_requests_get,
    ), patch(
        "pylitterbot.session.AsyncOAuth2Client.patch",
        side_effect=responses.mocked_requests_patch,
    ), patch(
        "pylitterbot.session.AsyncOAuth2Client.post",
        side_effect=responses.mocked_requests_post,
    ):
        client = AsyncOAuth2Client
        client.fetch_token = fetch_token
        yield client
