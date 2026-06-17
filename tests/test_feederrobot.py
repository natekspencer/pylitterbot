"""Test feederrobot module."""

# pylint: disable=protected-access
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from aiointercept import aiointercept
from freezegun.api import FrozenDateTimeFactory

from pylitterbot import Account
from pylitterbot.exceptions import InvalidCommandException
from pylitterbot.robot.feederrobot import (
    COMMAND_ENDPOINT,
    FEEDER_ENDPOINT,
    NO_SKIP,
    SCHEDULE_ENDPOINT,
    FeederRobot,
)
from pylitterbot.utils import utcnow

from .common import FEEDER_ROBOT_DATA

pytestmark = pytest.mark.asyncio


async def test_feeder_robot(
    mock_aiointercept: aiointercept,
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
    assert robot.is_on
    assert robot.is_online
    assert robot.last_feeding == robot.last_meal
    assert robot.meal_insert_size == 0.125
    assert robot.night_light_mode_enabled
    assert not robot.panel_lock_enabled
    with pytest.warns(DeprecationWarning, match="power_type"):
        assert robot.power_status == "AC"
    assert robot.power_type == "AC"

    utc = timezone.utc
    assert robot.get_food_dispensed_since(datetime(2022, 8, 1, tzinfo=utc)) == 0.75
    assert robot.get_food_dispensed_since(datetime(2022, 9, 1, tzinfo=utc)) == 0.5

    # simulate different power statuses
    FEEDER_ROBOT_DATA["state"]["info"]["power"] = False
    FEEDER_ROBOT_DATA["state"]["info"]["acPower"] = False
    robot._update_data(FEEDER_ROBOT_DATA)
    assert not robot.is_on
    with pytest.warns(DeprecationWarning, match="power_type"):  # type: ignore[unreachable]
        assert robot.power_status == "NC"
    assert robot.power_type == "NC"
    FEEDER_ROBOT_DATA["state"]["info"]["power"] = True
    FEEDER_ROBOT_DATA["state"]["info"]["dcPower"] = True
    robot._update_data(FEEDER_ROBOT_DATA)
    assert robot.is_on
    with pytest.warns(DeprecationWarning, match="power_type"):
        assert robot.power_status == "DC"
    assert robot.power_type == "DC"

    mock_aiointercept.clear()
    mock_aiointercept.post(
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

    mock_aiointercept.post(
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

    mock_aiointercept.post(COMMAND_ENDPOINT, repeat=True)
    assert await robot.give_snack()
    assert await robot.set_gravity_mode(True)
    assert robot.gravity_mode_enabled
    assert robot.next_feeding is None
    assert await robot.set_night_light(True)
    assert await robot.set_panel_lockout(True)

    mock_aiointercept.post(
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
    mock_aiointercept.post(
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
    freezer: FrozenDateTimeFactory,
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


async def test_feeder_robot_schedule_writes(
    freezer: FrozenDateTimeFactory,
    mock_aiointercept: aiointercept,
    mock_account: Account,
) -> None:
    """Tests that the feeding schedule can be edited, skipped, paused, and cleared."""
    # Pin the clock so the computed skip date is deterministic. The fixture
    # timezone is America/Denver and meal 1 ("Breakfast") runs at 06:30 daily,
    # so the next occurrence of meal 1 from this moment is later the same day.
    freezer.move_to("2022-07-21 00:00:00-06:00")
    robot = FeederRobot(data=deepcopy(FEEDER_ROBOT_DATA), account=mock_account)
    assert robot.active_schedule is not None

    mock_aiointercept.post(SCHEDULE_ENDPOINT, repeat=True)
    mock_aiointercept.post(f"{SCHEDULE_ENDPOINT}/clear", repeat=True)

    def meal(meal_number: int) -> dict:
        assert (schedule := robot.active_schedule) is not None
        return next(m for m in schedule["meals"] if m["mealNumber"] == meal_number)

    def last_request_json(url: str) -> dict:
        """Return the body of the most recent POST to ``url``.

        Asserts the endpoint was actually called, so a write that silently
        skipped its HTTP request would fail the test.
        """
        for (_method, request_url), calls in mock_aiointercept.requests.items():
            if str(request_url) == url:
                body: dict = calls[-1].kwargs["json"]
                return body
        raise AssertionError(f"no request was made to {url}")

    # Skip the next occurrence of meal 1 -> its date at midnight, then un-skip.
    assert await robot.skip_meal(1)
    assert meal(1)["skip"] == "2022-07-21T00:00:00.000"
    assert await robot.skip_meal(1, skip=False)
    assert meal(1)["skip"] == NO_SKIP

    # Pause / resume meal 1.
    assert await robot.pause_meal(1)
    assert meal(1)["paused"] is True
    assert await robot.pause_meal(1, paused=False)
    assert meal(1)["paused"] is False

    # Edit via set_schedule (e.g. change a meal time).
    assert (schedule := robot.active_schedule) is not None
    meals = deepcopy(schedule["meals"])
    meals[0]["hour"] = 9
    assert await robot.set_schedule(meals)
    assert meal(1)["hour"] == 9

    # The outbound payload carries the edit and the activation flag, and
    # translates the read model's snake_case ``created_at`` to ``createdAt``.
    sent = last_request_json(SCHEDULE_ENDPOINT)
    assert sent["setActive"] is True
    assert sent["schedule"]["serial"] == robot.serial
    assert sent["schedule"]["createdAt"] == "2021-12-17T07:07:31.047747+00:00"
    assert "created_at" not in sent["schedule"]
    assert (
        next(m for m in sent["schedule"]["meals"] if m["mealNumber"] == 1)["hour"] == 9
    )

    # Defensive copies: neither the dict returned by ``active_schedule`` nor the
    # list passed to ``set_schedule`` aliases internal state, so mutating them
    # afterwards does not silently change the robot without a REST write.
    snapshot = robot.active_schedule
    assert snapshot is not None
    snapshot["meals"][0]["hour"] = 3
    assert meal(1)["hour"] == 9

    edited = deepcopy(snapshot["meals"])
    edited[0]["hour"] = 7
    assert await robot.set_schedule(edited)
    assert meal(1)["hour"] == 7
    edited[0]["hour"] = 11  # mutate the caller's list after the write
    assert meal(1)["hour"] == 7

    # Unknown meal number raises for both skip and pause.
    with pytest.raises(InvalidCommandException):
        await robot.skip_meal(99)
    with pytest.raises(InvalidCommandException):
        await robot.pause_meal(99)

    # Clear the schedule.
    assert await robot.clear_schedule()
    assert (schedule := robot.active_schedule) is not None
    assert schedule["meals"] == []
    assert last_request_json(f"{SCHEDULE_ENDPOINT}/clear") == {"serial": robot.serial}

    # No active schedule -> meal writes raise, clear is still a no-op success.
    data = deepcopy(FEEDER_ROBOT_DATA)
    data["state"]["active_schedule"] = None
    robot._update_data(data)
    with pytest.raises(InvalidCommandException):
        await robot.skip_meal(1)
    with pytest.raises(InvalidCommandException):
        await robot.pause_meal(1)
    with pytest.raises(InvalidCommandException):
        await robot.set_schedule([])
    assert await robot.clear_schedule()

    await robot._account.disconnect()
