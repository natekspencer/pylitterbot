"""Test robot module."""

# pylint: disable=protected-access
import asyncio
import logging
import random
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from string import ascii_letters
from typing import Any
from unittest.mock import patch

import pytest
from aiohttp.typedefs import URL
from aioresponses import CallbackResult, aioresponses

from pylitterbot import Account
from pylitterbot.enums import LitterBoxCommand, LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException
from pylitterbot.robot import EVENT_UPDATE
from pylitterbot.robot.litterrobot3 import UNIT_STATUS, LitterRobot, LitterRobot3

from .common import (
    COMMAND_RESPONSE,
    INVALID_COMMAND_RESPONSE,
    ROBOT_DATA,
    ROBOT_DELETED_DATA,
    ROBOT_ENDPOINT,
    ROBOT_FULL_ID,
    ROBOT_ID,
    ROBOT_NAME,
    ROBOT_SERIAL,
    get_robot,
)

pytestmark = pytest.mark.asyncio


async def test_robot_setup(mock_account: Account) -> None:
    """Tests that robot setup is successful and parses as expected."""
    robot = LitterRobot3(data=ROBOT_DATA, account=mock_account)
    assert robot
    assert (
        str(robot)
        == f"Name: {ROBOT_NAME}, Model: Litter-Robot 3, Serial: {ROBOT_SERIAL}, id: {ROBOT_ID}"
    )
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_capacity == 30
    assert robot.cycle_count == 15
    assert robot.cycles_after_drawer_full == 0
    assert not robot.is_drawer_full_indicator_triggered
    assert robot.is_onboarded
    assert robot.is_online
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
    assert robot.sleep_mode_start_time and robot.sleep_mode_start_time.timetz() == time(
        hour=22, minute=30, tzinfo=timezone.utc
    )
    assert robot.sleep_mode_end_time and robot.sleep_mode_end_time.timetz() == time(
        hour=6, minute=30, tzinfo=timezone.utc
    )
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 50


async def test_robot_with_zero_cycle_capacity(mock_account: Account) -> None:
    """Tests that a robot with zero cycle capacity doesn't cause an error."""
    data = {**ROBOT_DATA, "cycleCount": 0, "unitStatus": "DFS"}
    robot = LitterRobot3(data=data, account=mock_account)
    assert robot.cycle_capacity == 0
    assert robot.waste_drawer_level == 100


async def test_robot_with_sleep_mode_time(mock_account: Account) -> None:
    """Tests that robot with `sleepModeTime` is setup correctly."""
    for hour in range(-12, 25, 12):
        with patch(
            "pylitterbot.utils.utcnow",
            return_value=datetime.now(timezone.utc) + timedelta(hours=hour),
        ):
            start_time = datetime.combine(
                datetime.today(), time(hour=12, tzinfo=timezone.utc)
            )

            robot = LitterRobot3(
                data={**ROBOT_DATA, "sleepModeTime": int(start_time.timestamp())},
                account=mock_account,
            )
            assert (
                robot.sleep_mode_start_time
                and robot.sleep_mode_start_time.timetz() == start_time.timetz()
            )


