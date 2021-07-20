import logging
from datetime import datetime, time, timedelta
from unittest.mock import patch

import pytest
import pytz
from pylitterbot.enums import LitterBoxCommand, LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.robot import UNIT_STATUS, Robot

from .common import (
    ROBOT_DATA,
    ROBOT_FULL_ID,
    ROBOT_ID,
    ROBOT_NAME,
    ROBOT_SERIAL,
    get_robot,
)
from .conftest import MockedResponses

pytestmark = pytest.mark.asyncio


def test_robot_setup():
    """Tests that robot setup is successful and parses as expected."""
    robot = Robot(data=ROBOT_DATA)
    assert robot
    assert str(robot) == f"Name: {ROBOT_NAME}, Serial: {ROBOT_SERIAL}, id: {ROBOT_ID}"
    assert robot.auto_offline_disabled
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_capacity == 30
    assert robot.cycle_count == 15
    assert robot.cycles_after_drawer_full == 0
    assert robot.device_type == "udp"
    assert not robot.did_notify_offline
    assert robot.drawer_full_indicator_cycle_count == 0
    assert not robot.is_drawer_full_indicator_triggered
    assert robot.is_onboarded
    assert robot.is_sleeping
    assert not robot.is_waste_drawer_full
    assert robot.last_seen == datetime(
        year=2021, month=2, day=1, minute=30, tzinfo=pytz.UTC
    )
    assert robot.model == "Litter-Robot 3 Connect"
    assert robot.name == ROBOT_NAME
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    assert robot.power_status == "AC"
    assert robot.setup_date == datetime(year=2021, month=1, day=1, tzinfo=pytz.UTC)
    assert robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time.timetz() == time(
        hour=22, minute=30, tzinfo=pytz.UTC
    )
    assert robot.sleep_mode_end_time.timetz() == time(
        hour=6, minute=30, tzinfo=pytz.UTC
    )
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 50


def test_robot_with_sleep_mode_time():
    """Tests that robot with `sleepModeTime` is setup correctly."""
    for hour in range(-12, 25, 12):
        with patch(
            "pylitterbot.robot.utcnow",
            return_value=datetime.now(pytz.UTC) + timedelta(hours=hour),
        ):
            start_time = datetime.combine(
                datetime.today(), time(hour=12, tzinfo=pytz.UTC)
            )

            robot = Robot(
                data={**ROBOT_DATA, "sleepModeTime": int(start_time.timestamp())}
            )
            assert robot.sleep_mode_start_time.timetz() == start_time.timetz()


def test_robot_with_invalid_sleep_mode_active(caplog):
    """Tests that a robot with an invalid `sleepModeActive` value is setup correctly."""
    invalid_value = "17F"
    robot = Robot(data={**ROBOT_DATA, "sleepModeActive": invalid_value})
    assert caplog.record_tuples == [
        (
            "pylitterbot.robot",
            logging.ERROR,
            f"Unable to parse sleep mode start time from value '{invalid_value}'",
        )
    ]
    assert robot.sleep_mode_start_time is None


def test_robot_with_unknown_status():
    """Tests that a robot with an unknown `unitStatus` is setup correctly."""
    import random
    import string

    random_status = "_" + "".join(random.sample(string.ascii_letters, 3))

    robot = Robot(data={**ROBOT_DATA, "unitStatus": random_status})
    assert robot.status_code == random_status
    assert robot.status == LitterBoxStatus.UNKNOWN
    assert robot.status.value is None
    assert robot.status.text == "Unknown"


async def test_robot_with_drawer_full_status(mock_client):
    """Tests that a robot with a `unitStatus` of DF1/DF2 calls the activity endpoint."""
    robot = await get_robot(mock_client, ROBOT_FULL_ID)
    assert robot.status == LitterBoxStatus.DRAWER_FULL_1
    assert robot.is_waste_drawer_full

    responses = MockedResponses(
        robot_data={UNIT_STATUS: LitterBoxStatus.DRAWER_FULL_2.value}
    )
    with patch(
        "pylitterbot.session.AsyncOAuth2Client.get",
        side_effect=responses.mocked_requests_get,
    ):
        await robot.refresh()
        assert robot.is_waste_drawer_full

        responses.robot_data = {UNIT_STATUS: LitterBoxStatus.DRAWER_FULL.value}
        await robot.refresh()
        assert robot.status == LitterBoxStatus.DRAWER_FULL
        assert robot.is_waste_drawer_full


