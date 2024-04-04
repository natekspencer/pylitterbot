"""Test session module."""

# pylint: disable=protected-access
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from aiohttp import ClientResponseError
from aioresponses import aioresponses

from pylitterbot.session import LitterRobotSession

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


async def test_token_refresh(mock_aioresponse: aioresponses) -> None:
    """Tests the base session."""
    mock_aioresponse.patch("localhost")

    async with LitterRobotSession() as session:
        assert not session.is_token_valid()
        await session.refresh_token()
        assert not session.is_token_valid()

    async with LitterRobotSession(token=EXPIRED_ACCESS_TOKEN) as session:
        assert not session.is_token_valid()
        await session.patch("localhost")
        assert session.is_token_valid()


async def test_custom_headers() -> None:
    """Tests the base session."""
    async with LitterRobotSession() as session:
        session._custom_args = {"localhost": {"header": {"a": "b"}}}
        assert session.generate_args("localhost", header={"c": "d"}) == {
            "header": {"a": "b", "c": "d"}
        }


async def test_not_authorized(mock_aioresponse: aioresponses) -> None:
    """Test not authorized error."""
    mock_aioresponse.patch("localhost", status=401)

    async with LitterRobotSession(token=EXPIRED_ACCESS_TOKEN) as session:
        with pytest.raises(ClientResponseError):
            await session.patch("localhost")
