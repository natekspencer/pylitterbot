from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import aioresponses
import jwt
import pytest

from pylitterbot.session import LitterRobotSession

pytestmark = pytest.mark.asyncio


async def test_token_refresh(mock_aioresponse: aioresponses) -> None:
    """Tests the base session."""
    session = LitterRobotSession(
        token={
            "access_token": jwt.encode(
                {"exp": datetime.now(tz=timezone.utc) - timedelta(hours=1)},
                "secret",
            ),
            "refresh_token": "some_refresh_token",
        }
    )
    assert session
    assert not session.is_token_valid()
    await session.refresh_token()
    assert session.is_token_valid()
