"""Test litterrobot4 module."""

# pylint: disable=protected-access
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
from json import loads
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiohttp import ClientConnectionError
from aiointercept import aiointercept
from freezegun.api import FrozenDateTimeFactory

from pylitterbot import Account
from pylitterbot.enums import LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.robot.litterrobot4 import (
    LITTER_LEVEL_EMPTY,
    LR4_ENDPOINT,
    BrightnessLevel,
    GlobeMotorFaultStatus,
    HopperStatus,
    LitterRobot4,
    LitterRobot4Command,
    NightLightMode,
)

from .common import LITTER_ROBOT_4_DATA

pytestmark = pytest.mark.asyncio


async def test_litter_robot_4(
    mock_aiointercept: aiointercept,
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that a Litter-Robot 4 setup is successful and parses as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)
    await robot.subscribe()
    await robot.unsubscribe()
    assert (
        str(robot)
        == "Name: Litter-Robot 4, Model: Litter-Robot 4, Serial: LR4C000001, id: LR4ID"
    )
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_capacity == 58
    assert robot.cycle_count == 93
    assert robot.cycles_after_drawer_full == 0
    assert robot.firmware == "ESP: 1.1.50 / PIC: 10512.2560.2.51 / TOF: 255.0.255.255"
    assert robot.firmware_update_status == "SUCCEEDED"
    assert not robot.firmware_update_triggered
    assert robot.litter_level == 40.0
    assert not robot.is_drawer_full_indicator_triggered
    assert not robot.is_laser_dirty
    assert robot.globe_motor_fault_status == GlobeMotorFaultStatus.FAULT_CLEAR
    assert robot.globe_motor_retract_fault_status == GlobeMotorFaultStatus.FAULT_CLEAR
    assert robot.is_on
    assert robot.is_onboarded
    assert robot.is_online
    assert not robot.is_sleeping
    assert not robot.is_waste_drawer_full
    assert robot.last_seen == datetime(
        year=2022, month=7, day=20, minute=13, tzinfo=timezone.utc
    )
    assert robot.model == "Litter-Robot 4"
    assert robot.name == "Litter-Robot 4"
    assert robot.night_light_brightness == 100
    assert robot.night_light_level == BrightnessLevel.HIGH
    assert robot.night_light_mode == NightLightMode.AUTO
    assert robot.night_light_mode_enabled
    assert robot.panel_brightness == BrightnessLevel.HIGH
    assert not robot.panel_lock_enabled
    assert robot.pet_weight == 7.93
    with pytest.warns(DeprecationWarning, match="power_type"):
        assert robot.power_status == "AC"
    assert robot.power_type == "AC"
    assert robot.setup_date == datetime(
        year=2022, month=7, day=16, hour=21, minute=40, tzinfo=timezone.utc
    )
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 91

    assert await robot.start_cleaning()

    mock_aiointercept.clear()
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "getLitterRobot4Activity": [
                    {
                        "timestamp": "2022-09-17 20:53:32.000000000",
                        "value": "robotCycleStatusIdle",
                        "actionValue": "",
                    },
                    {
                        "timestamp": "2022-09-17 20:51:18.000000000",
                        "value": "robotCycleStatusDump",
                        "actionValue": "",
                    },
                    {
                        "timestamp": "2022-09-17 20:44:18.000000000",
                        "value": "catWeight",
                        "actionValue": "6.35",
                    },
                    {
                        "timestamp": "2022-09-17 20:40:07.000000000",
                        "value": "odometerCleanCycles",
                        "actionValue": "42",
                    },
                    {
                        "timestamp": "2022-09-17 20:39:56.000000000",
                        "value": "litterHopperDispensed",
                        "actionValue": "84",
                    },
                ]
            }
        },
    )
    activities = await robot.get_activity_history(5)
    assert len(activities) == 5
    assert activities[0].action == LitterBoxStatus.CLEAN_CYCLE_COMPLETE
    assert activities[2].action == "Pet Weight Recorded: 6.35 lbs"
    assert activities[3].action == "Clean Cycles: 42"
    assert activities[4].action == "Litter Dispensed: 84"
    with pytest.raises(InvalidCommandException):
        await robot.get_activity_history(0)

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "getLitterRobot4Insights": {
                    "totalCycles": 35,
                    "averageCycles": 5,
                    "cycleHistory": [
                        {"date": "2022-09-08", "numberOfCycles": 5},
                        {"date": "2022-09-07", "numberOfCycles": 6},
                        {"date": "2022-09-06", "numberOfCycles": 4},
                        {"date": "2022-09-05", "numberOfCycles": 4},
                        {"date": "2022-09-04", "numberOfCycles": 5},
                        {"date": "2022-09-03", "numberOfCycles": 6},
                        {"date": "2022-09-02", "numberOfCycles": 5},
                    ],
                    "totalCatDetections": 35,
                }
            }
        },
    )
    insight = await robot.get_insight(days=7)
    assert len(insight.cycle_history) == 7

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={"data": {"getLitterRobot4Insights": None}},
    )
    with pytest.raises(LitterRobotException):
        await robot.get_insight(days=7)

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={"data": {"sendLitterRobot4Command": "Error sending a command"}},
    )
    assert not await robot._dispatch_command("12")
    assert caplog.messages[-1] == "Error sending a command"

    error_message = "sendLitterRobot4Command: Robot not online: LR4C000001"
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {"sendLitterRobot4Command": None},
            "errors": [{"message": error_message}],
        },
    )
    assert not await robot.set_night_light_brightness(100)
    assert caplog.messages[-1] == error_message

    # test multiple errors in message
    error_message2 = "sendLitterRobot4Command: Robot still offline: LR4C000001"
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {"sendLitterRobot4Command": None},
            "errors": [{"message": error_message}, {"message": error_message2}],
        },
    )
    assert not await robot.set_night_light_brightness(100)
    assert caplog.messages[-1] == f"{error_message}, {error_message2}"

    mock_aiointercept.post(
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

    mock_aiointercept.post(
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

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "getLitterRobot4BySerial": {
                    **LITTER_ROBOT_4_DATA,
                    "nightLightBrightness": 10,
                    "nightLightMode": "TEST",
                    "panelBrightnessHigh": None,
                    "isDFIFull": True,
                }
            }
        },
    )
    await robot.refresh()
    assert robot.night_light_brightness == 10
    assert robot.night_light_level is None
    assert robot.night_light_mode is None  # type: ignore[unreachable]
    assert robot.panel_brightness is None
    assert robot.status == LitterBoxStatus.DRAWER_FULL

    new_name = "Test Name"
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={"data": {"updateLitterRobot4": {"name": new_name}}},
    )
    assert robot.name != new_name
    assert await robot.set_name(new_name)
    assert robot.name == new_name

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "sendLitterRobot4Command": 'command "setNightLightValue (0x02190055)" sent'
            }
        },
    )
    await robot.set_night_light_brightness(25)
    with pytest.raises(InvalidCommandException):
        await robot.set_night_light_brightness(20)

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "sendLitterRobot4Command": 'command "nightLightModeAuto (0x02180002)" sent'
            }
        },
    )
    await robot.set_night_light_mode(NightLightMode.AUTO)

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "sendLitterRobot4Command": 'command "panelBrightnessHigh (0x020E5A64)" sent'
            }
        },
    )
    await robot.set_panel_brightness(BrightnessLevel.HIGH)

    version_info = {
        "isEspFirmwareUpdateNeeded": True,
        "isPicFirmwareUpdateNeeded": True,
        "isLaserboardFirmwareUpdateNeeded": False,
        "latestFirmware": {
            "espFirmwareVersion": "1.1.54",
            "picFirmwareVersion": "10512.2560.2.66",
            "laserBoardFirmwareVersion": "4.0.65.4",
        },
    }
    firmware_response = {"data": {"litterRobot4CompareFirmwareVersion": version_info}}
    mock_aiointercept.post(LR4_ENDPOINT, payload=firmware_response)
    assert await robot.has_firmware_update()

    version_info["isEspFirmwareUpdateNeeded"] = False
    version_info["isPicFirmwareUpdateNeeded"] = False
    mock_aiointercept.post(LR4_ENDPOINT, payload=firmware_response)
    assert not await robot.has_firmware_update(True)
    latest_firmware = await robot.get_latest_firmware()
    assert latest_firmware == "ESP: 1.1.54 / PIC: 10512.2560.2.66 / TOF: 4.0.65.4"

    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "litterRobot4TriggerFirmwareUpdate": {
                    "isEspFirmwareUpdateNeeded": True,
                    "isLaserboardFirmwareUpdateNeeded": False,
                    "isPicFirmwareUpdateNeeded": True,
                    "isUpdateTriggered": True,
                }
            }
        },
    )
    assert await robot.update_firmware()
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "litterRobot4TriggerFirmwareUpdate": {
                    "isEspFirmwareUpdateNeeded": False,
                    "isLaserboardFirmwareUpdateNeeded": False,
                    "isPicFirmwareUpdateNeeded": False,
                    "isUpdateTriggered": False,
                }
            }
        },
    )
    assert not await robot.update_firmware()

    firmware_response = {
        "data": {"litterRobot4CompareFirmwareVersion": None},
        "errors": [
            {
                "path": ["litterRobot4CompareFirmwareVersion"],
                "errorType": "Error",
                "message": "validateFirmwareForRobotDetails: Robot has already active Firmware Update",
            }
        ],
    }
    mock_aiointercept.post(LR4_ENDPOINT, payload=firmware_response, repeat=True)
    assert not await robot.has_firmware_update(True)
    assert not await robot.get_latest_firmware()

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "start,expected_start_timestamp",
    [
        (None, None),
        (
            datetime(2022, 9, 10, 8, 30, 15, tzinfo=timezone.utc),
            "2022-09-10 08:30:15",
        ),
        (datetime(2022, 9, 10, 8, 30, 15), "2022-09-10 08:30:15"),
        (
            datetime(2022, 9, 10, 1, 30, 15, tzinfo=timezone(timedelta(hours=-7))),
            "2022-09-10 08:30:15",
        ),
        (
            datetime(2022, 9, 10, 8, 30, 15, 123456, tzinfo=timezone.utc),
            "2022-09-10 08:30:16",
        ),
        (
            datetime(2022, 9, 10, 23, 59, 59, 1, tzinfo=timezone.utc),
            "2022-09-11 00:00:00",
        ),
    ],
    ids=[
        "no_start",
        "utc",
        "naive_as_utc",
        "offset_converted_to_utc",
        "fraction_rounds_up",
        "fraction_rounds_up_across_midnight",
    ],
)
async def test_litter_robot_4_activity_history_start(
    mock_aiointercept: aiointercept,
    mock_account: Account,
    start: datetime | None,
    expected_start_timestamp: str | None,
) -> None:
    """Tests that the activity history start is sent in the format the API accepts."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aiointercept.clear()
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "getLitterRobot4Activity": [
                    {
                        "timestamp": "2022-09-17 20:53:32.000000000",
                        "value": "robotCycleStatusIdle",
                        "actionValue": "",
                    }
                ]
            }
        },
    )

    activities = await robot.get_activity_history(limit=10, start=start)
    assert len(activities) == 1

    json = list(mock_aiointercept.requests.items())[-1][-1][-1].kwargs.get("json", {})
    variables = json.get("variables", {})
    assert variables.get("limit") == 10
    assert variables.get("startTimestamp") == expected_start_timestamp
    if start is None:
        assert "startTimestamp" not in variables

    await robot._account.disconnect()


async def test_litter_robot_4_websocket_subscription_payload() -> None:
    """LR4 WebSocket data frames use litterRobot4StateSubscriptionByUser."""
    states = [{**LITTER_ROBOT_4_DATA, "DFILevelPercent": 50}]
    message = {
        "type": "data",
        "payload": {
            "data": {"litterRobot4StateSubscriptionByUser": {"robots": states}}
        },
    }
    assert LitterRobot4.parse_websocket_message(message) == states
    assert LitterRobot4._WS_PROTOCOL.is_shared


async def test_litter_robot_4_shared_subscription_dispatch(
    mock_account: Account,
) -> None:
    """A ByUser array payload updates each LR4 listener with its own entry."""
    data_a = {**LITTER_ROBOT_4_DATA, "unitId": "LR4ID-A"}
    data_b = {**LITTER_ROBOT_4_DATA, "unitId": "LR4ID-B"}
    robot_a = LitterRobot4(data=data_a, account=mock_account)
    robot_b = LitterRobot4(data=data_b, account=mock_account)
    message = {
        "type": "data",
        "payload": {
            "data": {
                "litterRobot4StateSubscriptionByUser": {
                    "robots": [
                        {**data_a, "DFILevelPercent": 42},
                        {**data_b, "DFILevelPercent": 99},
                    ]
                }
            }
        },
    }
    robot_a._ws_message_handler(message)
    robot_b._ws_message_handler(message)
    assert robot_a.waste_drawer_level == 42
    assert robot_b.waste_drawer_level == 99


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), (None, False)],
)
async def test_litter_robot_4_laser_dirty(
    mock_account: Account, value: bool | None, expected: bool
) -> None:
    """Tests that the laser dirty flag is read from the robot data."""
    data = {**LITTER_ROBOT_4_DATA, "isLaserDirty": value}
    robot = LitterRobot4(data=data, account=mock_account)
    assert robot.is_laser_dirty is expected

    await robot._account.disconnect()


async def test_litter_robot_4_set_sleep_mode(mock_account: Account) -> None:
    """Tests setting the sleep schedule on a Litter-Robot 4."""
    data = deepcopy(LITTER_ROBOT_4_DATA)
    data["weekdaySleepModeEnabled"] = {
        day: {"sleepTime": 0, "wakeTime": 0, "isEnabled": False}
        for day in (
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
        )
    }
    robot = LitterRobot4(data=data, account=mock_account)
    assert not robot.sleep_mode_enabled
    post = AsyncMock(return_value={"data": {"sendLitterRobot4Command": "ok"}})
    robot._post = post  # type: ignore[method-assign]

    def last_days() -> list[dict]:
        variables = post.call_args.kwargs["json"]["variables"]
        assert variables["command"] == LitterRobot4Command.SET_SLEEP_WAKE_TIMES
        days: list[dict] = loads(variables["value"])["days"]
        return days

    # Enable sleep for all days
    assert await robot.set_sleep_mode(True, time(22, 30), wake_time=420)
    assert robot.sleep_mode_enabled
    assert (  # type: ignore[unreachable]
        last_days() == [{"sleepMinutes": 1350, "wakeMinutes": 420, "enabled": True}] * 7
    )

    # Disable sleep for all days, keeping the times
    assert await robot.set_sleep_mode(False)
    assert not robot.sleep_mode_enabled
    assert (
        last_days()
        == [{"sleepMinutes": 1350, "wakeMinutes": 420, "enabled": False}] * 7
    )

    # Enable sleep for Saturday only, which is the last day sent
    assert await robot.set_sleep_mode(True, 60, wake_time=120, day_of_week=6)
    days = last_days()
    assert days[6] == {"sleepMinutes": 60, "wakeMinutes": 120, "enabled": True}
    assert (
        days[:6] == [{"sleepMinutes": 1350, "wakeMinutes": 420, "enabled": False}] * 6
    )
    schedule = robot._data["weekdaySleepModeEnabled"]
    assert schedule["Saturday"] == {"sleepTime": 60, "wakeTime": 120, "isEnabled": True}
    assert not schedule["Sunday"]["isEnabled"]

    await robot._account.disconnect()


async def test_litter_robot_4_set_sleep_mode_failure(mock_account: Account) -> None:
    """Tests that a rejected command leaves the schedule unchanged."""
    robot = LitterRobot4(data=deepcopy(LITTER_ROBOT_4_DATA), account=mock_account)
    schedule = deepcopy(robot._data["weekdaySleepModeEnabled"])

    robot._post = AsyncMock(  # type: ignore[method-assign]
        return_value={"data": {"sendLitterRobot4Command": "Error sending a command"}}
    )
    assert not await robot.set_sleep_mode(False)
    assert robot._data["weekdaySleepModeEnabled"] == schedule

    robot._post = AsyncMock(  # type: ignore[method-assign]
        side_effect=ClientConnectionError("down")
    )
    assert not await robot.set_sleep_mode(False)
    assert robot._data["weekdaySleepModeEnabled"] == schedule

    await robot._account.disconnect()


@pytest.mark.parametrize("day_of_week", [-1, 7])
async def test_litter_robot_4_set_sleep_mode_invalid_day(
    mock_account: Account, day_of_week: int
) -> None:
    """Tests that an invalid day is rejected before anything is sent."""
    robot = LitterRobot4(data=deepcopy(LITTER_ROBOT_4_DATA), account=mock_account)
    post = AsyncMock()
    robot._post = post  # type: ignore[method-assign]

    with pytest.raises(InvalidCommandException, match="day_of_week"):
        await robot.set_sleep_mode(True, day_of_week=day_of_week)
    post.assert_not_awaited()

    await robot._account.disconnect()


async def test_litter_robot_4_sleep_time(
    freezer: FrozenDateTimeFactory, mock_account: Account
) -> None:
    """Tests that a Litter-Robot 4 parses sleep time as expected."""
    freezer.move_to("2022-07-21 12:00:00-06:00")
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)
    assert robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-21T23:30:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-21T07:30:00-06:00"

    freezer.move_to("2022-07-23 12:00:00-06:00")
    assert robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-24T00:00:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-22T07:30:00-06:00"

    freezer.move_to("2022-07-24 08:00:00-06:00")
    assert robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-24T00:00:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-24T08:30:00-06:00"


async def test_litter_robot_4_sleep_time_full_day(
    freezer: FrozenDateTimeFactory, mock_account: Account
) -> None:
    """Tests that matching sleep and wake times are a full day of sleep."""
    days = (
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    )
    schedule = {
        day: {"sleepTime": 10, "wakeTime": 10, "isEnabled": True} for day in days
    }
    mountain = timezone(timedelta(hours=-6))
    freezer.move_to("2022-07-24 12:00:00-06:00")
    robot = LitterRobot4(
        data={**LITTER_ROBOT_4_DATA, "weekdaySleepModeEnabled": schedule},
        account=mock_account,
    )
    assert robot.sleep_schedule
    assert robot.sleep_schedule.is_active(datetime.now(mountain))
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-24T00:10:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-25T00:10:00-06:00"

    freezer.move_to("2022-07-25 00:10:00-06:00")
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-24T00:10:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-25T00:10:00-06:00"

    freezer.move_to("2022-07-25 00:10:01-06:00")
    assert robot.sleep_schedule.is_active(datetime.now(mountain))
    assert robot.sleep_mode_start_time
    assert robot.sleep_mode_start_time.isoformat() == "2022-07-25T00:10:00-06:00"
    assert robot.sleep_mode_end_time
    assert robot.sleep_mode_end_time.isoformat() == "2022-07-26T00:10:00-06:00"

    await robot._account.disconnect()


async def test_litter_robot_4_cleaning(mock_account: Account) -> None:
    """Tests Litter-Robot 4 in clean mode."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)
    assert robot.status == LitterBoxStatus.READY
    assert robot.litter_level == 40
    assert robot.litter_level_calculated == 40

    # simulate update to cleaning
    robot._update_data({"robotStatus": "ROBOT_CLEAN"}, partial=True)
    status = LitterBoxStatus.CLEAN_CYCLE
    assert robot.status == status
    assert robot.status_code == "CCP"
    assert robot.litter_level == 40
    assert robot.litter_level_calculated == 40

    # simulate litter level read mid-cycle
    robot._update_data({"litterLevel": LITTER_LEVEL_EMPTY}, partial=True)
    assert robot.litter_level == 40
    assert robot.litter_level_calculated == 40

    # simulate stopped cleaning
    robot._update_data({"robotStatus": "ROBOT_IDLE"}, partial=True)
    assert robot.status == LitterBoxStatus.READY
    assert robot.litter_level == 40
    assert robot.litter_level_calculated == 40

    # simulate litter level read after clean
    robot._update_data({"litterLevel": 481, "litterLevelPercentage": 0.3}, partial=True)
    assert robot.status == LitterBoxStatus.READY
    assert robot.litter_level == 30
    assert robot.litter_level_calculated == 30


