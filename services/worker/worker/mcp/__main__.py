"""Entry point: ``python -m worker.mcp`` / ``sarathi-mcp`` — stdio MCP server."""

from __future__ import annotations


def main() -> None:
    from worker.mcp.server import mcp

    mcp.run()  # stdio transport (default)


if __name__ == "__main__":
    main()
