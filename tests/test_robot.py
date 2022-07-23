"""Test robot module."""
import logging
import random
import string
from datetime import datetime, time, timedelta, timezone
from unittest.mock import patch

import pytest
from aiohttp.typedefs import URL
from aioresponses import CallbackResult, aioresponses

from pylitterbot.enums import LitterBoxCommand, LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.robot import (
    DEFAULT_ENDPOINT,
    LR4_ENDPOINT,
    UNIT_STATUS,
    LitterRobot3,
    LitterRobot4,
    Robot,
)
from pylitterbot.session import LitterRobotSession

from .common import (
    COMMAND_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    LITTER_ROBOT_4_DATA,
    ROBOT_DATA,
    ROBOT_FULL_ID,
    ROBOT_ID,
    ROBOT_NAME,
    ROBOT_SERIAL,
    USER_ID,
    get_robot,
)

ROBOT_ENDPOINT = f"{DEFAULT_ENDPOINT}/users/{USER_ID}/robots/%s"


def test_robot_setup():
    """Tests that robot setup is successful and parses as expected."""
    robot = LitterRobot3(data=ROBOT_DATA)
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
        year=2021, month=2, day=1, minute=30, tzinfo=timezone.utc
    )
    assert robot.model == "Litter-Robot 3"
    assert robot.name == ROBOT_NAME
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    assert robot.power_status == "AC"
    assert robot.setup_date == datetime(year=2021, month=1, day=1, tzinfo=timezone.utc)
    assert robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time.timetz() == time(
        hour=22, minute=30, tzinfo=timezone.utc
    )
    assert robot.sleep_mode_end_time.timetz() == time(
        hour=6, minute=30, tzinfo=timezone.utc
    )
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 50


