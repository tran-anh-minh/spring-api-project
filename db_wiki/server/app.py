from mcp.server.fastmcp import FastMCP

mcp = FastMCP("db-wiki")


def main() -> None:
    mcp.run()
