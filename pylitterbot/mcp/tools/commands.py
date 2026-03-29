"""Command tools for MCP server."""

from __future__ import annotations

from pylitterbot.mcp.helpers import resolve_feeder_robot, resolve_litter_robot
from pylitterbot.mcp.server import mcp
from pylitterbot.robot.litterrobot4 import LitterRobot4
from pylitterbot.robot.litterrobot5 import LitterRobot5


@mcp.tool()
async def start_cleaning(robot: str) -> str:
    """Start a clean cycle on a Litter-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    await resolved.start_cleaning()
    return f"Started cleaning cycle on '{resolved.name}'."


@mcp.tool()
async def reset_robot(robot: str) -> str:
    """Remote reset a Litter-Robot (LR4/LR5 only, clears errors).

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        return (
            f"'{resolved.name}' ({resolved.model}) does not support remote reset. "
            "Only Litter-Robot 4 and 5 support this feature."
        )
    await resolved.reset()
    return f"Reset '{resolved.name}' successfully."


@mcp.tool()
async def give_snack(robot: str) -> str:
    """Dispense food from a Feeder-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_feeder_robot(robot)
    await resolved.give_snack()
    return f"Dispensed snack from '{resolved.name}'."


@mcp.tool()
async def set_power_status(robot: str, enabled: bool) -> str:
    """Turn a Litter-Robot on or off.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to turn on, False to turn off.

    """
    resolved = await resolve_litter_robot(robot)
    await resolved.set_power_status(enabled)
    state = "on" if enabled else "off"
    return f"Turned '{resolved.name}' {state}."
