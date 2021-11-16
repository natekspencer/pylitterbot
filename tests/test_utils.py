from pylitterbot.utils import round_time


def test_round_time_default():
    """Tests parsing a Litter-Robot timestamp."""
    timestamp = round_time()
    assert timestamp
