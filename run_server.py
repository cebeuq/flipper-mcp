"""Launcher for the flipper MCP server.

Run as `python run_server.py`. Because the script lives at the project root,
Python puts that directory on sys.path, so `import flipper_mcp` works without
setting PYTHONPATH — convenient for registering with Claude Code by path.
"""

from flipper_mcp.server import main

if __name__ == "__main__":
    main()
