"""Test litterrobot5 module."""

# pylint: disable=protected-access
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from aiohttp.typedefs import URL
from aioresponses import CallbackResult

from pylitterbot.enums import LitterBoxStatus
from pylitterbot.robot.litterrobot5 import (
    LR5_CAMERA_CANVAS_FRONT,
    LR5_CAMERA_CANVAS_GLOBE,
    LR5_CAMERA_INVENTORY_ENDPOINT,
    LR5_CAMERA_SETTINGS_ENDPOINT,
    LR5_ENDPOINT,
    LR5_OTAUPDATE_ENDPOINT,
    BrightnessLevel,
    HopperStatus,
    LitterLevelState,
    LitterRobot5,
    NightLightMode,
)
from pylitterbot.utils import utcnow

from .common import LITTER_ROBOT_5_DATA, get_account

pytestmark = pytest.mark.asyncio


async def test_litter_robot_5_properties(mock_account: Any) -> None:
    """Tests that a Litter-Robot 5 setup is successful and parses as expected."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)

    assert (
        str(robot)
        == "Name: Litter-Robot 5, Model: Litter-Robot 5, Serial: LR5-00-00-00-0000-000000, id: LR5-00-00-00-0000-000000"
    )

    assert robot.timezone == "America/Los_Angeles"
    assert robot.robot_variant == "LR5_PRO"
    assert robot.updated_at == datetime(
        year=2026,
        month=1,
        day=19,
        hour=13,
        minute=41,
        second=57,
        microsecond=483000,
        tzinfo=timezone.utc,
    )
    assert robot.next_filter_replacement_date == datetime(
        year=2026,
        month=2,
        day=26,
        hour=23,
        minute=0,
        second=36,
        microsecond=347000,
        tzinfo=timezone.utc,
    )
    assert robot.camera_device_id == "aabbccdd11223344aabbcc00"
    assert robot.camera_serial_number == "E0000000000000A"
    assert robot.camera_space_id == "aabbccdd11223344aabbcc01"
    assert robot.wifi_rssi == 0
    assert robot.is_night_light_on is True
    assert robot.is_drawer_removed is False
    assert robot.is_usb_fault_detected is False
    assert robot.is_gas_sensor_fault_detected is False
    assert robot.is_laser_dirty is False
    assert robot.pinch_status == "Clear"
    assert robot.display_code == "DcModeIdle"
    assert robot.cycle_state == "StWaitOn"
    assert robot.cycle_type == "StCycleIdle"
    assert robot.cat_detect == "WeightClear"
    assert robot.privacy_mode == "Normal"
    assert robot.pet_weight_raw == 1110.0
    assert robot.pet_weight == pytest.approx(11.1)
    assert robot.clean_cycle_wait_time_minutes == 7
    assert robot.cycle_count == 183
    assert robot.cycles_after_drawer_full == 0
    assert not robot.is_drawer_full_indicator_triggered

    assert robot.is_online
    assert not robot.is_sleeping
    assert not robot.is_waste_drawer_full

    assert robot.hopper_status == HopperStatus.DISABLED
    assert robot.is_hopper_removed is True

    assert robot.litter_level == 76.74
    assert robot.litter_level_state == LitterLevelState.OPTIMAL

    assert robot.night_light_brightness == 69
    assert robot.night_light_mode == NightLightMode.AUTO
    assert robot.night_light_mode_enabled

    assert robot.panel_brightness == BrightnessLevel.MEDIUM
    assert not robot.panel_lock_enabled

    assert robot.power_status == "On"
    assert robot.setup_date == datetime(
        year=2026,
        month=1,
        day=27,
        hour=23,
        minute=0,
        second=36,
        microsecond=347000,
        tzinfo=timezone.utc,
    )
    assert robot.last_seen == datetime(
        year=2026,
        month=2,
        day=8,
        hour=7,
        minute=26,
        second=58,
        microsecond=390000,
        tzinfo=timezone.utc,
    )

    assert robot.status == LitterBoxStatus.READY
    assert robot.status_code == LitterBoxStatus.READY.value

    assert robot.waste_drawer_level == 34


async def test_litter_robot_5_write_endpoints(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Ensure LR5 write helpers hit expected REST endpoints."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    url = f"{LR5_ENDPOINT}/robots/{robot.serial}"

    # Rename uses PATCH /robots/{serial} returning 204.
    mock_aioresponse.patch(url, status=204, body="")
    new_name = "Test Name"
    assert robot.name != new_name
    assert await robot.set_name(new_name)
    assert robot.name == new_name
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "name": new_name
    }

    # Night light toggle uses PATCH /robots/{serial} with nightLightSettings.mode.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light(False)
    is_enabled = robot.night_light_mode_enabled
    assert is_enabled is False
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"mode": "Off"}
    }

    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light(True)
    is_enabled = robot.night_light_mode_enabled
    assert is_enabled is True
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"mode": "Auto"}
    }

    # Panel lock uses PATCH /robots/{serial} with panelSettings.isKeypadLocked.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_panel_lockout(True)
    assert robot.panel_lock_enabled is True
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "panelSettings": {"isKeypadLocked": True}
    }

    # Wait time uses PATCH /robots/{serial} with litterRobotSettings.cycleDelay.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_wait_time(15)
    assert robot.clean_cycle_wait_time_minutes == 15
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "litterRobotSettings": {"cycleDelay": 15}
    }

    # Panel brightness uses PATCH /robots/{serial} with panelSettings.displayIntensity.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_panel_brightness(BrightnessLevel.HIGH)
    assert robot.panel_brightness == BrightnessLevel.HIGH
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "panelSettings": {"displayIntensity": "High"}
    }

    # Night light brightness uses PATCH /robots/{serial} with nightLightSettings.brightness.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light_brightness(42)
    assert robot.night_light_brightness == 42
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"brightness": 42}
    }

    # Night light color uses PATCH /robots/{serial} with nightLightSettings.color.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light_color("#FFF5")
    assert robot.night_light_color == "#FFF5"
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"mode": "Auto", "brightness": 42, "color": "#FFF5"}
    }

    # Night light mode setter uses PATCH /robots/{serial} with nightLightSettings.mode.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light_mode(NightLightMode.OFF)
    mode = robot.night_light_mode
    assert mode == NightLightMode.OFF
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"mode": "Off"}
    }

    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_night_light_mode(NightLightMode.ON)
    mode = robot.night_light_mode
    assert mode == NightLightMode.ON
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "nightLightSettings": {"mode": "On"}
    }

    # Sound settings use PATCH /robots/{serial} with soundSettings nested keys.
    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_sound_volume(5)
    assert robot.sound_volume == 5
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "soundSettings": {"volume": 5}
    }

    mock_aioresponse.patch(url, status=204, body="")
    assert await robot.set_camera_audio_enabled(True)
    assert robot.camera_audio_enabled is True
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "soundSettings": {"cameraAudioEnabled": True}
    }

    # Sleep schedule uses PATCH /robots/{serial} with sleepSchedules list.
    mock_aioresponse.patch(url, status=204, body="")
    sleep_enabled = robot.sleep_mode_enabled
    assert sleep_enabled is False
    assert await robot.set_sleep_schedule(
        0, is_enabled=True, sleep_time=60, wake_time=120
    )
    sleep_enabled = robot.sleep_mode_enabled
    assert sleep_enabled is True
    expected_schedules = [
        {"dayOfWeek": 0, "isEnabled": True, "sleepTime": 60, "wakeTime": 120},
        {"dayOfWeek": 1, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 2, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 3, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 4, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 5, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
        {"dayOfWeek": 6, "isEnabled": False, "sleepTime": 0, "wakeTime": 0},
    ]
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "sleepSchedules": expected_schedules
    }

    # Power + clean use the command bus endpoint.
    cmd_url = f"{LR5_ENDPOINT}/robots/{robot.serial}/commands"
    mock_aioresponse.post(cmd_url, status=200, body="")
    assert await robot.set_power_status(True)
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "type": "POWER_ON"
    }

    mock_aioresponse.post(cmd_url, status=200, body="")
    assert await robot.start_cleaning()
    assert list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json") == {
        "type": "CLEAN_CYCLE"
    }


async def test_litter_robot_5_firmware_details_from_state(mock_account: Any) -> None:
    """Ensure LR5 firmware details are derived from the robot state payload."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    details = await robot.get_firmware_details()

    assert details == {
        "isFirmwareUpdating": False,
        "currentFirmware": {
            "mcuVersion": "v5.7.5 2904_0106",
            "cameraVersion": "1.2.2-1233",
            "edgeVersion": "1.5.22",
            "aiVersion": "0.0.43",
        },
    }


