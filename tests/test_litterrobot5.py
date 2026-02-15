"""Test litterrobot5 module."""

# pylint: disable=protected-access
from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from aiohttp import ClientConnectionError
from aioresponses import aioresponses
from freezegun.api import FrozenDateTimeFactory

from pylitterbot import Account
from pylitterbot.enums import LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException, LitterRobotException
from pylitterbot.robot.litterrobot5 import (
    LITTER_LEVEL_EMPTY,
    LR5_ENDPOINT,
    BrightnessLevel,
    HopperStatus,
    LitterLevelState,
    LitterRobot5,
    NightLightMode,
)

from .common import LITTER_ROBOT_5_DATA, LITTER_ROBOT_5_PRO_DATA

pytestmark = pytest.mark.asyncio


LR5_GET_URL = f"{LR5_ENDPOINT}/robots/{LITTER_ROBOT_5_DATA['serial']}"
LR5_COMMANDS_URL = f"{LR5_GET_URL}/commands"


async def test_litter_robot_5(
    mock_account: Account,
) -> None:
    """Tests that a Litter-Robot 5 setup is successful and parses as expected."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert (
        str(robot)
        == "Name: Robo-shitter, Model: Litter-Robot 5, Serial: LR5-00-00-00-0000-000001, id: LR5-00-00-00-0000-000001"
    )
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_count == 81  # reads from state.odometerCleanCycles
    assert robot.firmware == "ESP: v2.5.6 / MCU: v5.7.4 2904_106"
    assert robot.firmware_update_status == "UpdateSuccessful"
    assert not robot.firmware_update_triggered
    assert robot.hopper_status == HopperStatus.DISABLED  # case-insensitive match
    assert not robot.is_drawer_full_indicator_triggered
    assert robot.is_hopper_removed is True
    assert robot.is_online
    assert not robot.is_sleeping
    assert not robot.is_smart_weight_enabled
    assert not robot.is_waste_drawer_full
    assert robot.litter_level == 100.0
    assert robot.litter_level_state == LitterLevelState.OPTIMAL  # case-insensitive
    assert robot.model == "Litter-Robot 5"
    assert robot.name == "Robo-shitter"
    assert robot.night_light_brightness == 70
    assert robot.night_light_color == "#665F5F"
    assert robot.night_light_level is None  # 70 doesn't map to LOW/MEDIUM/HIGH
    assert robot.night_light_mode == NightLightMode.AUTO
    assert robot.night_light_mode_enabled
    assert robot.panel_brightness == BrightnessLevel.LOW  # from displayIntensity
    assert not robot.panel_lock_enabled
    assert robot.pet_weight == 1104.0
    assert robot.power_status == "On"
    assert robot.scoops_saved_count == 80
    assert not robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time is None
    assert robot.sleep_mode_end_time is None
    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value
    assert robot.status_text == LitterBoxStatus.READY.text
    assert robot.timezone == "America/New_York"
    assert robot.waste_drawer_level == 16

    await robot._account.disconnect()


async def test_litter_robot_5_firmware_fallback(
    mock_account: Account,
) -> None:
    """Tests firmware parsing when firmwareVersions is missing."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    del data["state"]["firmwareVersions"]
    robot = LitterRobot5(data=data, account=mock_account)
    # Falls back to espFirmwareVersion and stmFirmwareVersion
    assert robot.firmware == "ESP: v2.5.6 / MCU: v5.7.4 2904_106"

    await robot._account.disconnect()


