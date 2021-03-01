from unittest.mock import Mock

import pytest
from pylitterbot.session import Session

pytestmark = pytest.mark.asyncio


async def test_base_session():
    """Tests the base session."""
    session = Session(vendor=Mock())
    assert session

    with pytest.raises(NotImplementedError):
        await session.get("")
    with pytest.raises(NotImplementedError):
        await session.patch("")
    with pytest.raises(NotImplementedError):
        await session.post("")

    assert "test" in session.generate_headers({"test": "value"}).keys()