async def test_litter_robot_5_firmware_latest_from_otaupdate(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Return latest firmware string when the OTA update service provides it."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    mock_aioresponse.post(
        LR5_OTAUPDATE_ENDPOINT,
        payload={
            "data": {
                "checkUpdateStatusBySerial": {
                    "serialNumber": robot.serial,
                    "status": "AVAILABLE",
                    "progress": None,
                    "currentFirmware": "v1.0.0",
                    "latestFirmware": "v1.0.1",
                    "message": None,
                }
            }
        },
    )

    try:
        assert await robot.get_latest_firmware(force_check=True) == "v1.0.1"
    finally:
        await mock_account.disconnect()


async def test_litter_robot_5_firmware_update_availability_from_otaupdate(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Return update availability based on the OTA update service status field."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    mock_aioresponse.post(
        LR5_OTAUPDATE_ENDPOINT,
        payload={
            "data": {
                "checkUpdateStatusBySerial": {
                    "serialNumber": robot.serial,
                    "status": "UNAVAILABLE",
                    "progress": None,
                    "currentFirmware": "v1.0.0",
                    "latestFirmware": None,
                    "message": None,
                }
            }
        },
    )

    try:
        assert await robot.has_firmware_update(force_check=True) is False
    finally:
        await mock_account.disconnect()