async def test_litter_robot_5_firmware_no_versions(
    mock_account: Account,
) -> None:
    """Tests firmware parsing when no firmware data is available."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    del data["state"]["firmwareVersions"]
    del data["state"]["espFirmwareVersion"]
    del data["state"]["stmFirmwareVersion"]
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.firmware == "ESP: None / MCU: None"

    await robot._account.disconnect()


async def test_litter_robot_5_panel_brightness_values(
    mock_account: Account,
) -> None:
    """Tests panel brightness with displayIntensity strings and numeric fallback."""
    data = deepcopy(LITTER_ROBOT_5_DATA)

    # Real API uses displayIntensity strings
    data["panelSettings"]["displayIntensity"] = "Low"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.LOW

    data["panelSettings"]["displayIntensity"] = "Medium"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.MEDIUM

    data["panelSettings"]["displayIntensity"] = "High"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.HIGH

    # Numeric brightness fallback (when no displayIntensity)
    del data["panelSettings"]["displayIntensity"]
    data["panelSettings"]["brightness"] = 25
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.LOW

    data["panelSettings"]["brightness"] = 50
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.MEDIUM

    data["panelSettings"]["brightness"] = 100
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness == BrightnessLevel.HIGH

    data["panelSettings"]["brightness"] = None
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.panel_brightness is None

    await robot._account.disconnect()


async def test_litter_robot_5_night_light_levels(
    mock_account: Account,
) -> None:
    """Tests night light level with exact enum values."""
    data = deepcopy(LITTER_ROBOT_5_DATA)

    data["nightLightSettings"]["brightness"] = 25
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_level == BrightnessLevel.LOW

    data["nightLightSettings"]["brightness"] = 50
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_level == BrightnessLevel.MEDIUM

    data["nightLightSettings"]["brightness"] = 100
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_level == BrightnessLevel.HIGH

    await robot._account.disconnect()


async def test_litter_robot_5_night_light_modes(
    mock_account: Account,
) -> None:
    """Tests night light mode parsing."""
    data = deepcopy(LITTER_ROBOT_5_DATA)

    data["nightLightSettings"]["mode"] = "On"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_mode == NightLightMode.ON
    assert robot.night_light_mode_enabled

    data["nightLightSettings"]["mode"] = "Off"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_mode == NightLightMode.OFF
    assert not robot.night_light_mode_enabled

    data["nightLightSettings"]["mode"] = "Auto"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_mode == NightLightMode.AUTO
    assert robot.night_light_mode_enabled

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "updated_data,status",
    [
        # Offline takes priority
        ({"state": {"isOnline": False}}, LitterBoxStatus.OFFLINE),
        # Cycle state interrupts (highest priority when online)
        (
            {"state": {"isOnline": True, "cycleState": "StCatDetect"}},
            LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
        ),
        (
            {"state": {"isOnline": True, "cycleState": "StPause"}},
            LitterBoxStatus.PAUSED,
        ),
        # Legacy cycle state format (LR4-style)
        (
            {"state": {"isOnline": True, "robotCycleState": "CYCLE_STATE_PAUSE"}},
            LitterBoxStatus.PAUSED,
        ),
        (
            {"state": {"isOnline": True, "robotCycleState": "CYCLE_STATE_CAT_DETECT"}},
            LitterBoxStatus.CAT_SENSOR_INTERRUPTED,
        ),
        # Real API state field (StPascalCase format)
        (
            {"state": {"isOnline": True, "state": "StRobotIdle"}},
            LitterBoxStatus.READY,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotClean"}},
            LitterBoxStatus.CLEAN_CYCLE,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotCatDetect"}},
            LitterBoxStatus.CAT_DETECTED,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotEmpty"}},
            LitterBoxStatus.EMPTY_CYCLE,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotPowerUp"}},
            LitterBoxStatus.POWER_UP,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotPowerDown"}},
            LitterBoxStatus.POWER_DOWN,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotPowerOff"}},
            LitterBoxStatus.OFF,
        ),
        (
            {"state": {"isOnline": True, "state": "StRobotBonnet"}},
            LitterBoxStatus.BONNET_REMOVED,
        ),
        # Display code (DcPascalCase from real API)
        (
            {"state": {"isOnline": True, "displayCode": "DcCatDetect"}},
            LitterBoxStatus.CAT_DETECTED,
        ),
        (
            {"state": {"isOnline": True, "displayCode": "DcDfiFull"}},
            LitterBoxStatus.DRAWER_FULL,
        ),
        (
            {"state": {"isOnline": True, "displayCode": "DcModeCycle"}},
            LitterBoxStatus.CLEAN_CYCLE,
        ),
        (
            {"state": {"isOnline": True, "displayCode": "DcModeIdle"}},
            LitterBoxStatus.READY,
        ),
        # Power display codes (observed from live hardware power cycle)
        (
            {"state": {"isOnline": True, "displayCode": "DcxSuspend"}},
            LitterBoxStatus.POWER_DOWN,
        ),
        (
            {"state": {"isOnline": True, "displayCode": "DcxLampTest"}},
            LitterBoxStatus.POWER_UP,
        ),
        # Legacy display code format (LR4-style)
        (
            {"state": {"isOnline": True, "displayCode": "DC_CAT_DETECT"}},
            LitterBoxStatus.CAT_DETECTED,
        ),
        # statusIndicator.type
        (
            {"state": {"isOnline": True, "statusIndicator": {"type": "READY"}}},
            LitterBoxStatus.READY,
        ),
        (
            {"state": {"isOnline": True, "statusIndicator": {"type": "DRAWER_FULL"}}},
            LitterBoxStatus.DRAWER_FULL,
        ),
        (
            {"state": {"isOnline": True, "statusIndicator": {"type": "CYCLING"}}},
            LitterBoxStatus.CLEAN_CYCLE,
        ),
        (
            {"state": {"isOnline": True, "statusIndicator": {"type": "LITTER_LOW"}}},
            LitterBoxStatus.READY,
        ),
        # statusIndicator power states (observed from live power cycle)
        (
            {"state": {"isOnline": True, "statusIndicator": {"type": "OFF"}}},
            LitterBoxStatus.OFF,
        ),
        # Legacy status string
        (
            {"state": {"isOnline": True, "status": "Ready"}},
            LitterBoxStatus.READY,
        ),
        # Drawer full overrides ready (via state field)
        (
            {"state": {"isOnline": True, "state": "StRobotIdle", "isDrawerFull": True}},
            LitterBoxStatus.DRAWER_FULL,
        ),
        # Legacy LR5_STATUS_MAP fallback
        (
            {"state": {"isOnline": True, "status": "ROBOT_BONNET"}},
            LitterBoxStatus.BONNET_REMOVED,
        ),
        (
            {"state": {"isOnline": True, "status": "ROBOT_POWER_UP"}},
            LitterBoxStatus.POWER_UP,
        ),
        # Unknown status
        (
            {"state": {"isOnline": True, "status": "SomeNewStatus"}},
            LitterBoxStatus.UNKNOWN,
        ),
        # No status at all
        (
            {"state": {"isOnline": True}},
            LitterBoxStatus.UNKNOWN,
        ),
        # robotStatus fallback when status is missing
        (
            {"state": {"isOnline": True, "robotStatus": "ROBOT_IDLE"}},
            LitterBoxStatus.READY,
        ),
    ],
)
async def test_litter_robot_5_status(
    mock_account: Account, updated_data: dict[str, Any], status: LitterBoxStatus
) -> None:
    """Tests Litter-Robot 5 in various statuses."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    # Clear all state fields that could interfere with status resolution, then apply test data
    data["state"] = {
        **{
            k: v
            for k, v in data["state"].items()
            if k
            not in (
                "state",
                "status",
                "robotStatus",
                "cycleState",
                "robotCycleState",
                "displayCode",
                "statusIndicator",
                "isDrawerFull",
            )
        },
        **updated_data.get("state", {}),
    }
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.status == status


