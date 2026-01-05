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


async def test_reassign_visit_success(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that reassign_visit successfully reassigns a visit between pets."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": "success"}},
    )

    result = await robot.reassign_visit(
        visit_timestamp="2025-12-29T17:56:12",
        from_pet_id="pet-123",
        to_pet_id="pet-456",
    )
    assert result is True

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
    assert "reassignPetVisit" in json.get("query", "")
    variables = json.get("variables", {}).get("input", {})
    assert variables["robotSerial"] == "LR4C000001"
    assert variables["visitTimestamp"] == "2025-12-29T17:56:12"
    assert variables["fromPetId"] == "pet-123"
    assert variables["toPetId"] == "pet-456"

    await robot._account.disconnect()


async def test_reassign_visit_from_unknown(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests reassigning from unassigned (None) to a pet."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": "success"}},
    )

    result = await robot.reassign_visit(
        visit_timestamp="2025-12-29T17:56:12",
        from_pet_id=None,
        to_pet_id="pet-456",
    )
    assert result is True

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
    variables = json.get("variables", {}).get("input", {})
    assert variables["fromPetId"] == ""
    assert variables["toPetId"] == "pet-456"

    await robot._account.disconnect()


async def test_reassign_visit_to_unknown(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests reassigning from a pet to unassigned (None)."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": "success"}},
    )

    result = await robot.reassign_visit(
        visit_timestamp="2025-12-29T17:56:12",
        from_pet_id="pet-123",
        to_pet_id=None,
    )
    assert result is True

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
    variables = json.get("variables", {}).get("input", {})
    assert variables["fromPetId"] == "pet-123"
    assert variables["toPetId"] == ""

    await robot._account.disconnect()


async def test_reassign_visit_with_datetime(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that datetime objects are correctly converted to timestamp strings."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": "success"}},
    )

    # Test with timezone-aware datetime
    visit_time = datetime(2025, 12, 29, 17, 56, 12, tzinfo=timezone.utc)
    result = await robot.reassign_visit(
        visit_timestamp=visit_time,
        from_pet_id="pet-123",
        to_pet_id="pet-456",
    )
    assert result is True

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
    variables = json.get("variables", {}).get("input", {})
    assert variables["visitTimestamp"] == "2025-12-29T17:56:12"

    await robot._account.disconnect()


