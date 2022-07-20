from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import jwt
import pytest
from aiohttp import ClientResponseError
from aioresponses import aioresponses

from pylitterbot.robot import LR4_ENDPOINT
from pylitterbot.session import (
    AUTH_ENDPOINT,
    TOKEN_EXCHANGE_ENDPOINT,
    TOKEN_REFRESH_ENDPOINT,
    ClientSession,
)

from .common import (
    ACTIVITY_FULL_RESPONSE,
    ACTIVITY_RESPONSE,
    COMMAND_RESPONSE,
    INSIGHT_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    LITTER_ROBOT_4_RESPONSE,
    ROBOT_DATA,
    ROBOT_FULL_DATA,
    ROBOT_FULL_ID,
    ROBOT_ID,
    TOKEN_RESPONSE,
    USER_RESPONSE,
)


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    with aioresponses() as m:
        m.post(
            AUTH_ENDPOINT, status=200, payload={"token": "tokenResponse"}, repeat=True
        )
        m.post(
            re.compile(re.escape(TOKEN_EXCHANGE_ENDPOINT)),
            status=200,
            payload={
                "kind": "kindResponse",
                "idToken": jwt.encode(
                    {"exp": datetime.now(tz=timezone.utc) + timedelta(hours=1)},
                    "secret",
                ),
                "refreshToken": "refreshTokenResponse",
                "expiresIn": "3600",
                "isNewUser": False,
            },
            repeat=True,
        )
        m.post(
            re.compile(re.escape(TOKEN_REFRESH_ENDPOINT)),
            status=200,
            payload={
                "access_token": (
                    token := jwt.encode(
                        {"exp": datetime.now(tz=timezone.utc) + timedelta(hours=1)},
                        "secret",
                    )
                ),
                "expires_in": "3600",
                "token_type": "Bearer",
                "refresh_token": "refreshTokenResponse",
                "id_token": token,
                "user_id": "userIdResponse",
                "project_id": "projectId",
            },
            repeat=True,
        )
        m.get(re.compile(".*/users$"), status=200, payload=USER_RESPONSE)
        m.get(
            re.compile(".*/robots$"),
            status=200,
            payload=[ROBOT_DATA, ROBOT_FULL_DATA],
            repeat=True,
        )
        m.get(
            re.compile(".*/activity?.*$"),
            status=200,
            payload=ACTIVITY_RESPONSE,
            repeat=True,
        )
        m.get(
            re.compile(".*/insights?.*$"),
            status=200,
            payload=INSIGHT_RESPONSE,
            repeat=True,
        )
        m.post(
            re.compile(".*/dispatch-commands$"),
            status=200,
            payload=COMMAND_RESPONSE,
            repeat=True,
        )
        m.post(
            LR4_ENDPOINT,
            status=200,
            payload={"data": {"getLitterRobot4ByUser": [LITTER_ROBOT_4_RESPONSE]}},
            repeat=True,
        )
        yield m


async def async_get_access_token(self, **kwargs):
    self.parse_response_token(TOKEN_RESPONSE)


async def __aexit__(self, exc_type, exc, tb):
    pass


class MockResponse:
    def __init__(self, json_data, status_code):
        self.json_data = json_data
        self.status = status_code

    def json(self):
        return self.json_data


class MockedResponses:
    def __init__(self, robot_data: dict | None = None) -> None:
        self.robot_data = robot_data if robot_data else {}

    async def mocked_requests_get(self, *args, **kwargs):
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

    async def mocked_requests_patch(self, *args, **kwargs):
        if args[0].endswith(f"/robots/{ROBOT_ID}"):
            return MockResponse({**ROBOT_DATA, **kwargs.get("json")}, 200)
        elif args[0].endswith(f"/robots/{ROBOT_FULL_ID}"):
            return MockResponse({**ROBOT_FULL_DATA, **kwargs.get("json")}, 200)

        return MockResponse(None, 404)

    async def mocked_requests_post(self, *args, **kwargs):
        if args[1].endswith(
            "https://42nk7qrhdg.execute-api.us-east-1.amazonaws.com/prod/login"
        ):
            return MockResponse(TOKEN_RESPONSE, 200)
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
