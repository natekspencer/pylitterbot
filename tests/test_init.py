"""Tests module."""

from pylitterbot import __version__


def test_version() -> None:
    """Test the version."""
    assert __version__ != "0.0.0"
