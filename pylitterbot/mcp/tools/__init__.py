"""Tool registration: import all tool modules so @mcp.tool() decorators fire."""

from pylitterbot.mcp.tools import (  # noqa: F401
    activity,
    commands,
    compound,
    pets,
    settings,
    status,
)
