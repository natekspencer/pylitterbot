"""Test litterrobot4 module."""

# pylint: disable=protected-access
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pytest
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.enums import LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.robot.litterrobot4 import (
    LITTER_LEVEL_EMPTY,
    LR4_ENDPOINT,
    BrightnessLevel,
    HopperStatus,
    LitterRobot4,
    LitterRobot4Command,
    NightLightMode,
)

from .common import LITTER_ROBOT_4_DATA

pytestmark = pytest.mark.asyncio


async def test_litter_robot_4(
    mock_aioresponse: aioresponses,
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
    assert robot.power_status == "AC"
    assert robot.setup_date == datetime(
        year=2022, month=7, day=16, hour=21, minute=40, tzinfo=timezone.utc
    )
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.waste_drawer_level == 91

    assert await robot.start_cleaning()

    mock_aioresponse.clear()
    mock_aioresponse.post(
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
                ]
            }
        },
    )
    activities = await robot.get_activity_history(3)
    assert len(activities) == 3
    assert activities[0].action == LitterBoxStatus.CLEAN_CYCLE_COMPLETE
    assert activities[2].action == "Pet Weight Recorded: 6.35 lbs"
    with pytest.raises(InvalidCommandException):
        await robot.get_activity_history(0)

    mock_aioresponse.post(
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

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"getLitterRobot4Insights": None}},
    )
    with pytest.raises(LitterRobotException):
        await robot.get_insight(days=7)

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"sendLitterRobot4Command": "Error sending a command"}},
    )
    assert not await robot._dispatch_command("12")
    assert caplog.messages[-1] == "Error sending a command"

    error_message = "sendLitterRobot4Command: Robot not online: LR4C000001"
    mock_aioresponse.post(
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
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {"sendLitterRobot4Command": None},
            "errors": [{"message": error_message}, {"message": error_message2}],
        },
    )
    assert not await robot.set_night_light_brightness(100)
    assert caplog.messages[-1] == f"{error_message}, {error_message2}"

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

    mock_aioresponse.post(
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
    assert robot.night_light_mode is None  # type: ignore
    assert robot.panel_brightness is None
    assert robot.status == LitterBoxStatus.DRAWER_FULL

    new_name = "Test Name"
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"updateLitterRobot4": {"name": new_name}}},
    )
    assert robot.name != new_name
    assert await robot.set_name(new_name)
    assert robot.name == new_name

    mock_aioresponse.post(
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

    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "sendLitterRobot4Command": 'command "nightLightModeAuto (0x02180002)" sent'
            }
        },
    )
    await robot.set_night_light_mode(NightLightMode.AUTO)

    mock_aioresponse.post(
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
    mock_aioresponse.post(LR4_ENDPOINT, payload=firmware_response)
    assert await robot.has_firmware_update()

    version_info["isEspFirmwareUpdateNeeded"] = False
    version_info["isPicFirmwareUpdateNeeded"] = False
    mock_aioresponse.post(LR4_ENDPOINT, payload=firmware_response)
    assert not await robot.has_firmware_update(True)
    latest_firmware = await robot.get_latest_firmware()
    assert latest_firmware == "ESP: 1.1.54 / PIC: 10512.2560.2.66 / TOF: 4.0.65.4"

    mock_aioresponse.post(
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
    mock_aioresponse.post(
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
    mock_aioresponse.post(LR4_ENDPOINT, payload=firmware_response, repeat=True)
    assert not await robot.has_firmware_update(True)
    assert not await robot.get_latest_firmware()

    await robot._account.disconnect()


async def test_litter_robot_4_sleep_time(
    freezer: pytest.fixture, mock_account: Account
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
    mock_aioresponse: aioresponses,
    mock_account: Account,
    method_call: Callable,
    dispatch_command: str,
    mock_response_data: dict,
    args: Any,
) -> None:
    """Tests that commands for Litter-Robot 4 are sent as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": mock_response_data},
    )

    await getattr(robot, method_call.__name__)(*args)

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
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
    mock_aioresponse: aioresponses,
    mock_account: Account,
    is_removed: bool,
    mock_mutation_response_data: dict,
    expected_is_hopper_removed: bool | None,
    expected_hopper_status: HopperStatus | None,
    expected_return: bool,
) -> None:
    """Tests that LitterHopper toggling works as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": mock_mutation_response_data},
    )

    assert (await robot.toggle_hopper(is_removed)) is expected_return
    assert robot.hopper_status == expected_hopper_status
    assert robot.is_hopper_removed is expected_is_hopper_removed

    json = list(mock_aioresponse.requests.items())[-1][-1][0].kwargs.get("json", {})
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
