"""Test utils module."""
from pylitterbot.utils import from_litter_robot_timestamp, round_time


def test_round_time_default():
    """Tests rouding a timestamp."""
    timestamp = round_time()
    assert timestamp


def test_from_litter_robot_timestamp():
    """Tests parsing a Litter-Robot timestamp."""
    assert from_litter_robot_timestamp(None) is None