async def test_litter_robot_5_status_code_unknown(
    mock_account: Account,
) -> None:
    """Tests status_code when status is UNKNOWN returns raw status string."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    data["state"]["status"] = "SomeBrandNewStatus"
    # Clear fields that would take priority
    data["state"].pop("robotCycleState", None)
    data["state"].pop("cycleState", None)
    data["state"].pop("displayCode", None)
    data["state"].pop("robotStatus", None)
    data["state"].pop("statusIndicator", None)
    # Clear the state.state field which now takes priority
    data["state"].pop("state", None)
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.status == LitterBoxStatus.UNKNOWN
    assert robot.status_code == "SomeBrandNewStatus"

    await robot._account.disconnect()


async def test_litter_robot_5_refresh(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests refreshing Litter-Robot 5 data."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.waste_drawer_level == 16

    updated_data = deepcopy(LITTER_ROBOT_5_DATA)
    updated_data["state"]["dfiLevelPercent"] = 50

    mock_aioresponse.get(LR5_GET_URL, payload=updated_data)
    await robot.refresh()
    assert robot.waste_drawer_level == 50

    await robot._account.disconnect()


async def test_litter_robot_5_set_name(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting the name on a Litter-Robot 5 via REST PATCH."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.name == "Robo-shitter"

    new_name = "Mr. Clean"
    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_name(new_name)
    assert robot.name == new_name

    await robot._account.disconnect()


async def test_litter_robot_5_set_panel_lockout(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests toggling the panel lock on a Litter-Robot 5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert not robot.panel_lock_enabled

    # Enable panel lock
    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_panel_lockout(True)
    assert robot.panel_lock_enabled

    # Disable panel lock
    mock_aioresponse.patch(LR5_GET_URL, payload={})  # type: ignore[unreachable]
    assert await robot.set_panel_lockout(False)
    assert not robot.panel_lock_enabled

    await robot._account.disconnect()


async def test_litter_robot_5_set_wait_time(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting the wait time on a Litter-Robot 5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.clean_cycle_wait_time_minutes == 7

    # Valid wait time
    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_wait_time(15)
    assert robot.clean_cycle_wait_time_minutes == 15

    # Invalid wait time
    with pytest.raises(InvalidCommandException):
        await robot.set_wait_time(10)

    await robot._account.disconnect()


async def test_litter_robot_5_dispatch_command_failure(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that dispatch_command handles errors gracefully."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.patch(
        LR5_GET_URL,
        exception=InvalidCommandException("Test error"),
    )
    assert not await robot._dispatch_command("testCommand")

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "method,command_type",
    [
        ("start_cleaning", "CLEAN_CYCLE"),
        ("reset", "REMOTE_RESET"),
        ("reset_waste_drawer", "RESET_WASTE_LEVEL"),
        ("change_filter", "CHANGE_FILTER"),
    ],
)
async def test_litter_robot_5_commands(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    method: str,
    command_type: str,
) -> None:
    """Tests LR5 operational commands via POST /robots/{serial}/commands."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.post(LR5_COMMANDS_URL, payload=None)
    assert await getattr(robot, method)()

    await robot._account.disconnect()


