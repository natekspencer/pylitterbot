"""Activity tools for MCP server."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from pylitterbot.enums import LitterBoxStatus
from pylitterbot.mcp.helpers import resolve_feeder_robot, resolve_litter_robot
from pylitterbot.mcp.server import mcp


@mcp.tool()
async def get_activity_history(robot: str, limit: int = 100) -> list[dict[str, str]]:
    """Get the activity log for a Litter-Robot.

    Args:
        robot: Robot name (case-insensitive) or ID.
        limit: Maximum number of activity entries to return (default 100).

    """
    resolved = await resolve_litter_robot(robot)
    activities = await resolved.get_activity_history(limit=limit)
    return [
        {
            "timestamp": str(a.timestamp),
            "action": a.action.text
            if isinstance(a.action, LitterBoxStatus)
            else str(a.action),
        }
        for a in activities
    ]


@mcp.tool()
async def get_insight(robot: str, days: int = 30) -> dict[str, Any]:
    """Get usage analytics for a Litter-Robot over a time period.

    Args:
        robot: Robot name (case-insensitive) or ID.
        days: Number of days to look back (default 30).

    """
    resolved = await resolve_litter_robot(robot)
    insight = await resolved.get_insight(days=days)
    return {
        "total_cycles": insight.total_cycles,
        "average_cycles": insight.average_cycles,
        "total_days": insight.total_days,
        "cycle_history": [
            {"date": str(d), "cycles": c} for d, c in insight.cycle_history
        ],
    }


@mcp.tool()
async def get_food_dispensed(robot: str, hours: int = 24) -> dict[str, Any]:
    """Get the amount of food dispensed by a Feeder-Robot over a time period.

    Args:
        robot: Robot name (case-insensitive) or ID.
        hours: Number of hours to look back (default 24).

    """
    resolved = await resolve_feeder_robot(robot)
    since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    cups = resolved.get_food_dispensed_since(since)
    return {
        "robot": resolved.name,
        "cups_dispensed": cups,
        "hours": hours,
    }
