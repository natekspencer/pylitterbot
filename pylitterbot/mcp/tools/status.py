"""Status tools for MCP server."""

from __future__ import annotations

from typing import Any

from pylitterbot.mcp.helpers import format_robot_summary, resolve_robot
from pylitterbot.mcp.server import get_account, mcp


@mcp.tool()
async def get_robots() -> list[dict[str, Any]]:
    """List all robots with current status summary.

    Returns a list of robot summaries including name, model, online status,
    and model-specific details like waste drawer level or food level.
    """
    account = await get_account()
    await account.refresh_robots()
    return [format_robot_summary(robot) for robot in account.robots]


@mcp.tool()
async def get_robot_status(robot: str) -> dict[str, Any]:
    """Get detailed status for one robot.

    Args:
        robot: Robot name (case-insensitive) or ID.

    Returns a detailed summary including waste level, cycle count, power,
    sleep status, and model-specific details.
    """
    resolved = await resolve_robot(robot)
    await resolved.refresh()
    return format_robot_summary(resolved)
