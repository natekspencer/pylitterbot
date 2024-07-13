"""Conftest."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from aioresponses import aioresponses
from pycognito import TokenVerificationException

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


@pytest.fixture(autouse=True)
def no_cognito(monkeypatch):  # type: ignore
    """Remove pycognito.aws_srp.AWSSRP.authenticate_user for all tests."""

    def _mock_authenticate_user(_, client=None, client_metadata=None):  # type: ignore
        return {
            "AuthenticationResult": {
                "TokenType": "admin",
                "IdToken": jwt.encode(
                    {
                        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=1),
                        "mid": "000000",
                    },
                    "secret",
                ),
                "AccessToken": "dummy_token",
                "RefreshToken": "dummy_token",
            }
        }

    def _mock_verify_tokens(self, token, id_name, token_use):  # type: ignore
        if "wrong" in token:
            raise TokenVerificationException
        setattr(self, id_name, token)

    def _mock_renew_access_token(self):  # type: ignore
        self._set_tokens(_mock_authenticate_user(None))  # type: ignore

    monkeypatch.setattr(
        "pycognito.aws_srp.AWSSRP.authenticate_user", _mock_authenticate_user
    )
    monkeypatch.setattr("pycognito.Cognito.verify_token", _mock_verify_tokens)
    monkeypatch.setattr(
        "pycognito.Cognito.renew_access_token", _mock_renew_access_token
    )


@pytest_asyncio.fixture
async def mock_account() -> Account:
    """Mock an account."""
    return await get_account()


@pytest.fixture
def mock_aioresponse() -> aioresponses:
    """Mock aioresponses fixture."""
    with aioresponses() as mock:
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
