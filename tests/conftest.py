from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import jwt
import pytest
from aiohttp import ClientResponse, ClientResponseError
from aioresponses import CallbackResult, aioresponses

from pylitterbot.robot import LR4_ENDPOINT
from pylitterbot.session import ClientSession, LitterRobotSession

from .common import (
    ACTIVITY_FULL_RESPONSE,
    ACTIVITY_RESPONSE,
    COMMAND_RESPONSE,
    INSIGHT_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    LITTER_ROBOT_4_DATA,
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
            LitterRobotSession.AUTH_ENDPOINT,
            status=200,
            payload={"token": "tokenResponse"},
            repeat=True,
        )
        m.post(
            re.compile(re.escape(LitterRobotSession.TOKEN_EXCHANGE_ENDPOINT)),
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
            re.compile(re.escape(LitterRobotSession.TOKEN_REFRESH_ENDPOINT)),
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
            LR4_ENDPOINT,
            status=200,
            payload={"data": {"getLitterRobot4ByUser": [LITTER_ROBOT_4_DATA]}},
            repeat=False,
        )
        yield m
