"""Test utils module."""
from pylitterbot.utils import decode, encode, round_time, to_timestamp


def test_round_time_default() -> None:
    """Tests rouding a timestamp."""
    timestamp = round_time()
    assert timestamp


def test_to_timestamp() -> None:
    """Tests parsing a Litter-Robot timestamp."""
    assert to_timestamp(None) is None
    assert to_timestamp("2022-09-14") is not None


def test_encode_decode() -> None:
    """Test encoding and decoding of values."""
    value = "test"
    assert (encoded := encode(value)) == "dGVzdA=="
    assert decode(encoded) == value
    assert encode({value: value}) == "eyJ0ZXN0IjogInRlc3QifQ=="
