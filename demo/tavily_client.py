"""
Connects to the Tavily MCP server and converts its tools
into LangChain-compatible tools via langchain-mcp-adapters.
"""

import os
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from config import TAVILY_API_KEY

import sys

_VENV_PYTHON = os.path.join(os.path.dirname(__file__), "venv", "bin", "python")

server_params = StdioServerParameters(
    command=_VENV_PYTHON if os.path.exists(_VENV_PYTHON) else sys.executable,
    args=["-m", "mcp_server_tavily"],
    env={
        **os.environ,
        "TAVILY_API_KEY": TAVILY_API_KEY,
    },
)


@asynccontextmanager
async def tavily_mcp_session():
    """
    Open a Tavily MCP subprocess and yield a live MCP session.
    """
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def get_tavily_tools(session):
    """Convert Tavily MCP tools into LangChain tools."""
    return await load_mcp_tools(session)


# Quick test
if __name__ == "__main__":
    import asyncio

    async def main():
        async with tavily_mcp_session() as session:
            tools = await get_tavily_tools(session)
            print(f"Loaded {len(tools)} Tavily tools:")
            for t in tools:
                print(f"  - {t.name}: {t.description[:80]}...")

    asyncio.run(main())
