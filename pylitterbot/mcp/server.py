"""FastMCP server instance and Account lifecycle management.

Note:
    This server does not re-authenticate on session expiry. For long-running
    MCP sessions, if credentials expire or the upstream token becomes invalid,
    all tool calls will fail until the process is restarted. Restart the MCP
    server process to re-auth.

"""

from __future__ import annotations

import asyncio
import os

from mcp.server.fastmcp import FastMCP

from pylitterbot import Account

mcp = FastMCP("litter-robot")

_account: Account | None = None
_account_lock = asyncio.Lock()


async def get_account() -> Account:
    """Get or create the connected Account. Lazy initialization."""
    global _account
    if _account is not None:
        return _account
    async with _account_lock:
        if _account is not None:
            return _account
        username = os.environ.get("LITTER_ROBOT_USERNAME")
        password = os.environ.get("LITTER_ROBOT_PASSWORD")
        if not username or not password:
            raise RuntimeError(
                "LITTER_ROBOT_USERNAME and LITTER_ROBOT_PASSWORD environment "
                "variables are required."
            )
        account = Account()
        try:
            await account.connect(
                username=username,
                password=password,
                load_robots=True,
                load_pets=True,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to connect to Litter-Robot account. Check credentials."
            ) from exc
        _account = account
    return _account