async def test_litter_robot_5_update_firmware_triggers_otaupdate_mutation(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Trigger a firmware update via the OTA update GraphQL mutation."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    mock_aioresponse.post(
        LR5_OTAUPDATE_ENDPOINT,
        payload={
            "data": {
                "triggerRobotUpdateBySerial": {
                    "success": True,
                    "serialNumber": robot.serial,
                    "message": None,
                }
            }
        },
    )

    try:
        assert await robot.update_firmware() is True
        assert (
            list(mock_aioresponse.requests.items())[-1][-1][-1].kwargs.get("json", {})
        ).get("variables") == {"serialNumber": robot.serial}
    finally:
        await mock_account.disconnect()


async def test_litter_robot_5_firmware_latest_falls_back_to_user_query(
    mock_aioresponse: Any,
) -> None:
    """Fall back to user-scoped status when serial query returns a marshal error."""
    account = await get_account(logged_in=True)
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=account)

    def ota_callback(_: URL, **kwargs: Any) -> CallbackResult:
        query = (kwargs.get("json") or {}).get("query") or ""
        if "checkUpdateStatusBySerial" in query:
            return CallbackResult(
                payload={
                    "data": {"checkUpdateStatusBySerial": None},
                    "errors": [
                        {
                            "message": "Unable to marshal response: Object of type TypeError is not JSON serializable"
                        }
                    ],
                }
            )
        if "checkUpdateStatusByUser" in query:
            return CallbackResult(
                payload={
                    "data": {
                        "checkUpdateStatusByUser": [
                            {
                                "serialNumber": robot.serial,
                                "status": "AVAILABLE",
                                "progress": None,
                                "currentFirmware": "v1.0.0",
                                "latestFirmware": "v1.0.1",
                                "message": None,
                            }
                        ]
                    }
                }
            )
        raise AssertionError(f"Unexpected OTA update query: {query}")

    mock_aioresponse.post(LR5_OTAUPDATE_ENDPOINT, callback=ota_callback, repeat=True)
    try:
        assert await robot.get_latest_firmware(force_check=True) == "v1.0.1"
    finally:
        await account.disconnect()


