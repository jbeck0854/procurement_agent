"""
Connects to postgres-mcp server and converts its tools
into LangChain-compatible tools via langchain-mcp-adapters.
"""

from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

from config import DATABASE_URL

# How to start the postgres-mcp subprocess
server_params = StdioServerParameters(
    command="postgres-mcp",
    args=[DATABASE_URL, "--access-mode", "unrestricted"],
)


@asynccontextmanager
async def mcp_session():
    """
    Open a postgres-mcp subprocess and yield a live MCP session.
    The subprocess stays alive as long as the caller is inside
    the 'async with' block.
    """
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def get_mcp_tools(session):
    """Convert MCP tools into LangChain tools."""
    return await load_mcp_tools(session)


# Quick test
if __name__ == "__main__":
    import asyncio

    async def main():
        async with mcp_session() as session:
            tools = await get_mcp_tools(session)
            print(f"Loaded {len(tools)} MCP tools:")
            for t in tools:
                print(f"  - {t.name}: {t.description[:80]}...")

    asyncio.run(main())
