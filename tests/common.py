"""Common test module."""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

from aiohttp import ClientConnectorError, ClientResponseError, ClientWebSocketResponse

from pylitterbot import Account, LitterRobot
from pylitterbot.robot.litterrobot3 import DEFAULT_ENDPOINT

USERNAME = "username@username.com"
PASSWORD = "password"

USER_ID = "000000"
USER_RESPONSE = {
    "user": {
        "lastName": "User",
        "userEmail": USERNAME,
        "userId": USER_ID,
        "firstName": "Test",
    }
}

ROBOT_ID = "a0123b4567cd8e"
ROBOT_NAME = "Test"
ROBOT_SERIAL = "LR3C012345"
ROBOT_DATA = {
    "powerStatus": "AC",
    "lastSeen": "2021-02-01T00:30:00.000000",
    "cleanCycleWaitTimeMinutes": "7",
    "unitStatus": "RDY",
    "litterRobotNickname": ROBOT_NAME,
    "cycleCount": "15",
    "panelLockActive": "0",
    "cyclesAfterDrawerFull": "0",
    "litterRobotSerial": ROBOT_SERIAL,
    "cycleCapacity": "30",
    "litterRobotId": ROBOT_ID,
    "nightLightActive": "1",
    "isDFITriggered": "0",
    "sleepModeActive": "102:00:00",
    "deviceType": "udp",
    "isOnboarded": True,
    "setupDate": "2021-01-01T00:00:00.000000",
}

ROBOT_FULL_ID = "a9876b5432cd1e"
ROBOT_FULL_NAME = "Full Test"
ROBOT_FULL_SERIAL = "LR3C987654"
ROBOT_FULL_DATA = {
    "powerStatus": "AC",
    "lastSeen": "2021-02-01T00:30:00.000000",
    "cleanCycleWaitTimeMinutes": "7",
    "unitStatus": "DF1",
    "litterRobotNickname": ROBOT_FULL_NAME,
    "cycleCount": "28",
    "panelLockActive": "0",
    "cyclesAfterDrawerFull": "0",
    "litterRobotSerial": ROBOT_FULL_SERIAL,
    "cycleCapacity": "30",
    "litterRobotId": ROBOT_FULL_ID,
    "nightLightActive": "1",
    "isDFITriggered": "1",
    "sleepModeActive": "102:00:00",
    "deviceType": "udp",
    "isOnboarded": True,
    "setupDate": "2021-01-01T00:00:00.000000",
}

ROBOT_ENDPOINT = f"{DEFAULT_ENDPOINT}/users/{USER_ID}/robots/%s"


COMMAND_RESPONSE = {
    "_developerMessage": "Command: <COMMAND> posted to litterRobotId: <LR-ID>",
}

INVALID_COMMAND_RESPONSE = {
    "status_code": "500",
    "developerMessage": "Invalid command: <W12",
    "type": "InvalidCommandException",
    "userMessage": "Server Error",
    "request_id": "Mock-LR-Request-ID",
}

ACTIVITY_RESPONSE = {
    "activities": [
        {
            "timestamp": "2021-03-01T00:01:00.000000",
            "unitStatus": "RDY",
        },
        {
            "timestamp": "2021-03-01T00:00:00.000000",
            "unitStatus": "CCC",
        },
    ]
}

ACTIVITY_FULL_RESPONSE = {
    "activities": [
        {
            "timestamp": "2021-03-01T00:01:00.000000",
            "unitStatus": "CST",
        },
        {
            "timestamp": "2021-03-01T00:00:00.000000",
            "unitStatus": "DF1",
        },
    ]
}

INSIGHT_RESPONSE = {
    "totalCycles": 3,
    "averageCycles": 1.5,
    "cycleHistory": [
        {"date": "2021-03-01", "cyclesCompleted": 1},
        {"date": "2021-02-28", "cyclesCompleted": 2},
    ],
}