async def test_litter_robot_4_setup(
    mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture
):
    """Tests that a Litter-Robot 4 setup is successful and parses as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA)
    await robot.subscribe_for_updates()

    session = LitterRobotSession()
    robot = LitterRobot4(session=session, data=LITTER_ROBOT_4_DATA)
    await robot.subscribe_for_updates()
    await robot.unsubscribe_from_updates()
    assert robot
    assert str(robot) == "Name: Litter-Robot 4, Serial: LR4C000001, id: LR4ID"
    assert robot.auto_offline_disabled
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_capacity == 58
    assert robot.cycle_count == 93
    assert robot.cycles_after_drawer_full == 0
    assert robot.device_type is None
    assert not robot.did_notify_offline
    assert robot.drawer_full_indicator_cycle_count == 0
    assert not robot.is_drawer_full_indicator_triggered
    assert robot.is_onboarded
    assert not robot.is_sleeping
    assert not robot.is_waste_drawer_full
    assert robot.last_seen == datetime(
        year=2022, month=7, day=20, minute=13, tzinfo=timezone.utc
    )
    assert robot.model == "Litter-Robot 4"
    assert robot.name == "Litter-Robot 4"
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    assert robot.power_status == "AC"
    assert robot.setup_date == datetime(
        year=2022, month=7, day=16, hour=21, minute=40, second=50, tzinfo=timezone.utc
    )
    assert not robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.strftime("%H:%M") == "00:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.strftime("%H:%M") == "00:00"
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 91

    assert await robot.get_activity_history() == []
    insight = await robot.get_insight()
    assert insight.cycle_history == []

    assert await robot.start_cleaning()

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"sendLitterRobot4Command": "Error sending a command"}},
        status=200,
    )
    assert not await robot._dispatch_command("12")
    assert caplog.messages[-1] == "Error sending a command"

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "getLitterRobot4BySerial": {
                    **LITTER_ROBOT_4_DATA,
                    "DFILevelPercent": 99,
                }
            }
        },
    )
    await robot.refresh()
    assert robot.waste_drawer_level == 99

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "sendLitterRobot4Command": 'command "setClumpTime (0x02160007)" sent'
            }
        },
    )
    await robot.set_wait_time(7)
    with pytest.raises(InvalidCommandException):
        await robot.set_wait_time(-1)


def test_robot_with_sleep_mode_time():
    """Tests that robot with `sleepModeTime` is setup correctly."""
    for hour in range(-12, 25, 12):
        with patch(
            "pylitterbot.robot.utcnow",
            return_value=datetime.now(timezone.utc) + timedelta(hours=hour),
        ):
            start_time = datetime.combine(
                datetime.today(), time(hour=12, tzinfo=timezone.utc)
            )

            robot = LitterRobot3(
                data={**ROBOT_DATA, "sleepModeTime": int(start_time.timestamp())}
            )
            assert robot.sleep_mode_start_time.timetz() == start_time.timetz()


def test_robot_with_invalid_sleep_mode_active(caplog):
    """Tests that a robot with an invalid `sleepModeActive` value is setup correctly."""
    invalid_value = "17F"
    robot = LitterRobot3(data={**ROBOT_DATA, "sleepModeActive": invalid_value})
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

    random_status = "_" + "".join(random.sample(string.ascii_letters, 3))

    robot = LitterRobot3(data={**ROBOT_DATA, "unitStatus": random_status})
    assert robot.status_code == random_status
    assert robot.status == LitterBoxStatus.UNKNOWN
    assert robot.status.value is None
    assert robot.status.text == "Unknown"


async def test_robot_with_drawer_full_status(mock_aioresponse):
    """Tests that a robot with a `unitStatus` of DF1/DF2 calls the activity endpoint."""
    url = ROBOT_ENDPOINT % ROBOT_FULL_ID

    robot = await get_robot(ROBOT_FULL_ID)
    robot_status = LitterBoxStatus.DRAWER_FULL_1
    assert robot_status.minimum_cycles_left == 2
    assert robot.status == robot_status
    assert robot.is_waste_drawer_full
    assert robot.cycle_capacity == robot.cycle_count + robot_status.minimum_cycles_left

    robot_status = LitterBoxStatus.DRAWER_FULL_2
    mock_aioresponse.get(url, payload={**ROBOT_DATA, UNIT_STATUS: robot_status.value})
    assert robot_status.minimum_cycles_left == 1
    await robot.refresh()
    assert robot.status == robot_status
    assert robot.is_waste_drawer_full
    assert robot.cycle_capacity == robot.cycle_count + robot_status.minimum_cycles_left

    robot_status = LitterBoxStatus.DRAWER_FULL
    mock_aioresponse.get(url, payload={**ROBOT_DATA, UNIT_STATUS: robot_status.value})
    assert robot_status.minimum_cycles_left == 0
    await robot.refresh()
    assert robot.status == robot_status
    assert robot.is_waste_drawer_full
    assert robot.cycle_capacity == robot.cycle_count + robot_status.minimum_cycles_left

    await robot._session.close()


def test_robot_creation_fails():
    """Tests that robot creation fails if missing information."""
    with pytest.raises(LitterRobotException):
        LitterRobot3()


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
async def test_dispatch_commands(mock_aioresponse, method_call, dispatch_command, args):
    """Tests that the dispatch commands are sent as expected."""
    robot = await get_robot()

    mock_aioresponse.post(
        f"{ROBOT_ENDPOINT % robot.id}{LitterBoxCommand.ENDPOINT}",
        status=200,
        payload=COMMAND_RESPONSE,
    )
    await getattr(robot, method_call.__name__)(*args)
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "command": f"{LitterBoxCommand.PREFIX}{dispatch_command}"
    }
    await robot._session.close()


async def test_other_commands(mock_aioresponse: aioresponses) -> None:
    """Tests that other various robot commands call as expected."""
    robot = await get_robot()
    assert robot._session
    url = ROBOT_ENDPOINT % robot.id

    def patch_callback(_: URL, **kwargs):
        return CallbackResult(payload={**robot._data, **kwargs["json"]})

    mock_aioresponse.patch(url, callback=patch_callback)
    new_name = "New Name"
    await robot.set_name(new_name)
    assert robot.name == new_name

    def patch_callback2(_: URL, **kwargs):
        assert kwargs["json"] == {"sleepModeEnable": False}
        return CallbackResult(payload=robot._data)

    mock_aioresponse.patch(url, callback=patch_callback2)
    await robot.set_sleep_mode(False)

    def patch_callback3(_: URL, **kwargs):
        json = kwargs["json"]
        assert json.get("sleepModeEnable")
        assert robot.sleep_mode_start_time
        assert json.get("sleepModeTime") in (
            robot.sleep_mode_start_time.timestamp(),
            (robot.sleep_mode_start_time + timedelta(hours=24)).timestamp(),
        )
        return CallbackResult(payload={**robot._data, **json})

    mock_aioresponse.patch(url, callback=patch_callback3)
    await robot.set_sleep_mode(True)

    def patch_callback4(_: URL, **kwargs):
        json = kwargs["json"]
        assert json.get("sleepModeEnable")
        assert robot.sleep_mode_start_time
        assert json.get("sleepModeTime") in (
            robot.sleep_mode_start_time.timestamp(),
            (robot.sleep_mode_start_time + timedelta(hours=24)).timestamp(),
        )
        return CallbackResult(payload={**robot._data, **json})

    mock_aioresponse.patch(url, callback=patch_callback4)
    assert robot.sleep_mode_start_time
    await robot.set_sleep_mode(True, robot.sleep_mode_start_time.timetz())

    def patch_callback5(_: URL, **kwargs):
        json = kwargs["json"]
        return CallbackResult(payload={**robot._data, **json})

    mock_aioresponse.patch(url, callback=patch_callback5)
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

    await robot._session.close()


async def test_invalid_commands(mock_aioresponse, caplog: pytest.LogCaptureFixture):
    """Tests expected exceptions/responses for invalid commands."""
    robot = await get_robot()
    url = f"{ROBOT_ENDPOINT % robot.id}{LitterBoxCommand.ENDPOINT}"

    with pytest.raises(InvalidCommandException):
        await robot.set_wait_time(12)

    mock_aioresponse.post(url, payload=INVALID_COMMAND_RESPONSE, status=500)
    assert not await robot._dispatch_command("W12")
    assert "Invalid command: <W12" in caplog.messages[-1]

    mock_aioresponse.post(url, payload={"oops": "no developerMessage"}, status=500)
    assert not await robot._dispatch_command("BAD")
    assert "oops" in caplog.messages[-1]

    with pytest.raises(InvalidCommandException):
        await robot.get_activity_history(0)
    assert robot._session
    await robot._session.close()
