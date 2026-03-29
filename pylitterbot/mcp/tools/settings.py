"""Settings tools for MCP server."""

from __future__ import annotations

from datetime import time

from pylitterbot.enums import NightLightMode
from pylitterbot.mcp.helpers import resolve_litter_robot, resolve_robot
from pylitterbot.mcp.server import mcp
from pylitterbot.robot.litterrobot4 import LitterRobot4


@mcp.tool()
async def set_name(robot: str, name: str) -> str:
    """Rename a robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        name: The new name for the robot.

    """
    resolved = await resolve_robot(robot)
    await resolved.set_name(name)
    return f"Renamed robot to '{name}'."


@mcp.tool()
async def set_night_light(robot: str, enabled: bool) -> str:
    """Enable or disable the night light on a robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to enable, False to disable.

    """
    resolved = await resolve_robot(robot)
    await resolved.set_night_light(enabled)
    state = "enabled" if enabled else "disabled"
    return f"Night light {state} on '{resolved.name}'."


@mcp.tool()
async def set_night_light_brightness(robot: str, brightness: int) -> str:
    """Set the night light brightness on a Litter-Robot 4.

    Args:
        robot: Robot name (case-insensitive) or ID.
        brightness: Brightness level (25=low, 50=medium, 100=high).

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot4):
        raise ValueError(
            f"Night light brightness is only supported on Litter-Robot 4, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    await resolved.set_night_light_brightness(brightness)
    return f"Night light brightness set to {brightness} on '{resolved.name}'."


@mcp.tool()
async def set_night_light_mode(robot: str, mode: str) -> str:
    """Set the night light mode on a Litter-Robot 4.

    Args:
        robot: Robot name (case-insensitive) or ID.
        mode: Night light mode - "off", "on", or "auto" (case-insensitive).

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot4):
        raise ValueError(
            f"Night light mode is only supported on Litter-Robot 4, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    try:
        night_light_mode = NightLightMode(mode.upper())
    except ValueError:
        valid = ", ".join(m.value.lower() for m in NightLightMode)
        raise ValueError(
            f"Invalid night light mode '{mode}'. Valid modes: {valid}"
        ) from None
    await resolved.set_night_light_mode(night_light_mode)
    return f"Night light mode set to '{mode.lower()}' on '{resolved.name}'."


@mcp.tool()
async def set_panel_lockout(robot: str, enabled: bool) -> str:
    """Enable or disable the button lock on a robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to lock buttons, False to unlock.

    """
    resolved = await resolve_robot(robot)
    await resolved.set_panel_lockout(enabled)
    state = "enabled" if enabled else "disabled"
    return f"Panel lockout {state} on '{resolved.name}'."


@mcp.tool()
async def set_wait_time(robot: str, minutes: int) -> str:
    """Set the clean cycle delay on a Litter-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        minutes: Wait time in minutes. LR3: 3, 7, 15. LR4/LR5: 3, 7, 15, 25, 30.

    """
    resolved = await resolve_litter_robot(robot)
    await resolved.set_wait_time(minutes)
    return f"Wait time set to {minutes} minutes on '{resolved.name}'."


@mcp.tool()
async def set_sleep_mode(
    robot: str, enabled: bool, start_time: str | None = None
) -> str:
    """Configure sleep mode on a Litter-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to enable sleep mode, False to disable.
        start_time: Sleep start time in HH:MM format (24-hour). Required when enabling.

    """
    resolved = await resolve_litter_robot(robot)
    sleep_time = None
    if enabled:
        if not start_time:
            raise ValueError("start_time is required when enabling sleep mode.")
        try:
            parts = start_time.split(":")
            sleep_time = time(int(parts[0]), int(parts[1]))
        except (IndexError, ValueError) as exc:
            raise ValueError(
                f"Invalid start_time '{start_time}'. Expected HH:MM (24-hour), e.g. '22:30'."
            ) from exc
    await resolved.set_sleep_mode(enabled, sleep_time)
    state = "enabled" if enabled else "disabled"
    return f"Sleep mode {state} on '{resolved.name}'."
