"""Command tools for MCP server."""

from __future__ import annotations

from typing import Any

from pylitterbot.mcp.helpers import (
    resolve_feeder_robot,
    resolve_litter_robot,
    resolve_litter_robot_4,
    resolve_litter_robot_5,
    resolve_robot,
)
from pylitterbot.mcp.server import mcp
from pylitterbot.robot.litterrobot3 import LitterRobot3
from pylitterbot.robot.litterrobot4 import LitterRobot4
from pylitterbot.robot.litterrobot5 import LitterRobot5


@mcp.tool()
async def start_cleaning(robot: str) -> str:
    """Start a clean cycle on a Litter-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    ok = await resolved.start_cleaning()
    if not ok:
        raise RuntimeError(f"Failed to start cleaning cycle on '{resolved.name}'.")
    return f"Started cleaning cycle on '{resolved.name}'."


@mcp.tool()
async def reset_robot(robot: str) -> str:
    """Remote reset a Litter-Robot (LR4/LR5 only, clears errors).

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        raise ValueError(
            f"'{resolved.name}' ({resolved.model}) does not support remote reset. "
            "Only Litter-Robot 4 and 5 support this feature."
        )
    ok = await resolved.reset()
    if not ok:
        raise RuntimeError(f"Failed to reset '{resolved.name}'.")
    return f"Reset '{resolved.name}' successfully."


@mcp.tool()
async def give_snack(robot: str) -> str:
    """Dispense food from a Feeder-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_feeder_robot(robot)
    ok = await resolved.give_snack()
    if not ok:
        raise RuntimeError(f"Failed to dispense snack from '{resolved.name}'.")
    return f"Dispensed snack from '{resolved.name}'."


@mcp.tool()
async def set_power_status(robot: str, enabled: bool) -> str:
    """Turn a Litter-Robot on or off.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to turn on, False to turn off.

    """
    resolved = await resolve_litter_robot(robot)
    ok = await resolved.set_power_status(enabled)
    if not ok:
        raise RuntimeError(f"Failed to set power status on '{resolved.name}'.")
    state = "on" if enabled else "off"
    return f"Turned '{resolved.name}' {state}."


@mcp.tool()
async def toggle_hopper(robot: str, is_removed: bool) -> str:
    """Enable or disable the litter hopper on a Litter-Robot 4.

    Args:
        robot: Robot name (case-insensitive) or ID.
        is_removed: True to remove/disable the hopper, False to install/enable.

    """
    resolved = await resolve_litter_robot_4(robot)
    ok = await resolved.toggle_hopper(is_removed)
    if not ok:
        raise RuntimeError(f"Failed to toggle hopper on '{resolved.name}'.")
    state = "removed" if is_removed else "installed"
    return f"Hopper {state} on '{resolved.name}'."


@mcp.tool()
async def reset_waste_drawer(robot: str) -> str:
    """Reset the waste drawer level indicator on a Litter-Robot 3 or 5.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    if not isinstance(resolved, (LitterRobot3, LitterRobot5)):
        raise ValueError(
            f"Waste drawer reset is only supported on Litter-Robot 3 and 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    ok = await resolved.reset_waste_drawer()
    if not ok:
        raise RuntimeError(f"Failed to reset waste drawer on '{resolved.name}'.")
    return f"Waste drawer reset on '{resolved.name}'."


@mcp.tool()
async def reset_settings(robot: str) -> str:
    """Reset a Litter-Robot 3 to default settings.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    if not isinstance(resolved, LitterRobot3):
        raise ValueError(
            f"Settings reset is only supported on Litter-Robot 3, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    ok = await resolved.reset_settings()
    if not ok:
        raise RuntimeError(f"Failed to reset settings on '{resolved.name}'.")
    return f"Settings reset on '{resolved.name}'."


@mcp.tool()
async def change_filter(robot: str) -> str:
    """Reset the filter replacement counter on a Litter-Robot 5.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot_5(robot)
    ok = await resolved.change_filter()
    if not ok:
        raise RuntimeError(f"Failed to reset filter counter on '{resolved.name}'.")
    return f"Filter replacement counter reset on '{resolved.name}'."


@mcp.tool()
async def update_firmware(robot: str) -> str:
    """Trigger a firmware update on a Litter-Robot 4.

    Note: The Litter-Robot 5 REST API does not expose a firmware update
    trigger endpoint, so this tool is restricted to Litter-Robot 4.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_litter_robot(robot)
    if not isinstance(resolved, LitterRobot4):
        raise ValueError(
            f"Firmware update is only supported on Litter-Robot 4, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    ok = await resolved.update_firmware()
    if not ok:
        raise RuntimeError(f"Failed to trigger firmware update on '{resolved.name}'.")
    return f"Firmware update triggered on '{resolved.name}'."


@mcp.tool()
async def get_firmware_details(robot: str) -> dict[str, Any]:
    """Get firmware version details for a Litter-Robot 4 or 5.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        raise ValueError(
            f"Firmware details are only supported on Litter-Robot 4 and 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    details = await resolved.get_firmware_details()
    return details or {}
