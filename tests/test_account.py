import re
from unittest.mock import Mock, patch

import pytest
from aiohttp import ClientResponse, web
from aiohttp.test_utils import TestClient
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.exceptions import LitterRobotException, LitterRobotLoginException
from pylitterbot.robot import LR4_ENDPOINT

from .common import (
    PASSWORD,
    ROBOT_DATA,
    ROBOT_FULL_DATA,
    USER_ID,
    USER_RESPONSE,
    USERNAME,
    get_account,
    mock_client_connector_error,
    mock_client_response_error,
)

pytestmark = pytest.mark.asyncio


async def test_account(mock_aioresponse: aioresponses) -> None:
    """Tests that an account is properly setup."""
    account = await get_account()
    assert account.user_id is None
    assert account.robots == set()

    with pytest.raises(LitterRobotLoginException):
        await account.connect()

    await account.connect(username=USERNAME, password=PASSWORD, load_robots=True)
    assert account.user_id == USER_ID
    assert len(account.robots) == 3

    await account.refresh_robots()
    assert len(account.robots) == 3

    with patch(
        "pylitterbot.session.Session.request",
        side_effect=mock_client_response_error(),
    ):
        await account.refresh_robots()

    await account.disconnect()


@pytest.mark.parametrize(
    "side_effect,exception",
    [
        (mock_client_response_error(401), LitterRobotLoginException),
        (mock_client_response_error(400), LitterRobotException),
        (mock_client_connector_error(), LitterRobotException),
    ],
)
async def test_account_connect_exceptions(mock_aioresponse, side_effect, exception):
    """Tests the expected outcome of various exceptions that may occur on `account.connect()`."""
    account = await get_account()

    with patch(
        "pylitterbot.session.Session.request",
        side_effect=side_effect,
    ), pytest.raises(exception):
        await account.connect(USERNAME, PASSWORD)

    await account.disconnect()
