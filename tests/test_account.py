import re
from unittest.mock import Mock, patch

import pytest
from aiohttp import ClientResponse, web
from aiohttp.test_utils import TestClient
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.exceptions import LitterRobotException, LitterRobotLoginException
from pylitterbot.robot import LR4_ENDPOINT
from pylitterbot.session import AUTH_ENDPOINT, TOKEN_EXCHANGE_ENDPOINT

from .common import (
    PASSWORD,
    ROBOT_DATA,
    ROBOT_FULL_DATA,
    USER_ID,
    USER_RESPONSE,
    USERNAME,
    get_account,
    mock_connect_error,
    mock_http_status_error,
)

pytestmark = pytest.mark.asyncio


async def test_account(mock_aioresponse: aioresponses) -> None:
    """Tests that an account is properly setup."""
    # mock_aioresponse.post(
    #     AUTH_ENDPOINT, status=200, payload={"token": "tokenResponse"}, repeat=True
    # )
    # mock_aioresponse.post(
    #     re.compile(re.escape(TOKEN_EXCHANGE_ENDPOINT)),
    #     status=200,
    #     payload={
    #         "kind": "kindResponse",
    #         "idToken": "idTokenResponse",
    #         "refreshToken": "refreshTokenResponse",
    #         "expiresIn": "3600",
    #         "isNewUser": False,
    #     },
    #     repeat=True,
    # )
    # mock_aioresponse.get(re.compile(".*/users$"), status=200, payload=USER_RESPONSE)
    # mock_aioresponse.get(
    #     re.compile(".*/robots$"),
    #     status=200,
    #     payload=[ROBOT_DATA, ROBOT_FULL_DATA],
    #     repeat=True,
    # )
    # mock_aioresponse.post(
    #     LR4_ENDPOINT,
    #     status=200,
    #     payload={"data": {"getLitterRobot4ByUser": []}},
    #     repeat=True,
    # )

    account = await get_account()
    assert account.user_id is None
    assert account.robots == set()

    with pytest.raises(LitterRobotLoginException):
        await account.connect()

    await account.connect(username=USERNAME, password=PASSWORD, load_robots=True)
    assert account.user_id == USER_ID
    assert len(account.robots) == 2

    await account.refresh_robots()
    assert len(account.robots) == 2

    # with patch(
    #     "pylitterbot.session.ClientSession.request",
    #     side_effect=mock_connect_error(),
    # ):
    #     await account.refresh_robots()

    await account.disconnect()


# @pytest.mark.parametrize(
#     "side_effect,exception",
#     [
#         (mock_http_status_error(401), LitterRobotLoginException),
#         (mock_http_status_error(400), LitterRobotException),
#         (mock_connect_error(), LitterRobotException),
#     ],
# )
# async def test_account_connect_exceptions(aiohttp_client, side_effect, exception):
#     """Tests the expected outcome of various exceptions that may occur on `account.connect()`."""
#     account = await get_account(aiohttp_client)

#     with patch(
#         "pylitterbot.session.ClientSession.async_get_access_token",
#         side_effect=side_effect,
#     ), pytest.raises(exception):
#         await account.connect(USERNAME, PASSWORD)