@pytest.mark.parametrize(
    "method_call,dispatch_command,mock_response_data,args",
    [
        (
            LitterRobot4.reset,
            LitterRobot4Command.SHORT_RESET_PRESS,
            {"sendLitterRobot4Command": 'command "shortResetPress (0x02010401)" sent'},
            {},
        ),
    ],
)
async def test_litter_robot_4_commands(
    mock_aiointercept: aiointercept,
    mock_account: Account,
    method_call: Callable,
    dispatch_command: str,
    mock_response_data: dict,
    args: Any,
) -> None:
    """Tests that commands for Litter-Robot 4 are sent as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aiointercept.clear()
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={"data": mock_response_data},
    )

    await getattr(robot, method_call.__name__)(*args)

    json = list(mock_aiointercept.requests.items())[-1][-1][-1].kwargs.get("json", {})
    assert "sendLitterRobot4Command" in json.get("query", "")
    assert json.get("variables", {}).get("command") == dispatch_command

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "is_removed,mock_mutation_response_data,expected_is_hopper_removed,expected_hopper_status,expected_return",
    [
        (
            True,
            {"toggleHopper": {"success": True}},
            True,
            HopperStatus.DISABLED,
            True,
        ),
        (
            False,
            {"toggleHopper": {"success": True}},
            False,
            HopperStatus.ENABLED,
            True,
        ),
        (
            True,
            {"toggleHopper": {"success": False}},
            False,
            None,
            False,
        ),
        (
            False,
            {"toggleHopper": {"success": False}},
            False,
            None,
            False,
        ),
    ],
)
async def test_litter_hopper_toggle(
    mock_aiointercept: aiointercept,
    mock_account: Account,
    is_removed: bool,
    mock_mutation_response_data: dict,
    expected_is_hopper_removed: bool | None,
    expected_hopper_status: HopperStatus | None,
    expected_return: bool,
) -> None:
    """Tests that LitterHopper toggling works as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aiointercept.clear()
    mock_aiointercept.post(
        LR4_ENDPOINT,
        payload={"data": mock_mutation_response_data},
    )

    assert (await robot.toggle_hopper(is_removed)) is expected_return
    assert robot.hopper_status == expected_hopper_status
    assert robot.is_hopper_removed is expected_is_hopper_removed

    json = list(mock_aiointercept.requests.items())[-1][-1][0].kwargs.get("json", {})
    assert "toggleHopper" in json.get("query", "")
    assert json.get("variables", {}).get("isRemoved") == is_removed

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "updated_data,status",
    [
        ({"isDFIFull": True}, LitterBoxStatus.DRAWER_FULL),
        ({"isOnline": False}, LitterBoxStatus.OFFLINE),
        (
            {"isOnline": False, "robotCycleState": "CYCLE_STATE_PAUSE"},
            LitterBoxStatus.OFFLINE,
        ),
        ({"robotCycleState": "CYCLE_STATE_PAUSE"}, LitterBoxStatus.PAUSED),
        (
            {"robotCycleState": "CYCLE_STATE_PAUSE", "robotStatus": "ROBOT_CLEAN"},
            LitterBoxStatus.PAUSED,
        ),
        (
            {"robotCycleState": "CYCLE_STATE_CAT_DETECT"},
            LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
        ),
        ({"robotStatus": "ROBOT_BONNET"}, LitterBoxStatus.BONNET_REMOVED),
        ({"robotStatus": "ROBOT_CAT_DETECT"}, LitterBoxStatus.CAT_DETECTED),
        ({"robotStatus": "ROBOT_CAT_DETECT_DELAY"}, LitterBoxStatus.CAT_SENSOR_TIMING),
        ({"robotStatus": "ROBOT_CLEAN"}, LitterBoxStatus.CLEAN_CYCLE),
        ({"robotStatus": "ROBOT_EMPTY"}, LitterBoxStatus.EMPTY_CYCLE),
        ({"robotStatus": "ROBOT_FIND_DUMP"}, LitterBoxStatus.CLEAN_CYCLE),
        ({"robotStatus": "ROBOT_IDLE"}, LitterBoxStatus.READY),
        ({"robotStatus": "ROBOT_POWER_DOWN"}, LitterBoxStatus.POWER_DOWN),
        ({"robotStatus": "ROBOT_POWER_OFF"}, LitterBoxStatus.OFF),
        ({"robotStatus": "ROBOT_POWER_UP"}, LitterBoxStatus.POWER_UP),
        ({"displayCode": "DC_CAT_DETECT"}, LitterBoxStatus.CAT_DETECTED),
        (
            {"displayCode": "DC_CAT_DETECT", "robotStatus": "ROBOT_CAT_DETECT_DELAY"},
            LitterBoxStatus.CAT_SENSOR_TIMING,
        ),
        (
            {
                "displayCode": "DC_CAT_DETECT",
                "robotCycleState": "CYCLE_STATE_CAT_DETECT",
            },
            LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
        ),
        (
            {"robotCycleState": "CYCLE_STATE_PAUSE", "unitPowerStatus": "OFF"},
            LitterBoxStatus.OFF,
        ),
        ({"displayCode": "DC_MTR_FAULT_PINCH"}, LitterBoxStatus.PINCH_DETECT),
        ({"displayCode": "DC_MTR_FAULT_OT_AMP"}, LitterBoxStatus.OVER_TORQUE_FAULT),
        ({"displayCode": "DC_MTR_FAULT_OT_SLP"}, LitterBoxStatus.OVER_TORQUE_FAULT),
        (
            {
                "displayCode": "DC_CAT_DETECT_30M",
                "robotStatus": "ROBOT_CAT_DETECT_DELAY",
            },
            LitterBoxStatus.CAT_SENSOR_FAULT,
        ),
        (
            {
                "displayCode": "DC_MTR_FAULT_PINCH",
                "robotCycleState": "CYCLE_STATE_CAT_DETECT",
            },
            LitterBoxStatus.PINCH_DETECT,
        ),
        (
            {"displayCode": "DC_MTR_FAULT_PINCH", "isOnline": False},
            LitterBoxStatus.OFFLINE,
        ),
        (
            {"displayCode": "DC_MTR_FAULT_PINCH", "unitPowerStatus": "OFF"},
            LitterBoxStatus.OFF,
        ),
        (
            {"displayCode": "DC_MODE_IDLE", "globeMotorFaultStatus": "FAULT_TIMEOUT"},
            LitterBoxStatus.READY,
        ),
    ],
)
async def test_litter_robot_4_status(
    mock_account: Account, updated_data: dict[str, str | bool], status: LitterBoxStatus
) -> None:
    """Tests Litter-Robot 4 in various statuses."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)
    assert robot.status == LitterBoxStatus.READY

    # update data and assert expected result
    robot._update_data(updated_data, partial=True)
    assert robot.status == status


async def test_litter_robot_4_status_fault_clears(mock_account: Account) -> None:
    """Tests that a fault status ends when the panel returns to idle."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    robot._update_data({"displayCode": "DC_MTR_FAULT_PINCH"}, partial=True)
    statuses = [robot.status]

    robot._update_data({"displayCode": "DC_MODE_IDLE"}, partial=True)
    statuses.append(robot.status)

    assert statuses == [LitterBoxStatus.PINCH_DETECT, LitterBoxStatus.READY]

    await robot._account.disconnect()


async def test_litter_robot_4_status_without_display_code(
    mock_account: Account,
) -> None:
    """Tests that a missing display code doesn't prevent reporting a status."""
    data = {**LITTER_ROBOT_4_DATA, "robotCycleState": "CYCLE_STATE_PAUSE"}
    del data["displayCode"]
    robot = LitterRobot4(data=data, account=mock_account)
    assert robot.status == LitterBoxStatus.PAUSED

    await robot._account.disconnect()