def test_robot_creation_fails():
    """Tests that robot creation fails if missing information."""
    with pytest.raises(LitterRobotException):
        Robot()


@pytest.mark.parametrize(
    "method_call,dispatch_command,args",
    [
        (Robot.reset_settings, LitterBoxCommand.DEFAULT_SETTINGS, {}),
        (Robot.start_cleaning, LitterBoxCommand.CLEAN, {}),
        (Robot.set_night_light, LitterBoxCommand.NIGHT_LIGHT_ON, {True}),
        (Robot.set_night_light, LitterBoxCommand.NIGHT_LIGHT_OFF, {False}),
        (Robot.set_panel_lockout, LitterBoxCommand.LOCK_ON, {True}),
        (Robot.set_panel_lockout, LitterBoxCommand.LOCK_OFF, {False}),
        (Robot.set_power_status, LitterBoxCommand.POWER_ON, {True}),
        (Robot.set_power_status, LitterBoxCommand.POWER_OFF, {False}),
        (Robot.set_wait_time, LitterBoxCommand.WAIT_TIME + "3", {3}),
        (Robot.set_wait_time, LitterBoxCommand.WAIT_TIME + "7", {7}),
        (Robot.set_wait_time, LitterBoxCommand.WAIT_TIME + "F", {15}),
    ],
)
async def test_dispatch_commands(mock_client, method_call, dispatch_command, args):
    """Tests that the dispatch commands are sent as expected."""
    robot = await get_robot(mock_client)

    await getattr(robot, method_call.__name__)(*args)
    assert mock_client.post.call_args.kwargs.get("json") == {
        "command": f"{LitterBoxCommand._PREFIX}{dispatch_command}"
    }


async def test_other_commands(mock_client):
    """Tests that other various robot commands call as expected."""
    robot = await get_robot(mock_client)

    mock_client.get.reset_mock()
    await robot.refresh()
    mock_client.get.assert_called_once()

    NEW_NAME = "New Name"
    await robot.set_name(NEW_NAME)
    assert robot.name == NEW_NAME

    await robot.set_sleep_mode(False)
    assert mock_client.patch.call_args.kwargs.get("json") == {"sleepModeEnable": False}

    await robot.set_sleep_mode(True)
    json = mock_client.patch.call_args.kwargs.get("json")
    assert json.get("sleepModeEnable")
    assert json.get("sleepModeTime") == robot.sleep_mode_start_time.timestamp()

    assert robot.cycle_count > 0
    await robot.reset_waste_drawer()
    assert robot.cycle_count == 0

    history = await robot.get_activity_history(2)
    assert history
    assert len(history) == 2
    assert str(history[0]) == "2021-03-01T00:01:00+00:00: Ready - 1 cycle"

    insight = await robot.get_insight(2)
    assert insight
    assert len(insight.cycle_history) == 2
    assert (
        str(insight)
        == "Completed 3 cycles averaging 1.5 cycles per day over the last 2 days"
    )


async def test_invalid_commands(mock_client):
    """Tests expected exceptions/responses for invalid commands."""
    robot = await get_robot(mock_client)

    with pytest.raises(InvalidCommandException):
        await robot.set_wait_time(12)

    assert await robot._dispatch_command("W12") is False
    assert mock_client.post.call_args.kwargs.get("json") == {
        "command": f"{LitterBoxCommand._PREFIX}W12"
    }

    with pytest.raises(InvalidCommandException):
        await robot.set_sleep_mode(True, 12)

    with pytest.raises(InvalidCommandException):
        await robot.get_activity_history(0)
