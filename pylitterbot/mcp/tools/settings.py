"""Settings tools for MCP server."""

from __future__ import annotations

from datetime import datetime

from pylitterbot.enums import BrightnessLevel, NightLightMode
from pylitterbot.mcp.helpers import (
    resolve_feeder_robot,
    resolve_litter_robot,
    resolve_robot,
)
from pylitterbot.mcp.server import mcp
from pylitterbot.robot.litterrobot4 import LitterRobot4
from pylitterbot.robot.litterrobot5 import LitterRobot5


@mcp.tool()
async def set_name(robot: str, name: str) -> str:
    """Rename a robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        name: The new name for the robot.

    """
    name = name.strip()
    if not name:
        raise ValueError("name must be a non-empty string.")
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
    """Set the night light brightness on a Litter-Robot 4 or 5.

    Args:
        robot: Robot name (case-insensitive) or ID.
        brightness: Brightness level. LR4: 25 (low), 50 (medium), 100 (high). LR5: 0-100.

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        raise ValueError(
            f"Night light brightness is only supported on Litter-Robot 4 and 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    if isinstance(resolved, LitterRobot5):
        if not 0 <= brightness <= 100:
            raise ValueError(
                f"Invalid brightness {brightness}. Must be between 0 and 100."
            )
    else:
        valid_brightness = {25, 50, 100}
        if brightness not in valid_brightness:
            raise ValueError(
                f"Invalid brightness {brightness}. Must be one of: {sorted(valid_brightness)}"
            )
    await resolved.set_night_light_brightness(brightness)
    return f"Night light brightness set to {brightness} on '{resolved.name}'."


@mcp.tool()
async def set_night_light_mode(robot: str, mode: str) -> str:
    """Set the night light mode on a Litter-Robot 4 or 5.

    Args:
        robot: Robot name (case-insensitive) or ID.
        mode: Night light mode - "off", "on", or "auto" (case-insensitive).

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        raise ValueError(
            f"Night light mode is only supported on Litter-Robot 4 and 5, "
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
    valid_wait_times = set(resolved.VALID_WAIT_TIMES)
    if minutes not in valid_wait_times:
        raise ValueError(
            f"Invalid wait time {minutes} for {resolved.model}. "
            f"Must be one of: {sorted(valid_wait_times)}"
        )
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
            sleep_time = datetime.strptime(start_time, "%H:%M").time()
        except ValueError as exc:
            raise ValueError(
                f"Invalid start_time '{start_time}'. Expected HH:MM (24-hour), e.g. '22:30'."
            ) from exc
    await resolved.set_sleep_mode(enabled, sleep_time)
    state = "enabled" if enabled else "disabled"
    return f"Sleep mode {state} on '{resolved.name}'."


@mcp.tool()
async def set_panel_brightness(robot: str, brightness: int) -> str:
    """Set the panel display brightness on a Litter-Robot 4 or 5.

    Args:
        robot: Robot name (case-insensitive) or ID.
        brightness: Brightness level (25=low, 50=medium, 100=high).

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, (LitterRobot4, LitterRobot5)):
        raise ValueError(
            f"Panel brightness is only supported on Litter-Robot 4 and 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    try:
        level = BrightnessLevel(brightness)
    except ValueError:
        valid = ", ".join(str(b.value) for b in BrightnessLevel)
        raise ValueError(
            f"Invalid brightness {brightness}. Must be one of: {valid}"
        ) from None
    await resolved.set_panel_brightness(level)
    return f"Panel brightness set to {brightness} on '{resolved.name}'."


@mcp.tool()
async def set_volume(robot: str, volume: int) -> str:
    """Set the sound volume on a Litter-Robot 5.

    Args:
        robot: Robot name (case-insensitive) or ID.
        volume: Volume level (0-100).

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot5):
        raise ValueError(
            f"Volume is only supported on Litter-Robot 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    if not 0 <= volume <= 100:
        raise ValueError(f"Invalid volume {volume}. Must be between 0 and 100.")
    await resolved.set_volume(volume)
    return f"Volume set to {volume} on '{resolved.name}'."


@mcp.tool()
async def set_privacy_mode(robot: str, enabled: bool) -> str:
    """Enable or disable privacy mode on a Litter-Robot 5.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to enable privacy mode, False to disable.

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot5):
        raise ValueError(
            f"Privacy mode is only supported on Litter-Robot 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    await resolved.set_privacy_mode(enabled)
    state = "enabled" if enabled else "disabled"
    return f"Privacy mode {state} on '{resolved.name}'."


@mcp.tool()
async def set_camera_audio(robot: str, enabled: bool) -> str:
    """Enable or disable camera audio on a Litter-Robot 5 (Pro only).

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to enable camera audio, False to disable.

    """
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot5):
        raise ValueError(
            f"Camera audio is only supported on Litter-Robot 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    await resolved.set_camera_audio(enabled)
    state = "enabled" if enabled else "disabled"
    return f"Camera audio {state} on '{resolved.name}'."


@mcp.tool()
async def set_gravity_mode(robot: str, enabled: bool) -> str:
    """Enable or disable gravity mode on a Feeder-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        enabled: True to enable gravity mode, False to disable.

    """
    resolved = await resolve_feeder_robot(robot)
    await resolved.set_gravity_mode(enabled)
    state = "enabled" if enabled else "disabled"
    return f"Gravity mode {state} on '{resolved.name}'."
