"""Test enums module."""
import logging

from pytest import LogCaptureFixture

from pylitterbot.enums import FeederRobotMealInsertSize, LitterBoxStatus


def test_drawer_full_statuses():
    """Tests the drawer full statuses are as expected."""
    statuses = LitterBoxStatus.get_drawer_full_statuses(codes_only=True)
    assert set(statuses) == set(["DF1", "DF2", "DFS", "SDF"])


def test_unknown_feeder_robot_meal_insert_size(caplog: LogCaptureFixture):
    """Test handling an unknown Feeder-Robot meal insert size."""
    assert FeederRobotMealInsertSize(12) == FeederRobotMealInsertSize.UNKNOWN
    assert caplog.record_tuples == [
        (
            "pylitterbot.enums",
            logging.ERROR,
            'Unknown meal insert size "12"',
        )
    ]