async def test_litter_robot_5_camera_session_bootstrap(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Ensure camera session bootstrap hits the expected Ienso endpoint."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.camera_device_id

    url = (
        "https://watford.ienso-dev.com/api/device-manager/client/generate-session/"
        f"{robot.camera_device_id}?autoStart=true"
    )
    payload = {
        "autoStart": True,
        "sessionExpiration": "2026-02-11T10:05:14.000Z",
        "sessionId": "SESSION_ID",
        "sessionToken": "SESSION_TOKEN",
        "signalingURL": "wss://watford.ienso-dev.com/api/signaling",
        "turnServer": {
            "password": "TURN_PW",
            "stunUrl": "stun:coturn.watford-prod.ienso-dev.com:3478",
            "turnUrl": ["turn:coturn.watford-prod.ienso-dev.com:3478"],
            "username": "TURN_USER",
        },
    }
    mock_aioresponse.get(url, payload=payload, status=200)

    assert await robot.get_camera_session(auto_start=True) == payload


async def test_litter_robot_5_camera_canvas_get_set(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Ensure LR5 can fetch and set camera live-view canvas."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.camera_device_id

    reported_url = (
        f"{LR5_CAMERA_SETTINGS_ENDPOINT}/{robot.camera_device_id}"
        "/reported-settings/videoSettings"
    )
    desired_url = (
        f"{LR5_CAMERA_SETTINGS_ENDPOINT}/{robot.camera_device_id}"
        "/desired-settings/videoSettings"
    )

    state = {"canvas": LR5_CAMERA_CANVAS_FRONT}

    def reported_callback(_: URL, **_kwargs: Any) -> CallbackResult:
        return CallbackResult(
            payload={
                "reportedSettings": [
                    {
                        "settingsType": "videoSettings",
                        "data": {"streams": {"live-view": {"canvas": state["canvas"]}}},
                    }
                ]
            }
        )

    def desired_callback(_: URL, **kwargs: Any) -> CallbackResult:
        payload = (kwargs.get("json") or {}).get("streams") or {}
        live = payload.get("live-view") if isinstance(payload, dict) else None
        if isinstance(live, dict) and isinstance(live.get("canvas"), str):
            state["canvas"] = live["canvas"]
        return CallbackResult(payload={"ok": True})

    mock_aioresponse.get(reported_url, callback=reported_callback, repeat=True)
    mock_aioresponse.patch(desired_url, callback=desired_callback, repeat=True)

    assert await robot.get_camera_live_canvas() == LR5_CAMERA_CANVAS_FRONT
    assert await robot.set_camera_live_canvas(
        LR5_CAMERA_CANVAS_GLOBE, timeout_seconds=2.0
    )
    assert await robot.get_camera_live_canvas() == LR5_CAMERA_CANVAS_GLOBE


async def test_litter_robot_5_camera_inventory_videos_events(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Ensure LR5 can fetch camera inventory, videos, and events lists."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    assert robot.camera_device_id

    inv_url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{robot.camera_device_id}"
    vids_url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{robot.camera_device_id}/videos"
    events_url = f"{LR5_CAMERA_INVENTORY_ENDPOINT}/{robot.camera_device_id}/events"

    mock_aioresponse.get(
        inv_url,
        payload={
            "deviceType": "LR5_CAMERA",
            "name": "LR5 Camera",
            "serial": "CAM-123",
            "settings": {"motionRecordingType": "ALWAYS"},
        },
    )
    mock_aioresponse.get(
        vids_url,
        payload=[
            {
                "id": 1,
                "createdAt": 1.0,
                "eventType": "cat_identified",
                "hlsDuration": "00:10",
                "videoThumbnail": "https://example.invalid/thumb.jpg?AWSAccessKeyId=**REDACTED**",
            }
        ],
    )
    mock_aioresponse.get(
        events_url,
        payload=[
            {
                "id": 10,
                "type": "ai_event",
                "createdAt": 2.0,
                "metadata": {"eventType": "cat_identified"},
            }
        ],
    )

    inv = await robot.get_camera_inventory()
    assert isinstance(inv, dict)
    assert inv.get("deviceType") == "LR5_CAMERA"

    vids = await robot.get_camera_videos()
    assert isinstance(vids, list)
    assert vids[0]["id"] == 1

    events = await robot.get_camera_events()
    assert isinstance(events, list)
    assert events[0]["id"] == 10


async def test_litter_robot_5_insight_computed_from_activities(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Compute insights from activities when no insights endpoint exists."""
    now = utcnow().replace(microsecond=0)
    today_1 = now.replace(hour=10, minute=0, second=0)
    today_2 = now.replace(hour=12, minute=0, second=0)
    yesterday = today_1 - timedelta(days=1)

    robot_data = {**LITTER_ROBOT_5_DATA, "timezone": "UTC"}
    robot = LitterRobot5(data=robot_data, account=mock_account)

    activities = [
        {
            "type": "CYCLE_COMPLETED",
            "timestamp": today_2.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventId": "e1",
        },
        {
            "type": "PET_VISIT",
            "timestamp": today_1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventId": "e2",
        },
        {
            "type": "CYCLE_COMPLETED",
            "timestamp": today_1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventId": "e3",
        },
        {
            "type": "CYCLE_COMPLETED",
            "timestamp": yesterday.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventId": "e4",
        },
        {
            "type": "CYCLE_COMPLETED",
            "timestamp": (today_1 - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "eventId": "e5",
        },
    ]

    base = f"{LR5_ENDPOINT}/robots/{robot.serial}/activities"
    mock_aioresponse.get(
        re.compile(rf"^{re.escape(base)}\?limit=100&offset=0$"),
        payload=activities,
        repeat=False,
    )

    insight = await robot.get_insight(days=2)
    assert insight.total_cycles == 3
    assert insight.average_cycles == 1.5
    assert insight.cycle_history[0] == (today_1.date(), 2)
    assert insight.cycle_history[1] == (yesterday.date(), 1)


async def test_litter_robot_5_activity_history_formats_pet_weight(
    mock_aioresponse: Any, mock_account: Any
) -> None:
    """Ensure PET_VISIT activities include the converted pet weight in lbs."""
    robot = LitterRobot5(data=LITTER_ROBOT_5_DATA, account=mock_account)
    url = f"{LR5_ENDPOINT}/robots/{robot.serial}/activities?limit=10"

    mock_aioresponse.get(
        url,
        payload=[
            {
                "type": "PET_VISIT",
                "timestamp": "2026-02-11T05:27:01Z",
                "petWeight": 1107.0,
            }
        ],
    )

    activities = await robot.get_activity_history(limit=10)
    assert len(activities) == 1
    assert activities[0].action == "Pet Visit: 11.07 lbs"
