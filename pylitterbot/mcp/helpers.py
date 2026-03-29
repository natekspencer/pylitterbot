"""Robot resolution and output formatting helpers."""

from __future__ import annotations

from typing import Any

from pylitterbot import FeederRobot, LitterRobot, Pet
from pylitterbot.robot import Robot
from pylitterbot.robot.litterrobot4 import LitterRobot4

from .server import get_account


async def resolve_robot(identifier: str) -> Robot:
    """Find a robot by name (case-insensitive) or ID."""
    account = await get_account()
    for robot in account.robots:
        if robot.name.lower() == identifier.lower() or robot.id == identifier:
            return robot
    available = ", ".join(r.name for r in account.robots)
    raise ValueError(
        f"No robot found matching '{identifier}'. Available: {available}"
    )


async def resolve_litter_robot(identifier: str) -> LitterRobot:
    """Find a LitterRobot by name or ID. Raises if the robot is not a Litter-Robot."""
    robot = await resolve_robot(identifier)
    if not isinstance(robot, LitterRobot):
        raise ValueError(
            f"'{robot.name}' is not a Litter-Robot (it is a {robot.model})."
        )
    return robot


async def resolve_feeder_robot(identifier: str) -> FeederRobot:
    """Find a FeederRobot by name or ID. Raises if the robot is not a Feeder-Robot."""
    robot = await resolve_robot(identifier)
    if not isinstance(robot, FeederRobot):
        raise ValueError(
            f"'{robot.name}' is not a Feeder-Robot (it is a {robot.model})."
        )
    return robot


def format_robot_summary(robot: Robot) -> dict[str, Any]:
    """Return a summary dict with common and model-specific fields."""
    summary: dict[str, Any] = {
        "name": robot.name,
        "id": robot.id,
        "model": robot.model,
        "serial": robot.serial,
        "is_online": robot.is_online,
        "power_status": robot.power_status,
    }

    if isinstance(robot, LitterRobot):
        summary.update(
            {
                "status": robot.status.text,
                "waste_drawer_level": robot.waste_drawer_level,
                "cycle_count": robot.cycle_count,
                "cycle_capacity": robot.cycle_capacity,
                "is_sleeping": robot.is_sleeping,
                "clean_cycle_wait_time_minutes": robot.clean_cycle_wait_time_minutes,
            }
        )

    if isinstance(robot, LitterRobot4):
        summary.update(
            {
                "litter_level": robot.litter_level,
                "night_light_mode": robot.night_light_mode.name
                if robot.night_light_mode
                else None,
                "pet_weight": robot.pet_weight,
            }
        )

    if isinstance(robot, FeederRobot):
        summary.update(
            {
                "food_level": robot.food_level,
                "meal_insert_size": robot.meal_insert_size,
                "last_feeding": robot.last_feeding,
            }
        )

    return summary


def format_pet_summary(pet: Pet) -> dict[str, Any]:
    """Return a summary dict for a pet."""
    return {
        "name": pet.name,
        "id": pet.id,
        "pet_type": pet.pet_type.name if pet.pet_type else None,
        "gender": pet.gender.name if pet.gender else None,
        "weight": pet.weight,
        "breeds": pet.breeds,
        "is_active": pet.is_active,
    }
