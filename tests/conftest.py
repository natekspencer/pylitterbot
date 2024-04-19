"""Conftest."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.pet import PET_PROFILE_ENDPOINT
from pylitterbot.robot.feederrobot import FEEDER_ENDPOINT
from pylitterbot.robot.litterrobot4 import LR4_ENDPOINT
from pylitterbot.session import LitterRobotSession

from .common import (
    ACTIVITY_RESPONSE,
    FEEDER_ROBOT_DATA,
    INSIGHT_RESPONSE,
    LITTER_ROBOT_4_DATA,
    PET_DATA,
    ROBOT_DATA,
    ROBOT_DELETED_DATA,
    ROBOT_FULL_DATA,
    USER_RESPONSE,
    get_account,
)


@pytest_asyncio.fixture
async def mock_account() -> Account:
    """Mock an account."""
    return await get_account()


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    """Mock aioresponses fixture."""
    with aioresponses() as mock:
        mock.post(
            LitterRobotSession.AUTH_ENDPOINT,
            payload={"token": "tokenResponse"},
            repeat=True,
        )
        mock.post(
            re.compile(re.escape(LitterRobotSession.TOKEN_EXCHANGE_ENDPOINT)),
            payload={
                "kind": "kindResponse",
                "idToken": jwt.encode(
                    {
                        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
                        "mid": "000000",
                    },
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
            payload={
                "access_token": (
                    token := jwt.encode(
                        {
                            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
                            "mid": "000000",
                        },
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
        mock.get(re.compile(".*/users$"), payload=USER_RESPONSE)
        mock.get(
            re.compile(".*/robots$"),
            payload=[ROBOT_DATA, ROBOT_DELETED_DATA, ROBOT_FULL_DATA],
            repeat=True,
        )
        mock.get(re.compile(".*/activity?.*$"), payload=ACTIVITY_RESPONSE, repeat=True)
        mock.get(re.compile(".*/insights?.*$"), payload=INSIGHT_RESPONSE, repeat=True)
        mock.post(
            LR4_ENDPOINT,
            payload={"data": {"getLitterRobot4ByUser": [LITTER_ROBOT_4_DATA]}},
            repeat=False,
        )
        mock.get(
            re.compile(f"^{LR4_ENDPOINT}/realtime?.*$"),
            # payload={},
            repeat=True,
            # callback=ws_callback,
        )
        mock.post(
            FEEDER_ENDPOINT,
            payload={"data": {"feeder_unit": [FEEDER_ROBOT_DATA]}},
            repeat=True,
        )
        mock.post(PET_PROFILE_ENDPOINT, payload={"data": {"getPetsByUser": [PET_DATA]}})
        yield mock
