from unittest.mock import patch

import pytest

from pylitterbot import Account
from pylitterbot.exceptions import LitterRobotException, LitterRobotLoginException

from .common import (
    PASSWORD,
    USER_ID,
    USERNAME,
    get_account,
    mock_connect_error,
    mock_http_status_error,
)

pytestmark = pytest.mark.asyncio


async def test_account(mock_client):
    """Tests that an account is properly setup."""
    account = await get_account(mock_client)
    assert account.user_id is None
    assert account.robots == set()

    with pytest.raises(LitterRobotLoginException):
        await account.connect()

    await account.connect(username=USERNAME, password=PASSWORD, load_robots=True)
    assert account.user_id == USER_ID
    assert len(account.robots) == 2

    await account.refresh_robots()
    assert len(account.robots) == 2

    with patch(
        "pylitterbot.session.AsyncOAuth2Client.get",
        side_effect=mock_connect_error(),
    ):
        await account.refresh_robots()

    await account.disconnect()


@pytest.mark.parametrize(
    "side_effect,exception",
    [
        (mock_http_status_error(401), LitterRobotLoginException),
        (mock_http_status_error(400), LitterRobotException),
        (mock_connect_error(), LitterRobotException),
    ],
)
async def test_account_connect_exceptions(mock_client, side_effect, exception):
    """Tests the expected outcome of various exceptions that may occur on `account.connect()`."""
    account = await get_account(mock_client)

    with patch(
        "pylitterbot.session.AsyncOAuth2Client.fetch_token",
        side_effect=side_effect,
    ), pytest.raises(exception):
        await account.connect(USERNAME, PASSWORD)
