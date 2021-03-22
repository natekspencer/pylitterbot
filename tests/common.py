from unittest.mock import Mock, patch

from httpx._exceptions import ConnectError, HTTPStatusError
from pylitterbot import Account
from pylitterbot.robot import Robot

USERNAME = "username@username.com"
PASSWORD = "password"
TOKEN_RESPONSE = {
    "token_type": "Bearer",
    "access_token": "LR-Access-Token",
    "refresh_token": "LR-Refresh-Token",
    "expires_in": 3600,
}

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


async def get_account(
    mock_client, logged_in: bool = False, load_robots: bool = False
) -> Account:
    """Gets an account that has the underlying API patched."""
    with patch("pylitterbot.session.AsyncOAuth2Client", mock_client):
        account = Account()
        if logged_in:
            await account.connect(
                username=USERNAME, password=PASSWORD, load_robots=load_robots
            )
        return account


async def get_robot(mock_client, robot_id: str = ROBOT_ID) -> Robot:
    """Gets a robot that has the underlying API patched."""
    account = await get_account(mock_client, logged_in=True, load_robots=True)
    robot = next(filter(lambda robot: (robot.id == robot_id), account.robots))
    assert robot

    return robot


def mock_http_status_error(status_code):
    """Returns a mocked `httpx._exceptions.HTTPStatusError`."""
    return HTTPStatusError(
        Mock(), request=Mock(), response=Mock(status_code=status_code)
    )


def mock_connect_error():
    """Returns a mocked `httpx._exceptions.ConnectError`."""
    return ConnectError(Mock(), request=Mock())
