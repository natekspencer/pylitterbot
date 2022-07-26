"""Test session module."""
# pylint: disable=protected-access
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from aioresponses import aioresponses

from pylitterbot.session import LitterRobotSession

pytestmark = pytest.mark.asyncio


async def test_token_refresh(mock_aioresponse: aioresponses) -> None:
    """Tests the base session."""
    mock_aioresponse.patch("localhost")

    session = LitterRobotSession()
    assert not session.is_token_valid()
    await session.refresh_token()
    assert not session.is_token_valid()

    session = LitterRobotSession(
        token={
            "access_token": jwt.encode(
                {"exp": datetime.now(tz=timezone.utc) - timedelta(hours=1)},
                "secret",
            ),
            "refresh_token": "some_refresh_token",
        }
    )
    assert not session.is_token_valid()
    await session.patch("localhost")
    assert session.is_token_valid()


async def test_custom_headers() -> None:
    """Tests the base session."""
    session = LitterRobotSession()
    session._custom_args = {"localhost": {"header": {"a": "b"}}}
    assert session.generate_args("localhost", header={"c": "d"}) == {
        "header": {"a": "b", "c": "d"}
    }
