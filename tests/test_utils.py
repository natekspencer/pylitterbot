"""Test utils module."""

import pytest

from pylitterbot.utils import (
    REDACTED,
    decode,
    encode,
    first_value,
    hex_to_rgb,
    redact,
    rgb_to_hex,
    round_time,
    to_timestamp,
)


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


def test_redact() -> None:
    """Test redacting values from a dictionary."""
    assert redact({"litterRobotId": None}) == {"litterRobotId": None}
    assert redact({"litterRobotId": "someId"}) == {"litterRobotId": REDACTED}

    data = {"key": "value"}
    assert redact(data) == data
    assert redact([data, data]) == [data, data]


def test_first_value() -> None:
    """Test looking up values from a dictionary."""
    values = {"key1": 1, "key2": 2, "key4": 4}
    assert first_value(values, ("key1", "key2")) == 1
    assert first_value(values, ("key2", "key3")) == 2
    assert first_value(values, ("key3", "key4")) == 4
    assert first_value(values, ("key3", "key5")) is None
    assert first_value(values, ("key3", "key5"), 0) == 0
    assert first_value(None, ("key3", "key5"), 10) == 10


def test_hex_to_rgb() -> None:
    """Test converting color hex strings to RGB tuples."""
    assert hex_to_rgb("#FF0000") == (255, 0, 0)
    assert hex_to_rgb("83FF5B") == (131, 255, 91)
    assert hex_to_rgb("#F0A") == (255, 0, 170)
    assert hex_to_rgb("#83FF5B00") == (131, 255, 91)  # trailing alpha is ignored

    for invalid in ("", "#12345", "#GG0000", "#123456789"):
        with pytest.raises(ValueError):
            hex_to_rgb(invalid)


def test_rgb_to_hex() -> None:
    """Test converting RGB tuples to color hex strings."""
    assert rgb_to_hex((255, 0, 0)) == "#FF0000"
    assert rgb_to_hex((131, 255, 91)) == "#83FF5B"

    for invalid in ((256, 0, 0), (0, -1, 0)):
        with pytest.raises(ValueError):
            rgb_to_hex(invalid)
