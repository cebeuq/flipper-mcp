"""Entry point: ``python -m flipper_mcp`` starts the stdio MCP server."""

from .server import mcp

if __name__ == "__main__":
    mcp.run()
