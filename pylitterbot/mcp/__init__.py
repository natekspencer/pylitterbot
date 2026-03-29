"""MCP server for pylitterbot."""

from pylitterbot.mcp.server import mcp


def main() -> None:
    """Entry point for the MCP server."""
    # Import tools to register them with the server
    import pylitterbot.mcp.tools  # noqa: F401

    mcp.run()


__all__ = ["main", "mcp"]
