"""Compound tools for MCP server — multi-endpoint operations."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from pylitterbot.enums import LitterBoxStatus
from pylitterbot.mcp.helpers import (
    format_pet_summary,
    format_robot_summary,
    resolve_robot,
)
from pylitterbot.mcp.server import get_account, mcp
from pylitterbot.robot.litterrobot import LitterRobot
from pylitterbot.robot.litterrobot4 import LitterRobot4

logger = logging.getLogger(__name__)

_ATTENTION_STATUSES = {
    LitterBoxStatus.DRAWER_FULL,
    LitterBoxStatus.DRAWER_FULL_1,
    LitterBoxStatus.DRAWER_FULL_2,
    LitterBoxStatus.STARTUP_DRAWER_FULL,
    LitterBoxStatus.OFFLINE,
    LitterBoxStatus.BONNET_REMOVED,
    LitterBoxStatus.CAT_SENSOR_FAULT,
    LitterBoxStatus.DUMP_HOME_POSITION_FAULT,
    LitterBoxStatus.DUMP_POSITION_FAULT,
    LitterBoxStatus.HOME_POSITION_FAULT,
    LitterBoxStatus.OVER_TORQUE_FAULT,
    LitterBoxStatus.PINCH_DETECT,
    LitterBoxStatus.STARTUP_CAT_SENSOR_FAULT,
    LitterBoxStatus.STARTUP_PINCH_DETECT,
}

_STATUS_SKIP_REASONS = {
    LitterBoxStatus.CAT_DETECTED: "cat detected",
    LitterBoxStatus.CAT_SENSOR_TIMING: "cat sensor timing",
    LitterBoxStatus.CLEAN_CYCLE: "already cleaning",
    LitterBoxStatus.CLEAN_CYCLE_COMPLETE: "clean cycle completing",
    LitterBoxStatus.DRAWER_FULL: "drawer full",
    LitterBoxStatus.DRAWER_FULL_1: "drawer almost full",
    LitterBoxStatus.DRAWER_FULL_2: "drawer almost full",
    LitterBoxStatus.OFF: "powered off",
    LitterBoxStatus.OFFLINE: "offline",
    LitterBoxStatus.PAUSED: "paused",
    LitterBoxStatus.EMPTY_CYCLE: "empty cycle in progress",
}


def _needs_attention(robot: LitterRobot) -> bool:
    """Return True if a LitterRobot needs attention."""
    if not robot.is_online:
        return True
    if robot.is_waste_drawer_full:
        return True
    if robot.status in _ATTENTION_STATUSES:
        return True
    return False


@mcp.tool()
async def fleet_overview() -> dict[str, Any]:
    """Get a prioritized overview of all robots.

    Returns robots partitioned into those needing attention (drawer full,
    errors, offline) and healthy ones, with full status summaries.
    """
    account = await get_account()
    await account.refresh_robots()

    needs_attention = []
    healthy = []

    for robot in account.robots:
        summary = format_robot_summary(robot)
        if isinstance(robot, LitterRobot) and _needs_attention(robot):
            needs_attention.append(summary)
        else:
            healthy.append(summary)

    return {
        "needs_attention": needs_attention,
        "healthy": healthy,
        "total_robots": len(account.robots),
    }


@mcp.tool()
async def clean_all_ready() -> dict[str, Any]:
    """Start cleaning on all Litter-Robots that are in READY state.

    Returns a report of which robots were cleaned and which were skipped
    with reasons (cat detected, already cycling, drawer full, etc.).
    """
    account = await get_account()
    await account.refresh_robots()

    cleaned = []
    skipped = []

    for robot in account.robots:
        if not isinstance(robot, LitterRobot):
            continue
        if robot.status == LitterBoxStatus.READY:
            try:
                await robot.start_cleaning()
                cleaned.append({"name": robot.name, "status": "cleaning started"})
            except Exception:
                logger.debug(
                    "Failed to start cleaning for %s", robot.name, exc_info=True
                )
                skipped.append(
                    {"name": robot.name, "reason": "failed to start cleaning"}
                )
        else:
            reason = _STATUS_SKIP_REASONS.get(
                robot.status, robot.status.text or "unknown"
            )
            skipped.append({"name": robot.name, "reason": reason})

    return {"cleaned": cleaned, "skipped": skipped}


@mcp.tool()
async def sync_settings(source_robot: str) -> dict[str, Any]:
    """Copy settings from one Litter-Robot to all others of the same model.

    Reads wait time, night light, panel lock, and sleep mode from the source
    and applies them to each target robot. For LR4s, also syncs night light
    brightness and mode.

    Args:
        source_robot: Name or ID of the source robot.

    """
    source = await resolve_robot(source_robot)
    if not isinstance(source, LitterRobot):
        raise ValueError(f"'{source.name}' is not a Litter-Robot.")

    account = await get_account()
    targets = []

    for robot in account.robots:
        if robot.id == source.id:
            continue
        if not isinstance(robot, LitterRobot):
            continue
        if robot.model != source.model:
            continue

        changes = []

        old_wait = robot.clean_cycle_wait_time_minutes
        if old_wait != source.clean_cycle_wait_time_minutes:
            await robot.set_wait_time(source.clean_cycle_wait_time_minutes)
            changes.append(
                f"wait_time: {old_wait} -> {source.clean_cycle_wait_time_minutes}"
            )

        old_night_light = robot.night_light_mode_enabled
        if old_night_light != source.night_light_mode_enabled:
            await robot.set_night_light(source.night_light_mode_enabled)
            changes.append(
                f"night_light: {old_night_light} -> {source.night_light_mode_enabled}"
            )

        old_panel_lock = robot.panel_lock_enabled
        if old_panel_lock != source.panel_lock_enabled:
            await robot.set_panel_lockout(source.panel_lock_enabled)
            changes.append(
                f"panel_lock: {old_panel_lock} -> {source.panel_lock_enabled}"
            )

        old_sleep = robot.sleep_mode_enabled
        if old_sleep != source.sleep_mode_enabled:
            sleep_time = (
                source.sleep_mode_start_time.timetz()
                if source.sleep_mode_start_time
                else None
            )
            await robot.set_sleep_mode(source.sleep_mode_enabled, sleep_time)
            changes.append(f"sleep_mode: {old_sleep} -> {source.sleep_mode_enabled}")

        if isinstance(source, LitterRobot4) and isinstance(robot, LitterRobot4):
            old_brightness = robot.night_light_brightness
            if old_brightness != source.night_light_brightness:
                await robot.set_night_light_brightness(source.night_light_brightness)
                changes.append(
                    f"night_light_brightness: {old_brightness} -> {source.night_light_brightness}"
                )

            old_mode = robot.night_light_mode
            if (
                old_mode != source.night_light_mode
                and source.night_light_mode is not None
            ):
                await robot.set_night_light_mode(source.night_light_mode)
                changes.append(
                    f"night_light_mode: {old_mode} -> {source.night_light_mode}"
                )

        targets.append({"name": robot.name, "changes": changes})

    return {"source": source.name, "targets": targets}


@mcp.tool()
async def pet_usage_report() -> dict[str, Any]:
    """Generate a per-pet usage report across all robots.

    Aggregates recent activity data (up to 100 entries) from all Litter-Robots
    and lists all pets. Note: direct pet-to-activity attribution may be limited
    depending on the robot model.
    """
    account = await get_account()
    await account.refresh_robots()
    await account.load_pets()

    robot_summaries = []
    for robot in account.robots:
        if not isinstance(robot, LitterRobot):
            continue
        try:
            activities = await robot.get_activity_history(limit=100)
            robot_summaries.append(
                {
                    "name": robot.name,
                    "activity_count": len(activities),
                }
            )
        except Exception:
            logger.debug(
                "Failed to retrieve activity for %s", robot.name, exc_info=True
            )
            robot_summaries.append(
                {
                    "name": robot.name,
                    "activity_count": 0,
                    "error": "Could not retrieve activity",
                }
            )

    pet_summaries = [format_pet_summary(pet) for pet in account.pets]

    return {
        "pets": pet_summaries,
        "robots": robot_summaries,
    }


@mcp.tool()
async def maintenance_forecast() -> list[dict[str, Any]]:
    """Estimate when each Litter-Robot's waste drawer will be full.

    Uses current cycle count, capacity, and recent cycle rate from insights
    to estimate days remaining. Sorted by urgency (fewest days first).
    """
    account = await get_account()
    await account.refresh_robots()

    forecasts = []
    for robot in account.robots:
        if not isinstance(robot, LitterRobot):
            continue

        cycles_remaining = max(0, robot.cycle_capacity - robot.cycle_count)

        try:
            insight = await robot.get_insight(days=7)
            avg_cycles_per_day = insight.average_cycles
        except Exception:
            avg_cycles_per_day = 0.0

        if avg_cycles_per_day > 0:
            estimated_days = cycles_remaining / avg_cycles_per_day
        else:
            estimated_days = None

        forecasts.append(
            {
                "name": robot.name,
                "waste_drawer_level": robot.waste_drawer_level,
                "cycles_remaining": cycles_remaining,
                "avg_cycles_per_day": avg_cycles_per_day,
                "estimated_days_remaining": round(estimated_days, 1)
                if estimated_days is not None
                else None,
            }
        )

    forecasts.sort(
        key=lambda f: (
            f["estimated_days_remaining"]
            if f["estimated_days_remaining"] is not None
            else float("inf")
        )
    )
    return forecasts


@mcp.tool()
async def household_digest(days: int = 7) -> dict[str, Any]:
    """Generate a time-bounded household activity digest.

    Combines insights and activity across all robots and pets for the
    specified period.

    Args:
        days: Number of days to cover (default 7).

    """
    if days < 1:
        raise ValueError("days must be >= 1.")
    account = await get_account()
    await account.refresh_robots()
    await account.load_pets()

    total_cycles = 0
    robot_data = []
    alerts = []

    for robot in account.robots:
        if not isinstance(robot, LitterRobot):
            continue
        try:
            insight = await robot.get_insight(days=days)
            total_cycles += insight.total_cycles
            robot_data.append(
                {
                    "name": robot.name,
                    "cycles": insight.total_cycles,
                    "average_per_day": insight.average_cycles,
                }
            )
        except Exception:
            robot_data.append(
                {
                    "name": robot.name,
                    "cycles": 0,
                    "error": "Could not retrieve insight data",
                }
            )

        if _needs_attention(robot):
            alerts.append(
                {
                    "robot": robot.name,
                    "status": robot.status.text,
                }
            )

    pet_summaries = [format_pet_summary(pet) for pet in account.pets]

    return {
        "period_days": days,
        "total_cycles": total_cycles,
        "robots": robot_data,
        "pets": pet_summaries,
        "alerts": alerts,
    }


@mcp.tool()
async def troubleshooting_report(robot: str) -> dict[str, Any]:
    """Generate a diagnostic report for a robot.

    Gathers current status, recent activity, firmware details, and error
    flags into a single report for troubleshooting.

    Args:
        robot: Robot name (case-insensitive) or ID.

    """
    resolved = await resolve_robot(robot)
    await resolved.refresh()

    report: dict[str, Any] = format_robot_summary(resolved)

    if isinstance(resolved, LitterRobot):
        try:
            activities = await resolved.get_activity_history(limit=50)
            report["recent_activity"] = [
                {
                    "timestamp": str(a.timestamp),
                    "action": a.action.text
                    if isinstance(a.action, LitterBoxStatus)
                    else str(a.action),
                }
                for a in activities
            ]
        except Exception:
            report["recent_activity"] = []

    if isinstance(resolved, LitterRobot4):
        report["firmware"] = resolved.firmware
        report["status_code"] = resolved.status_code
        report["globe_motor_fault"] = resolved.globe_motor_fault_status.name
        report["usb_fault"] = (
            resolved.usb_fault_status.name if resolved.usb_fault_status else None
        )
        try:
            report["firmware_details"] = await resolved.get_firmware_details()
        except Exception:
            report["firmware_details"] = None

    return report


@mcp.tool()
async def robot_comparison() -> dict[str, Any]:
    """Compare settings and performance across all robots.

    Groups robots by model type and highlights setting inconsistencies
    and performance outliers within each group.
    """
    account = await get_account()
    await account.refresh_robots()

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for robot in account.robots:
        summary = format_robot_summary(robot)
        groups[robot.model].append(summary)

    result_groups = []
    for model, robots in groups.items():
        inconsistencies = []
        outliers = []

        if len(robots) > 1 and all(
            "clean_cycle_wait_time_minutes" in r for r in robots
        ):
            wait_times = {r["name"]: r["clean_cycle_wait_time_minutes"] for r in robots}
            if len(set(wait_times.values())) > 1:
                inconsistencies.append({"setting": "wait_time", "values": wait_times})

        if len(robots) > 1 and all("cycle_count" in r for r in robots):
            cycle_counts = {r["name"]: r["cycle_count"] for r in robots}
            values = list(cycle_counts.values())
            if values and max(values) > 2 * min(values) and min(values) > 0:
                outliers.append({"metric": "cycle_count", "values": cycle_counts})

        result_groups.append(
            {
                "model": model,
                "robots": robots,
                "inconsistencies": inconsistencies,
                "outliers": outliers,
            }
        )

    return {"groups": result_groups}