async def test_reassign_visit_same_pet_raises(
    mock_account: Account,
) -> None:
    """Tests that reassigning to the same pet raises an exception."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    with pytest.raises(InvalidCommandException, match="must be different"):
        await robot.reassign_visit(
            visit_timestamp="2025-12-29T17:56:12",
            from_pet_id="pet-123",
            to_pet_id="pet-123",
        )

    # Also test with None/empty string equivalence
    with pytest.raises(InvalidCommandException, match="must be different"):
        await robot.reassign_visit(
            visit_timestamp="2025-12-29T17:56:12",
            from_pet_id=None,
            to_pet_id="",
        )


async def test_reassign_visit_failure(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that reassign_visit returns False when the API returns null."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": None}},
    )

    result = await robot.reassign_visit(
        visit_timestamp="2025-12-29T17:56:12",
        from_pet_id="pet-123",
        to_pet_id="pet-456",
    )
    assert result is False

    await robot._account.disconnect()


async def test_get_weight_history_success(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that get_weight_history returns parsed weight history entries."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    # Set a mock id_token since get_weight_history requires it
    mock_account._session._LitterRobotSession__id_token = "mock_id_token"  # type: ignore[attr-defined]

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "weightHistory": [
                    {
                        "record_field_00": "pet-123_15.26",
                        "time": "2025-12-29 17:56:12.000000000",
                    },
                    {
                        "record_field_00": "None_8.50",
                        "time": "2025-12-28 10:30:00.000000000",
                    },
                    {
                        "record_field_00": "pet-456_12.00",
                        "time": "2025-12-27 08:15:30.000000000",
                    },
                ]
            }
        },
    )

    entries = await robot.get_weight_history(days=7)

    assert len(entries) == 3

    # First entry - assigned to pet
    assert entries[0].pet_id == "pet-123"
    assert entries[0].weight == 15.26
    assert entries[0].timestamp == datetime(
        2025, 12, 29, 17, 56, 12, tzinfo=timezone.utc
    )

    # Second entry - unassigned (None)
    assert entries[1].pet_id is None
    assert entries[1].weight == 8.50
    assert entries[1].timestamp == datetime(
        2025, 12, 28, 10, 30, 0, tzinfo=timezone.utc
    )

    # Third entry - assigned to different pet
    assert entries[2].pet_id == "pet-456"
    assert entries[2].weight == 12.00

    await robot._account.disconnect()


async def test_get_weight_history_empty(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that get_weight_history handles empty results."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    # Set a mock id_token since get_weight_history requires it
    mock_account._session._LitterRobotSession__id_token = "mock_id_token"  # type: ignore[attr-defined]

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"weightHistory": []}},
    )

    entries = await robot.get_weight_history()

    assert entries == []

    await robot._account.disconnect()


async def test_get_weight_history_malformed_records(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that get_weight_history skips malformed record_field_00 values."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_account._session._LitterRobotSession__id_token = "mock_id_token"  # type: ignore[attr-defined]

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={
            "data": {
                "weightHistory": [
                    {
                        # Valid entry
                        "record_field_00": "pet-123_15.26",
                        "time": "2025-12-29 17:56:12.000000000",
                    },
                    {
                        # Malformed: no underscore separator
                        "record_field_00": "malformed",
                        "time": "2025-12-28 10:30:00.000000000",
                    },
                    {
                        # Malformed: empty string
                        "record_field_00": "",
                        "time": "2025-12-27 08:15:30.000000000",
                    },
                    {
                        # Malformed: weight is not a number
                        "record_field_00": "pet-456_notanumber",
                        "time": "2025-12-26 08:00:00.000000000",
                    },
                    {
                        # Valid entry after malformed ones
                        "record_field_00": "None_8.50",
                        "time": "2025-12-25 12:00:00.000000000",
                    },
                ]
            }
        },
    )

    entries = await robot.get_weight_history(days=7)

    assert len(entries) == 2
    assert entries[0].pet_id == "pet-123"
    assert entries[0].weight == 15.26
    assert entries[1].pet_id is None
    assert entries[1].weight == 8.50

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "timestamp_input,expected_timestamp",
    [
        # Plain ISO string (no suffix)
        ("2025-12-29T17:56:12", "2025-12-29T17:56:12"),
        # Z suffix
        ("2025-12-29T17:56:12Z", "2025-12-29T17:56:12"),
        # +00:00 suffix
        ("2025-12-29T17:56:12+00:00", "2025-12-29T17:56:12"),
        # Positive timezone offset
        ("2025-12-29T17:56:12+05:00", "2025-12-29T17:56:12"),
        # Negative timezone offset
        ("2025-12-29T17:56:12-05:00", "2025-12-29T17:56:12"),
        # With microseconds
        ("2025-12-29T17:56:12.123456", "2025-12-29T17:56:12"),
        # With microseconds and Z
        ("2025-12-29T17:56:12.123456Z", "2025-12-29T17:56:12"),
    ],
)
async def test_reassign_visit_timestamp_formats(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    timestamp_input: str,
    expected_timestamp: str,
) -> None:
    """Tests that various timestamp string formats are correctly normalized."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)

    mock_aioresponse.clear()
    mock_aioresponse.post(
        LR4_ENDPOINT,
        payload={"data": {"reassignPetVisit": "success"}},
    )

    result = await robot.reassign_visit(
        visit_timestamp=timestamp_input,
        from_pet_id="pet-123",
        to_pet_id="pet-456",
    )
    assert result is True

    json = list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
    variables = json.get("variables", {}).get("input", {})
    assert variables["visitTimestamp"] == expected_timestamp

    await robot._account.disconnect()
