"""Test utils module."""
from pylitterbot.utils import decode, encode, from_litter_robot_timestamp, round_time


def test_round_time_default():
    """Tests rouding a timestamp."""
    timestamp = round_time()
    assert timestamp


def test_from_litter_robot_timestamp():
    """Tests parsing a Litter-Robot timestamp."""
    assert from_litter_robot_timestamp(None) is None


def test_encode_decode():
    """Test encoding and decoding of values."""
    value = "test"
    assert (encoded := encode(value)) == "dGVzdA=="
    assert decode(encoded) == value
    assert encode({value: value}) == "eyJ0ZXN0IjogInRlc3QifQ=="
