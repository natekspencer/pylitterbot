"""Test litterrobot4 module."""
# pylint: disable=protected-access
from datetime import datetime, timezone

import pytest
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.enums import LitterBoxStatus
from pylitterbot.exceptions import InvalidCommandException
from pylitterbot.robot.litterrobot4 import (
    LR4_ENDPOINT,
    LitterRobot4,
    NightLightLevel,
    NightLightMode,
)

from .common import LITTER_ROBOT_4_DATA


async def test_litter_robot_4_setup(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that a Litter-Robot 4 setup is successful and parses as expected."""
    robot = LitterRobot4(data=LITTER_ROBOT_4_DATA, account=mock_account)
    await robot.subscribe_for_updates()
    await robot.unsubscribe_from_updates()
    assert (
        str(robot)
        == "Name: Litter-Robot 4, Model: Litter-Robot 4, Serial: LR4C000001, id: LR4ID"
    )
    with pytest.warns(DeprecationWarning):
        assert robot.auto_offline_disabled
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_capacity == 58
    assert robot.cycle_count == 93
    assert robot.cycles_after_drawer_full == 0
    with pytest.warns(DeprecationWarning):
        assert robot.device_type is None
    with pytest.warns(DeprecationWarning):
        assert not robot.did_notify_offline
    with pytest.warns(DeprecationWarning):
        assert robot.drawer_full_indicator_cycle_count == 0
    assert robot.firmware == "ESP: 1.1.50 / PIC: 10512.2560.2.51 / TOF: 255.0.255.255"
    assert not robot.is_drawer_full_indicator_triggered
    assert robot.is_onboarded
    assert not robot.is_sleeping
    assert not robot.is_waste_drawer_full
    assert robot.last_seen == datetime(
        year=2022, month=7, day=20, minute=13, tzinfo=timezone.utc
    )
    assert robot.model == "Litter-Robot 4"
    assert robot.name == "Litter-Robot 4"
    assert robot.night_light_brightness == 255
    assert robot.night_light_level == NightLightLevel.HIGH
    assert robot.night_light_mode == NightLightMode.AUTO
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    assert robot.pet_weight == 7.93
    assert robot.power_status == "AC"
    assert robot.setup_date == datetime(
        year=2022, month=7, day=16, hour=21, minute=40, second=50, tzinfo=timezone.utc
    )
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

    await robot._account.disconnect()


def test_litter_robot_4_sleep_time(
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