async def test_robot_with_invalid_sleep_mode_active(
    mock_account: Account, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that a robot with an invalid `sleepModeActive` value is setup correctly."""
    invalid_value = "17F"
    robot = LitterRobot3(
        data={**ROBOT_DATA, "sleepModeActive": invalid_value}, account=mock_account
    )
    assert caplog.record_tuples == [
        (
            "pylitterbot.robot.litterrobot3",
            logging.ERROR,
            f"Unable to parse sleep mode start time from value '{invalid_value}'",
        )
    ]
    assert robot.sleep_mode_start_time is None


async def test_robot_with_unknown_status(mock_account: Account) -> None:
    """Tests that a robot with an unknown `unitStatus` is setup correctly."""
    random_status = "_" + "".join(random.sample(ascii_letters, 3))

    robot = LitterRobot3(
        data={**ROBOT_DATA, "unitStatus": random_status}, account=mock_account
    )
    assert robot.status_code == random_status
    assert robot.status == LitterBoxStatus.UNKNOWN
    assert robot.status.value is None
    assert robot.status.text == "Unknown"


async def test_robot_with_drawer_full_status(mock_aioresponse: aioresponses) -> None:
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

    await robot._account.disconnect()


async def test_robot_deleted(mock_account: Account) -> None:
    """Tests that robot setup for a deleted robot without serial number throws an error."""
    with pytest.raises(ValueError):
        LitterRobot3(data=ROBOT_DELETED_DATA, account=mock_account)


@pytest.mark.parametrize(
    "method_call,dispatch_command,args",
    [
        (LitterRobot.reset_settings, LitterBoxCommand.DEFAULT_SETTINGS, {}),
        (LitterRobot.start_cleaning, LitterBoxCommand.CLEAN, {}),
        (LitterRobot.set_night_light, LitterBoxCommand.NIGHT_LIGHT_ON, {True}),
        (LitterRobot.set_night_light, LitterBoxCommand.NIGHT_LIGHT_OFF, {False}),
        (LitterRobot.set_panel_lockout, LitterBoxCommand.LOCK_ON, {True}),
        (LitterRobot.set_panel_lockout, LitterBoxCommand.LOCK_OFF, {False}),
        (LitterRobot.set_power_status, LitterBoxCommand.POWER_ON, {True}),
        (LitterRobot.set_power_status, LitterBoxCommand.POWER_OFF, {False}),
        (LitterRobot.set_wait_time, LitterBoxCommand.WAIT_TIME + "3", {3}),
        (LitterRobot.set_wait_time, LitterBoxCommand.WAIT_TIME + "7", {7}),
        (LitterRobot.set_wait_time, LitterBoxCommand.WAIT_TIME + "F", {15}),
    ],
)
async def test_dispatch_commands(
    mock_aioresponse: aioresponses,
    method_call: Callable,
    dispatch_command: str,
    args: Any,
) -> None:
    """Tests that the dispatch commands are sent as expected."""
    robot = await get_robot()

    mock_aioresponse.post(
        f"{ROBOT_ENDPOINT % robot.id}/{LitterBoxCommand.ENDPOINT}",
        payload=COMMAND_RESPONSE,
    )
    await getattr(robot, method_call.__name__)(*args)
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "command": f"{LitterBoxCommand.PREFIX}{dispatch_command}"
    }
    await robot._account.disconnect()


async def test_other_commands(mock_aioresponse: aioresponses) -> None:
    """Tests that other various robot commands call as expected."""
    robot = await get_robot()
    url = ROBOT_ENDPOINT % robot.id

    def patch_callback(_: URL, **kwargs: Any) -> CallbackResult:
        return CallbackResult(payload={**robot._data, **kwargs["json"]})

    mock_aioresponse.patch(url, callback=patch_callback)
    new_name = "New Name"
    await robot.set_name(new_name)
    assert robot.name == new_name

    def patch_callback2(_: URL, **kwargs: Any) -> CallbackResult:
        assert kwargs["json"] == {"sleepModeEnable": False}
        return CallbackResult(payload=robot._data)

    mock_aioresponse.patch(url, callback=patch_callback2)
    await robot.set_sleep_mode(False)

    def patch_callback3(_: URL, **kwargs: Any) -> CallbackResult:
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

    def patch_callback4(_: URL, **kwargs: Any) -> CallbackResult:
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

    def patch_callback5(_: URL, **kwargs: Any) -> CallbackResult:
        json = kwargs["json"]
        return CallbackResult(payload={**robot._data, **json})

    mock_aioresponse.patch(url, callback=patch_callback5)
    assert robot.cycle_count > 0
    if isinstance(robot, LitterRobot3):
        await robot.reset_waste_drawer()
    assert robot.cycle_count == 0

    history = await robot.get_activity_history(2)
    assert history
    assert len(history) == 2
    assert str(history[0]) == "2021-03-01T00:01:00+00:00: Ready"

    insight = await robot.get_insight(2)
    assert insight
    assert len(insight.cycle_history) == 2
    assert (
        str(insight)
        == "Completed 3 cycles averaging 1.5 cycles per day over the last 2 days"
    )

    await robot._account.disconnect()


async def test_invalid_commands(
    mock_aioresponse: aioresponses, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests expected exceptions/responses for invalid commands."""
    robot = await get_robot()
    url = f"{ROBOT_ENDPOINT % robot.id}/{LitterBoxCommand.ENDPOINT}"

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
    await robot._account.disconnect()


async def test_robot_update_event(mock_account: Account) -> None:
    """Test robot emits an update event."""
    robot = LitterRobot3(data=ROBOT_DATA, account=mock_account)
    assert not robot._listeners
    event = asyncio.Event()
    unsub = robot.on(EVENT_UPDATE, event.set)

    assert not event.is_set()
    robot._update_data({**ROBOT_DATA, "foo": "bar"})
    assert event.is_set()

    unsub()
    assert not robot._listeners[EVENT_UPDATE]
