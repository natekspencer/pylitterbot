"""Test feederrobot module."""
# pylint: disable=protected-access
import pytest
from aioresponses import aioresponses

from pylitterbot import Account
from pylitterbot.exceptions import InvalidCommandException
from pylitterbot.robot.feederrobot import COMMAND_ENDPOINT, FEEDER_ENDPOINT, FeederRobot

from .common import FEEDER_ROBOT_DATA

pytestmark = pytest.mark.asyncio


async def test_feeder_robot(
    mock_aioresponse: aioresponses,
    mock_account: Account,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that a Feeder-Robot setup is successful and parses as expected."""
    robot = FeederRobot(data=FEEDER_ROBOT_DATA, account=mock_account)
    await robot.subscribe_for_updates()
    await robot.unsubscribe_from_updates()
    assert (
        str(robot)
        == "Name: Feeder-Robot, Model: Feeder-Robot, Serial: RF1C000001, id: 1"
    )
    assert robot.firmware == "1.0.0"
    assert robot.food_level == 20
    assert robot.last_feeding == robot.last_meal
    assert robot.meal_insert_size == 0.125
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled

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

    assert not await robot.get_activity_history()
    assert (await robot.get_insight()).total_cycles == 0

    await robot._account.disconnect()
