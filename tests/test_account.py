"""Test account module."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from aiohttp.client_exceptions import ClientError
from aioresponses import aioresponses

from pylitterbot import FeederRobot, LitterRobot3
from pylitterbot.exceptions import LitterRobotException, LitterRobotLoginException
from pylitterbot.robot.litterrobot4 import LR4_ENDPOINT

from .common import (
    LITTER_ROBOT_4_DATA,
    PASSWORD,
    ROBOT_ENDPOINT,
    ROBOT_FULL_ID,
    ROBOT_ID,
    USER_ID,
    USERNAME,
    get_account,
    mock_client_connector_error,
    mock_client_response_error,
)

pytestmark = pytest.mark.asyncio

ROBOT_COUNT = 4


async def test_account(
    mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that an account is properly setup."""
    account = await get_account(token_update_callback=lambda token: None)
    assert account.user_id is None
    assert account.robots == []
    assert len(account.session._listeners) == 1  # pylint: disable=protected-access

    with pytest.raises(LitterRobotLoginException):
        await account.connect()

    await account.connect(username=USERNAME, password=PASSWORD, load_robots=True)
    assert account.user_id == USER_ID
    assert len(account.robots) == ROBOT_COUNT

    assert len(account.get_robots(LitterRobot3)) == 2
    assert len(account.get_robots(FeederRobot)) == 1

    for robot in account.robots:
        assert len(robot._listeners) == 0  # pylint: disable=protected-access

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"getLitterRobot4ByUser": [LITTER_ROBOT_4_DATA]}},
        repeat=True,
    )
    caplog.set_level(logging.INFO)
    await account.load_robots()
    assert (
        caplog.messages[-1]
        == "skipping robot without serial number (id=00a2d005ceae00, name=Deleted Test)"
    )
    assert len(account.robots) == ROBOT_COUNT

    mock_aioresponse.get(ROBOT_ENDPOINT % ROBOT_ID, payload={})
    mock_aioresponse.get(ROBOT_ENDPOINT % ROBOT_FULL_ID, payload={})
    await account.refresh_robots()
    assert len(account.robots) == ROBOT_COUNT

    with patch(
        "pylitterbot.session.Session.request",
        side_effect=mock_client_response_error(),
    ):
        await account.load_robots()

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
async def test_account_connect_exceptions(
    side_effect: ClientError, exception: type[LitterRobotException]
) -> None:
    """Tests the expected outcome of various exceptions that may occur on `account.connect()`."""
    account = await get_account()

    with patch(
        "pylitterbot.session.Session.request",
        side_effect=side_effect,
    ), pytest.raises(exception):
        await account.connect(USERNAME, PASSWORD)

    await account.disconnect()