LITTER_ROBOT_4_DATA: dict[str, Any] = {
    "unitId": "LR4ID",
    "name": "Litter-Robot 4",
    "serial": "LR4C000001",
    "userId": "000001",
    "espFirmware": "1.1.50",
    "picFirmwareVersion": "10512.2560.2.51",
    "laserBoardFirmwareVersion": "255.0.255.255",
    "unitPowerType": "AC",
    "catWeight": 7.93,
    "unitTimezone": "America/Denver",
    "cleanCycleWaitTime": 7,
    "isKeypadLockout": False,
    "nightLightMode": "AUTO",
    "nightLightBrightness": 255,
    "isPanelSleepMode": False,
    "panelSleepTime": 0,
    "panelWakeTime": 0,
    "weekdaySleepModeEnabled": {
        "Sunday": {"sleepTime": 0, "wakeTime": 510, "isEnabled": True},
        "Monday": {"sleepTime": 1410, "wakeTime": 450, "isEnabled": True},
        "Tuesday": {"sleepTime": 1410, "wakeTime": 450, "isEnabled": True},
        "Wednesday": {"sleepTime": 1410, "wakeTime": 450, "isEnabled": True},
        "Thursday": {"sleepTime": 1410, "wakeTime": 450, "isEnabled": True},
        "Friday": {"sleepTime": 1410, "wakeTime": 450, "isEnabled": True},
        "Saturday": {"sleepTime": 1380, "wakeTime": 510, "isEnabled": False},
    },
    "unitPowerStatus": "ON",
    "sleepStatus": "WAKE",
    "robotStatus": "ROBOT_IDLE",
    "globeMotorFaultStatus": "FAULT_CLEAR",
    "pinchStatus": "CLEAR",
    "catDetect": "CAT_DETECT_SCALE_CLEAR",
    "isBonnetRemoved": False,
    "isNightLightLEDOn": True,
    "odometerPowerCycles": 9,
    "odometerCleanCycles": 93,
    "odometerEmptyCycles": 0,
    "odometerFilterCycles": 0,
    "isDFIResetPending": False,
    "DFINumberOfCycles": 58,
    "DFILevelPercent": 91,
    "isDFIFull": False,
    "DFIFullCounter": 0,
    "DFITriggerCount": 33,
    "litterLevel": 475,
    "DFILevelMM": 115,
    "isCatDetectPending": False,
    "globeMotorRetractFaultStatus": "FAULT_CLEAR",
    "robotCycleStatus": "CYCLE_IDLE",
    "robotCycleState": "CYCLE_STATE_WAIT_ON",
    "weightSensor": 0.9,
    "isOnline": True,
    "isOnboarded": True,
    "lastSeen": "2022-07-20T00:13:00.000Z",
    "setupDateTime": "2022-07-16T21:40:50.000Z",
}


async def get_account(logged_in: bool = False, load_robots: bool = False) -> Account:
    """Get an account that has the underlying API patched."""
    with patch(
        "pylitterbot.session.ClientSession.ws_connect",
        return_value=ClientWebSocketResponse(
            Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), Mock(), Mock()
        ),
    ):
        account = Account()
        if logged_in:
            await account.connect(
                username=USERNAME, password=PASSWORD, load_robots=load_robots
            )
        return account


async def get_robot(robot_id: str = ROBOT_ID) -> LitterRobot:
    """Get a robot that has the underlying API patched."""
    account = await get_account(logged_in=True, load_robots=True)
    robot = next(
        filter(
            lambda robot: (robot.id == robot_id),
            [robot for robot in account.robots if isinstance(robot, LitterRobot)],
        )
    )
    assert robot

    return robot


def mock_client_response_error(status: int | None = None) -> ClientResponseError:
    """Return a mocked `aiohttp.ClientResponseError`."""
    return ClientResponseError(Mock(), Mock(), status=status)


def mock_client_connector_error() -> ClientConnectorError:
    """Return a mocked `aiohttp.ClientConnectorError`."""
    return ClientConnectorError(Mock(), Mock())