async def test_litter_robot_5_power_on_off(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests power on/off commands."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    # Power off
    mock_aioresponse.post(LR5_COMMANDS_URL, payload=None)
    assert await robot.set_power_status(False)

    # Power on
    mock_aioresponse.post(LR5_COMMANDS_URL, payload=None)
    assert await robot.set_power_status(True)

    await robot._account.disconnect()


async def test_litter_robot_5_set_night_light(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests night light on/off toggle."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_night_light(True)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_night_light(False)

    await robot._account.disconnect()


async def test_litter_robot_5_set_night_light_brightness(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting night light brightness."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_night_light_brightness(50)

    await robot._account.disconnect()


async def test_litter_robot_5_set_night_light_mode(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting night light mode."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    for mode in NightLightMode:
        mock_aioresponse.patch(LR5_GET_URL, payload={})
        assert await robot.set_night_light_mode(mode)

    await robot._account.disconnect()


async def test_litter_robot_5_set_panel_brightness(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting panel brightness."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    for level in BrightnessLevel:
        mock_aioresponse.patch(LR5_GET_URL, payload={})
        assert await robot.set_panel_brightness(level)

    await robot._account.disconnect()


async def test_litter_robot_5_command_failure(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests that _send_command handles errors gracefully."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.post(
        LR5_COMMANDS_URL,
        exception=ClientConnectionError("Connection error"),
    )
    assert not await robot.start_cleaning()

    await robot._account.disconnect()


async def test_litter_robot_5_activity_history(
    mock_account: Account,
) -> None:
    """Tests getting activity history for Litter-Robot 5 via REST endpoint."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    activities_data = [
        {
            "type": "PET_VISIT",
            "timestamp": "2025-12-10T20:53:32Z",
            "petWeight": 937.0,
        },
        {
            "type": "CYCLE_COMPLETED",
            "timestamp": "2025-12-10T20:51:18Z",
            "subtype": "robotCycleStateIdle",
        },
        {
            "type": "CAT_DETECT",
            "timestamp": "2025-12-10T20:44:18Z",
        },
    ]
    activities_url = f"{LR5_GET_URL}/activities?limit=3"
    with aioresponses() as mock:
        mock.get(activities_url, payload=activities_data)
        activities = await robot.get_activity_history(3)
    assert len(activities) == 3
    assert activities[0].action == "PET_VISIT"
    assert activities[1].action == "CYCLE_COMPLETED"
    assert activities[2].action == "CAT_DETECT"

    await robot._account.disconnect()


async def test_litter_robot_5_activity_history_invalid_limit(
    mock_account: Account,
) -> None:
    """Tests that activity history raises on invalid limit."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    with pytest.raises(InvalidCommandException):
        await robot.get_activity_history(0)

    await robot._account.disconnect()


async def test_litter_robot_5_activity_history_none_response(
    mock_account: Account,
) -> None:
    """Tests that activity history raises when response is None."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    activities_url = f"{LR5_GET_URL}/activities?limit=5"
    with aioresponses() as mock:
        mock.get(activities_url, payload=None)
        with pytest.raises(LitterRobotException):
            await robot.get_activity_history(5)

    await robot._account.disconnect()


async def test_litter_robot_5_insight(
    mock_account: Account,
) -> None:
    """Tests that get_insight raises NotImplementedError for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    with pytest.raises(NotImplementedError):
        await robot.get_insight(days=7)

    await robot._account.disconnect()


async def test_litter_robot_5_firmware_details(
    mock_account: Account,
) -> None:
    """Tests getting firmware details from robot state for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    details = await robot.get_firmware_details()
    assert isinstance(details, dict)
    assert "latestFirmware" in details
    assert isinstance(latest_firmware := details["latestFirmware"], dict)
    assert latest_firmware["espFirmwareVersion"] == "v2.5.6"
    assert latest_firmware["mcuFirmwareVersion"] == "v5.7.4 2904_106"

    latest = await robot.get_latest_firmware()
    assert latest == "ESP: v2.5.6 / MCU: v5.7.4 2904_106"

    # has_firmware_update always returns False for LR5 (no comparison endpoint)
    assert not await robot.has_firmware_update()

    await robot._account.disconnect()


async def test_litter_robot_5_update_firmware(
    mock_account: Account,
) -> None:
    """Tests that update_firmware raises NotImplementedError for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    with pytest.raises(NotImplementedError):
        await robot.update_firmware()

    await robot._account.disconnect()


async def test_litter_robot_5_cleaning(mock_account: Account) -> None:
    """Tests Litter-Robot 5 litter level during cleaning."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.litter_level == 100.0
    initial_calculated = robot.litter_level_calculated

    # Simulate update to cleaning - cycleType contains "Clean"
    robot._update_data(
        {"state": {**robot._state, "cycleType": "StCycleClean"}}, partial=True
    )
    # During cleaning, litter level should be stable
    assert robot.litter_level_calculated == initial_calculated

    # Simulate litter level read mid-cycle (level drops during rotation)
    robot._update_data(
        {
            "state": {
                **robot._state,
                "globeLitterLevel": LITTER_LEVEL_EMPTY,
            }
        },
        partial=True,
    )
    # Should still show the pre-cycle level due to expiry protection
    assert robot.litter_level_calculated == initial_calculated

    await robot._account.disconnect()


async def test_litter_robot_5_hopper_statuses(
    mock_account: Account,
) -> None:
    """Tests various hopper status values."""
    data = deepcopy(LITTER_ROBOT_5_DATA)

    data["state"]["hopperStatus"] = "ENABLED"
    data["state"]["isHopperInstalled"] = True
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.hopper_status == HopperStatus.ENABLED
    assert robot.is_hopper_removed is False

    data["state"]["hopperStatus"] = "MOTOR_FAULT_SHORT"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.hopper_status == HopperStatus.MOTOR_FAULT_SHORT

    data["state"]["hopperStatus"] = "EMPTY"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.hopper_status == HopperStatus.EMPTY

    # Real API returns mixed-case - now works with case-insensitive matching
    data["state"]["hopperStatus"] = "Disabled"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.hopper_status == HopperStatus.DISABLED

    data["state"]["hopperStatus"] = "Enabled"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.hopper_status == HopperStatus.ENABLED

    await robot._account.disconnect()


async def test_litter_robot_5_drawer_full_indicator(
    mock_account: Account,
) -> None:
    """Tests drawer full indicator with non-zero counter."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    data["state"]["dfiFullCounter"] = 3
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.is_drawer_full_indicator_triggered

    await robot._account.disconnect()


async def test_litter_robot_5_sleep_mode_enabled(
    freezer: FrozenDateTimeFactory,
    mock_account: Account,
) -> None:
    """Tests sleep mode parsing when enabled."""
    freezer.move_to("2025-12-10 12:00:00-05:00")
    data = deepcopy(LITTER_ROBOT_5_DATA)
    # Enable sleep on Wednesday (dayOfWeek=2, Wednesday in 0=Monday convention)
    data["sleepSchedules"] = [
        {"dayOfWeek": 0, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 1, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 2, "isEnabled": True, "sleepTime": 1380, "wakeTime": 450},
        {"dayOfWeek": 3, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 4, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 5, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 6, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
    ]
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.sleep_mode_enabled

    await robot._account.disconnect()


async def test_litter_robot_5_sleep_mode_disabled(
    mock_account: Account,
) -> None:
    """Tests sleep mode when all days are disabled."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert not robot.sleep_mode_enabled
    assert robot.sleep_mode_start_time is None
    assert robot.sleep_mode_end_time is None

    await robot._account.disconnect()


async def test_litter_robot_5_get_data_dict_warning(
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that _get_data_dict logs a warning for non-dict values."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    data["nightLightSettings"] = "not_a_dict"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.night_light_brightness == 0
    assert any("Expected dict" in msg for msg in caplog.messages)

    await robot._account.disconnect()


async def test_litter_robot_5_litter_level_state_values(
    mock_account: Account,
) -> None:
    """Tests various litter level state values."""
    data = deepcopy(LITTER_ROBOT_5_DATA)

    # to_enum now handles case-insensitive matching, so both UPPERCASE
    # and mixed-case values from the API should work correctly.
    for state_value, expected in [
        ("OPTIMAL", LitterLevelState.OPTIMAL),
        ("LOW", LitterLevelState.LOW),
        ("EMPTY", LitterLevelState.EMPTY),
        ("REFILL", LitterLevelState.REFILL),
        ("OVERFILL", LitterLevelState.OVERFILL),
        # Real API returns mixed-case - now works with case-insensitive matching
        ("Optimal", LitterLevelState.OPTIMAL),
        ("Low", LitterLevelState.LOW),
        ("Empty", LitterLevelState.EMPTY),
    ]:
        data["state"]["globeLitterLevelIndicator"] = state_value
        robot = LitterRobot5(data=data, account=mock_account)
        assert robot.litter_level_state == expected

    await robot._account.disconnect()


async def test_litter_robot_5_pro_model(
    mock_account: Account,
) -> None:
    """Tests that LR5 Pro is detected and model name is correct."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
    assert robot.is_pro
    assert robot.model == "Litter-Robot 5 Pro"

    # Standard LR5 should not be Pro
    robot_std = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert not robot_std.is_pro
    assert robot_std.model == "Litter-Robot 5"

    await robot._account.disconnect()


async def test_litter_robot_5_pro_firmware(
    mock_account: Account,
) -> None:
    """Tests firmware string includes Pro-specific versions."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
    fw = robot.firmware
    assert "MCU: v5.7.5 2904_0106" in fw
    assert "CAM: 1.2.2-1233" in fw
    assert "EDGE: 1.5.22" in fw
    assert "AI: 0.0.41" in fw

    await robot._account.disconnect()


async def test_litter_robot_5_pro_camera_metadata(
    mock_account: Account,
) -> None:
    """Tests camera metadata is available for Pro."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_PRO_DATA, account=mock_account)
    assert robot.camera_metadata is not None
    assert "deviceId" in robot.camera_metadata
    assert "serialNumber" in robot.camera_metadata

    # Standard LR5 has no camera metadata
    robot_std = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot_std.camera_metadata is None

    await robot._account.disconnect()


async def test_litter_robot_5_new_state_properties(
    mock_account: Account,
) -> None:
    """Tests new state properties from live API data."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    assert not robot.is_bonnet_removed
    assert not robot.is_drawer_removed
    assert not robot.is_laser_dirty
    assert not robot.is_firmware_updating
    assert not robot.is_gas_sensor_fault_detected
    assert not robot.is_usb_fault_detected
    assert not robot.extended_scale_activity
    assert robot.is_night_light_on
    assert robot.privacy_mode == "Normal"
    assert robot.wifi_rssi == 58
    assert robot.odometer_empty_cycles == 0
    assert robot.odometer_filter_cycles == 3
    assert robot.odometer_power_cycles == 14
    assert robot.globe_motor_fault_status == "MtrFaultClear"
    assert robot.globe_motor_retract_fault_status == "MtrFaultClear"
    assert robot.pinch_status == "Clear"
    assert robot.cat_detect == "WeightClear"
    assert robot.cycle_type == "StCycleIdle"
    assert robot.stm_update_status == "UpdateSuccessful"
    assert robot.hopper_fault is None
    assert robot.last_reset_odometer_clean_cycles == 1
    assert robot.optimal_litter_level == 434
    assert robot.next_filter_replacement_date is not None

    await robot._account.disconnect()


async def test_litter_robot_5_sound_properties(
    mock_account: Account,
) -> None:
    """Tests sound settings properties."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.sound_volume == 50
    assert not robot.camera_audio_enabled

    await robot._account.disconnect()


async def test_litter_robot_5_set_privacy_mode(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests privacy mode on/off commands."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.post(LR5_COMMANDS_URL, payload=None)
    assert await robot.set_privacy_mode(True)

    mock_aioresponse.post(LR5_COMMANDS_URL, payload=None)
    assert await robot.set_privacy_mode(False)

    await robot._account.disconnect()


async def test_litter_robot_5_set_volume(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting sound volume."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_volume(75)

    await robot._account.disconnect()


async def test_litter_robot_5_set_camera_audio(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests toggling camera audio."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_camera_audio(True)

    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_camera_audio(False)

    await robot._account.disconnect()


async def test_litter_robot_5_get_activities(
    mock_account: Account,
) -> None:
    """Tests REST activities endpoint."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    activities_data = [
        {
            "messageId": "msg-001",
            "type": "PET_VISIT",
            "timestamp": "2026-02-14T23:12:12Z",
            "petWeight": 937.0,
            "wasteType": "Urine",
            "duration": 31,
            "petIds": ["PET-123"],
            "cameraEventIds": [],
            "isWasteWeightValid": True,
            "wasteWeight": 40.0,
        },
        {
            "messageId": "msg-002",
            "type": "CYCLE_COMPLETED",
            "timestamp": "2026-02-14T23:29:21Z",
            "subtype": "robotCycleStateIdle",
        },
        {
            "messageId": "msg-003",
            "type": "OFFLINE",
            "timestamp": "2026-02-15T01:49:22Z",
            "reason": "CONNECTION_LOST",
        },
    ]
    activities_url = f"{LR5_GET_URL}/activities?limit=3"
    with aioresponses() as mock:
        mock.get(activities_url, payload=activities_data)
        result = await robot.get_activities(limit=3)
    assert len(result) == 3
    assert result[0]["type"] == "PET_VISIT"
    assert result[0]["wasteType"] == "Urine"
    assert result[0]["petWeight"] == 937.0
    assert result[1]["type"] == "CYCLE_COMPLETED"
    assert result[2]["type"] == "OFFLINE"

    await robot._account.disconnect()


async def test_litter_robot_5_bonnet_removed_state(
    mock_account: Account,
) -> None:
    """Tests bonnet and drawer removed state properties."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    data["state"]["isBonnetRemoved"] = True
    data["state"]["isDrawerRemoved"] = True
    data["state"]["isLaserDirty"] = True
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.is_bonnet_removed
    assert robot.is_drawer_removed
    assert robot.is_laser_dirty

    await robot._account.disconnect()


async def test_litter_robot_5_set_sleep_mode(
    mock_aioresponse: aioresponses,
    mock_account: Account,
) -> None:
    """Tests setting sleep mode via REST PATCH."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert not robot.sleep_mode_enabled

    # Enable sleep for all days
    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_sleep_mode(value=True, sleep_time=1380, wake_time=420)
    assert robot.sleep_mode_enabled

    # Disable sleep for all days
    mock_aioresponse.patch(LR5_GET_URL, payload={})  # type: ignore[unreachable]
    assert await robot.set_sleep_mode(value=False)
    assert not robot.sleep_mode_enabled

    # Enable sleep for a specific day (Sunday=6)
    mock_aioresponse.patch(LR5_GET_URL, payload={})
    assert await robot.set_sleep_mode(
        value=True, sleep_time=1380, wake_time=420, day_of_week=6
    )
    schedules = robot._data.get("sleepSchedules", [])
    sunday = next(s for s in schedules if s["dayOfWeek"] == 6)
    assert sunday["isEnabled"]
    assert sunday["sleepTime"] == 1380
    assert sunday["wakeTime"] == 420
    # Other days should remain disabled
    monday = next(s for s in schedules if s["dayOfWeek"] == 0)
    assert not monday["isEnabled"]

    await robot._account.disconnect()


async def test_litter_robot_5_fault_states(
    mock_account: Account,
) -> None:
    """Tests fault detection state properties in active state."""
    data = deepcopy(LITTER_ROBOT_5_DATA)
    data["state"]["isUsbFaultDetected"] = True
    data["state"]["isGasSensorFaultDetected"] = True
    data["state"]["isFirmwareUpdating"] = True
    data["state"]["extendedScaleActivity"] = True
    data["state"]["isNightLightOn"] = False
    data["state"]["hopperFault"] = "MOTOR_STALL"
    data["state"]["globeMotorRetractFaultStatus"] = "MtrFaultSet"
    robot = LitterRobot5(data=data, account=mock_account)
    assert robot.is_usb_fault_detected
    assert robot.is_gas_sensor_fault_detected
    assert robot.is_firmware_updating
    assert robot.extended_scale_activity
    assert not robot.is_night_light_on
    assert robot.hopper_fault == "MOTOR_STALL"
    assert robot.globe_motor_retract_fault_status == "MtrFaultSet"

    await robot._account.disconnect()


async def test_litter_robot_5_setup_date(
    mock_account: Account,
) -> None:
    """Tests that setup_date reads from state dict for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.setup_date is not None
    assert robot.setup_date.year == 2025
    assert robot.setup_date.month == 11
    assert robot.setup_date.day == 28

    await robot._account.disconnect()


async def test_litter_robot_5_last_seen(
    mock_account: Account,
) -> None:
    """Tests that last_seen reads from state dict for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.last_seen is not None
    assert robot.last_seen.year == 2025
    assert robot.last_seen.month == 12

    await robot._account.disconnect()


async def test_litter_robot_5_send_subscribe_request(
    mock_account: Account,
) -> None:
    """Tests that send_subscribe_request is a no-op for LR5."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    # Should not raise
    await robot.send_subscribe_request()
    await robot.send_subscribe_request(send_stop=True)

    await robot._account.disconnect()


async def test_litter_robot_5_firmware_details_esp_fallback(
    mock_account: Account,
) -> None:
    """Tests that get_firmware_details falls back to espFirmwareVersion when wifiVersion is None."""
    data = deepcopy(LITTER_ROBOT_5_PRO_DATA)
    # Pro data has wifiVersion: None in firmwareVersions
    robot = LitterRobot5(data=data, account=mock_account)
    details = await robot.get_firmware_details()
    assert isinstance(details, dict)
    # Should fall back to espFirmwareVersion from state
    assert isinstance(details["latestFirmware"], dict)
    assert details["latestFirmware"]["espFirmwareVersion"] == "v2.5.6"

    await robot._account.disconnect()
