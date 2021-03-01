from unittest.mock import patch

import pytest
from httpx import HTTPStatusError
from pylitterbot.litterrobot import LitterRobot
from pylitterbot.session import AsyncOAuth2Client

from tests.common import (
    ACTIVITY_RESPONSE,
    COMMAND_RESPONSE,
    INSIGHT_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    ROBOT_DATA,
    ROBOT_ID,
    TOKEN_RESPONSE,
    USER_ID,
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


def mocked_requests_get(*args, **kwargs):
    if args[0] == f"{LitterRobot.endpoint}/users":
        return MockResponse(USER_RESPONSE, 200)
    elif args[0] == f"{LitterRobot.endpoint}/users/{USER_ID}/robots":
        return MockResponse([ROBOT_DATA], 200)
    elif args[0] == f"{LitterRobot.endpoint}/users/{USER_ID}/robots/{ROBOT_ID}":
        return MockResponse(ROBOT_DATA, 200)
    elif (
        args[0] == f"{LitterRobot.endpoint}/users/{USER_ID}/robots/{ROBOT_ID}/activity"
    ):
        return MockResponse(ACTIVITY_RESPONSE, 200)
    elif (
        args[0] == f"{LitterRobot.endpoint}/users/{USER_ID}/robots/{ROBOT_ID}/insights"
    ):
        return MockResponse(INSIGHT_RESPONSE, 200)

    return MockResponse(None, 404)


def mocked_requests_patch(*args, **kwargs):
    if args[0] == f"{LitterRobot.endpoint}/users/{USER_ID}/robots/{ROBOT_ID}":
        return MockResponse({**ROBOT_DATA, **kwargs.get("json")}, 200)

    return MockResponse(None, 404)


def mocked_requests_post(*args, **kwargs):
    if (
        args[0]
        == f"{LitterRobot.endpoint}/users/{USER_ID}/robots/{ROBOT_ID}/dispatch-commands"
    ):
        if (kwargs.get("json") or {}).get("command") == "<W12":
            return MockResponse(
                INVALID_COMMAND_RESPONSE, int(INVALID_COMMAND_RESPONSE["status_code"])
            )
        return MockResponse(COMMAND_RESPONSE, 200)

    return MockResponse(None, 404)


@pytest.fixture
def mock_client():
    with patch(
        "pylitterbot.session.AsyncOAuth2Client.get", side_effect=mocked_requests_get
    ), patch(
        "pylitterbot.session.AsyncOAuth2Client.patch", side_effect=mocked_requests_patch
    ), patch(
        "pylitterbot.session.AsyncOAuth2Client.post", side_effect=mocked_requests_post
    ):
        client = AsyncOAuth2Client
        client.fetch_token = fetch_token
        yield client
