"""Test feederrobot module."""

# pylint: disable=protected-access
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.exceptions import InvalidCommandException
from pylitterbot.robot.feederrobot import COMMAND_ENDPOINT, FEEDER_ENDPOINT, FeederRobot
from pylitterbot.utils import utcnow

from .common import FEEDER_ROBOT_DATA

pytestmark = pytest.mark.asyncio


async def test_feeder_robot(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that a Feeder-Robot setup is successful and parses as expected."""
    robot = FeederRobot(data=FEEDER_ROBOT_DATA, account=mock_account)
    await robot.subscribe()
    await robot.unsubscribe()
    assert (
        str(robot)
        == "Name: Feeder-Robot, Model: Feeder-Robot, Serial: RF1C000001, id: 1"
    )
    assert robot.firmware == "1.0.0"
    assert robot.food_level == 10
    assert not robot.gravity_mode_enabled
    assert robot.is_online
    assert robot.last_feeding == robot.last_meal
    assert robot.meal_insert_size == 0.125
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    assert robot.power_status == "AC"

    utc = timezone.utc
    assert robot.get_food_dispensed_since(datetime(2022, 8, 1, tzinfo=utc)) == 0.75
    assert robot.get_food_dispensed_since(datetime(2022, 9, 1, tzinfo=utc)) == 0.5

    # simulate different power statuses
    FEEDER_ROBOT_DATA["state"]["info"]["acPower"] = False
    robot._update_data(FEEDER_ROBOT_DATA)
    assert robot.power_status == "NC"
    FEEDER_ROBOT_DATA["state"]["info"]["dcPower"] = True
    robot._update_data(FEEDER_ROBOT_DATA)
    assert robot.power_status == "DC"

    mock_aioresponse.clear()
    mock_aioresponse.post(
        FEEDER_ENDPOINT,
        payload={
            "data": {
                "feeder_unit_by_pk": {
                    **FEEDER_ROBOT_DATA,
                    "feeding_meal": [],
                }
            }
        },
    )
    await robot.refresh()
    assert robot.last_meal is None
    assert robot.last_feeding == robot.last_snack

    mock_aioresponse.post(
        FEEDER_ENDPOINT,
        payload={
            "data": {
                "feeder_unit_by_pk": {
                    **FEEDER_ROBOT_DATA,
                    "feeding_snack": [],
                    "feeding_meal": [],
                    "state": {
                        **(state := FEEDER_ROBOT_DATA["state"]),
                        "info": {
                            **state["info"],
                            "mealInsertSize": 2,
                        },
                    },
                }
            }
        },
    )
    await robot.refresh()
    assert robot.last_feeding is None
    assert robot.last_meal is None
    assert robot.last_snack is None
    assert robot.meal_insert_size == 0
    assert caplog.messages[-1] == 'Unknown meal insert size "2"'

    mock_aioresponse.post(COMMAND_ENDPOINT, repeat=True)
    assert await robot.give_snack()
    assert await robot.set_gravity_mode(True)
    assert robot.gravity_mode_enabled
    assert robot.next_feeding is None  # type: ignore[unreachable]
    assert await robot.set_night_light(True)
    assert await robot.set_panel_lockout(True)

    mock_aioresponse.post(
        FEEDER_ENDPOINT,
        payload={
            "data": {
                "update_feeder_unit_state_by_pk": {
                    **(state := FEEDER_ROBOT_DATA["state"]),
                    "info": {
                        **state["info"],
                        "mealInsertSize": 0,
                    },
                }
            }
        },
    )
    with pytest.raises(InvalidCommandException):
        await robot.set_meal_insert_size(0)
    assert await robot.set_meal_insert_size(0.25)
    assert robot.meal_insert_size == 0.25

    new_name = "New Name"
    mock_aioresponse.post(
        FEEDER_ENDPOINT,
        payload={
            "data": {
                "update_feeder_unit_by_pk": {**FEEDER_ROBOT_DATA, "name": new_name}
            }
        },
    )
    assert await robot.set_name(new_name)
    assert robot.name == new_name

    await robot._account.disconnect()


@pytest.mark.parametrize(
    "freezer_date,expected_value",
    [
        ("2022-07-21 00:00:00-06:00", "2022-07-21T06:30:00-06:00"),
        ("2022-07-21 07:00:00-06:00", "2022-07-22T06:30:00-06:00"),
        ("2022-07-22 00:00:00-06:00", "2022-07-22T06:30:00-06:00"),
        ("2022-07-22 07:00:00-06:00", "2022-07-22T12:00:00-06:00"),
    ],
)
async def test_feeder_robot_schedule(
    freezer: pytest.fixture,
    mock_account: Account,
    freezer_date: str,
    expected_value: str,
) -> None:
    """Tests that a Litter-Robot 4 parses sleep time as expected."""
    freezer.move_to(freezer_date)
    robot = FeederRobot(data=FEEDER_ROBOT_DATA, account=mock_account)

    assert not robot.gravity_mode_enabled

    assert (next_feeding := robot.next_feeding)
    assert next_feeding.isoformat() == expected_value

    freezer.move_to(next_feeding + timedelta(seconds=1))
    assert robot.next_feeding != next_feeding

    data = deepcopy(FEEDER_ROBOT_DATA)
    data["state"]["active_schedule"] = None
    data["state"]["updated_at"] = utcnow().isoformat()
    robot._update_data(data)
    assert robot.next_feeding is None
