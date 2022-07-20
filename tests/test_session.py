from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import aioresponses
import jwt
import pytest

from pylitterbot.session import OAuth2Session

pytestmark = pytest.mark.asyncio


async def test_token_refresh(mock_aioresponse: aioresponses) -> None:
    """Tests the base session."""
    session = OAuth2Session(
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
    assert (await session.async_get_access_token()) is not None
    assert session.is_token_valid()
