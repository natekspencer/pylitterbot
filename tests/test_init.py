"""Tests module."""
from pylitterbot import __version__


def test_version() -> None:
    """Test the version."""
    assert __version__ == "2023.1.2"
