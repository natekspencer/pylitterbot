"""Tool registration: import all tool modules so @mcp.tool() decorators fire."""

from pylitterbot.mcp.tools import activity, commands, compound, pets, settings, status  # noqa: F401
