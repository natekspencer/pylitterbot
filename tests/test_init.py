"""Tests module."""
from pylitterbot import __version__


def test_version() -> None:
    """Test the version."""
    assert __version__ == "2022.10.1"
