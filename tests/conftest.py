"""Conftest."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from aioresponses import aioresponses

from pylitterbot.robot.litterrobot4 import LR4_ENDPOINT
from pylitterbot.session import LitterRobotSession

from .common import (
    ACTIVITY_RESPONSE,
    INSIGHT_RESPONSE,
    LITTER_ROBOT_4_DATA,
    ROBOT_DATA,
    ROBOT_FULL_DATA,
    USER_RESPONSE,
)


@pytest.fixture
def mock_aioresponse():
    """Mock aioresponses fixture."""
    with aioresponses() as mock:
        mock.post(
            LitterRobotSession.AUTH_ENDPOINT,
            status=200,
            payload={"token": "tokenResponse"},
            repeat=True,
        )
        mock.post(
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
        mock.post(
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
        mock.get(re.compile(".*/users$"), status=200, payload=USER_RESPONSE)
        mock.get(
            re.compile(".*/robots$"),
            status=200,
            payload=[ROBOT_DATA, ROBOT_FULL_DATA],
            repeat=True,
        )
        mock.get(
            re.compile(".*/activity?.*$"),
            status=200,
            payload=ACTIVITY_RESPONSE,
            repeat=True,
        )
        mock.get(
            re.compile(".*/insights?.*$"),
            status=200,
            payload=INSIGHT_RESPONSE,
            repeat=True,
        )
        mock.post(
            LR4_ENDPOINT,
            status=200,
            payload={"data": {"getLitterRobot4ByUser": [LITTER_ROBOT_4_DATA]}},
            repeat=False,
        )

        mock.get(
            re.compile(f"^{LR4_ENDPOINT}/realtime?.*$"),
            # payload={},
            repeat=True,
            # callback=ws_callback,
        )
        yield mock
