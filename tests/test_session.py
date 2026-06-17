"""Test session module."""

# pylint: disable=protected-access
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from aiohttp import ClientResponseError
from aiointercept import aiointercept

from pylitterbot.session import DEFAULT_USER_AGENT, LitterRobotSession

pytestmark = pytest.mark.asyncio

EXPIRED_ACCESS_TOKEN = {
    "access_token": (
        token := jwt.encode(
            {"exp": datetime.now(tz=timezone.utc) - timedelta(hours=1)},
            "secret",
        )
    ),
    "id_token": token,
    "refresh_token": "some_refresh_token",
}
LOCALHOST = "http://localhost"


async def test_token_refresh(mock_aiointercept: aiointercept) -> None:
    """Tests the base session."""
    mock_aiointercept.patch(LOCALHOST)

    async with LitterRobotSession() as session:
        assert not session.is_token_valid()
        await session.refresh_tokens()
        assert not session.is_token_valid()

    async with LitterRobotSession(token=EXPIRED_ACCESS_TOKEN) as session:
        assert not session.is_token_valid()
        await session.patch(LOCALHOST)
        assert session.is_token_valid()


async def test_custom_headers() -> None:
    """Tests the base session."""
    async with LitterRobotSession() as session:
        session._custom_args = {"localhost": {"headers": {"a": "b"}}}
        assert session.generate_args("localhost", headers={"c": "d"}) == {
            "headers": {"a": "b", "c": "d", "User-Agent": DEFAULT_USER_AGENT}
        }


async def test_not_authorized(mock_aiointercept: aiointercept) -> None:
    """Test not authorized error."""
    mock_aiointercept.patch(LOCALHOST, status=401)

    async with LitterRobotSession(token=EXPIRED_ACCESS_TOKEN) as session:
        with pytest.raises(ClientResponseError):
            await session.patch(LOCALHOST)
