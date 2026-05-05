"""Minimal MCP echo server for testing routing."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("EchoServer")


@mcp.tool()
def echo(text: str) -> str:
    return f"echo: {text}"


if __name__ == "__main__":
    mcp.run()
