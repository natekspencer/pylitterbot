"""Pet tools for MCP server."""

from __future__ import annotations

from typing import Any

from pylitterbot.mcp.helpers import format_pet_summary, resolve_robot
from pylitterbot.mcp.server import get_account, mcp
from pylitterbot.robot.litterrobot5 import LitterRobot5


def _resolve_pet_id(pets: list, identifier: str) -> str:
    """Find a pet by name (case-insensitive) or ID and return its ID."""
    normalized = identifier.casefold()
    for pet in pets:
        name = pet.name or ""
        if name.casefold() == normalized or str(pet.id) == identifier:
            return pet.id
    available = ", ".join(p.name for p in pets)
    raise ValueError(f"No pet found matching '{identifier}'. Available: {available}")


@mcp.tool()
async def get_pets() -> list[dict[str, Any]]:
    """List all pets linked to the account.

    Returns a list of pet summaries including name, type, gender, weight,
    and breeds.
    """
    account = await get_account()
    await account.load_pets()
    return [format_pet_summary(pet) for pet in account.pets]


@mcp.tool()
async def reassign_pet_visit(
    robot: str, event_id: str, from_pet: str, to_pet: str
) -> str:
    """Reassign a detected pet visit to a different pet (Litter-Robot 5 only).

    Args:
        robot: Robot name (case-insensitive) or ID.
        event_id: The event ID of the activity to reassign.
        from_pet: Name or ID of the pet currently assigned to the visit.
        to_pet: Name or ID of the pet to reassign the visit to.

    Note:
        Both from_pet and to_pet are required. Unassigning a visit (leaving
        to_pet empty) is not supported by this tool; use the library directly
        if needed.

    """
    event_id = event_id.strip()
    if not event_id:
        raise ValueError("event_id must be a non-empty string.")
    resolved = await resolve_robot(robot)
    if not isinstance(resolved, LitterRobot5):
        raise ValueError(
            f"Pet visit reassignment is only supported on Litter-Robot 5, "
            f"but '{resolved.name}' is a {resolved.model}."
        )
    account = await get_account()
    from_pet_id = _resolve_pet_id(account.pets, from_pet)
    to_pet_id = _resolve_pet_id(account.pets, to_pet)
    await resolved.reassign_pet_visit(
        event_id, from_pet_id=from_pet_id, to_pet_id=to_pet_id
    )
    return (
        f"Reassigned visit '{event_id}' on '{resolved.name}' "
        f"from '{from_pet}' to '{to_pet}'."
    )
