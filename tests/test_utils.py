from pylitterbot.utils import round_time


def test_round_time_default():
    """Tests parsing a Litter-Robot timestamp."""
    timestamp = round_time()
    assert timestamp


def test_deprecation():
    """Tests that a deprecation warning is called."""
    import pytest
    from pylitterbot.enums import LitterBoxStatus
    from pylitterbot.robot import Robot

    with pytest.warns(DeprecationWarning):
        assert Robot.UnitStatus.READY == LitterBoxStatus.READY
