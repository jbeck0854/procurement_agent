from contextlib import asynccontextmanager

from langgraph.prebuilt import create_react_agent

from llm import get_llm
from mcp_client import mcp_session, get_mcp_tools
from tools.scoring import score_suppliers


@asynccontextmanager
async def create_agent():
    llm = get_llm()
    async with mcp_session() as session:
        mcp_tools = await get_mcp_tools(session)
        all_tools = [*mcp_tools, score_suppliers]
        agent = create_react_agent(llm, all_tools)
        yield agent


if __name__ == "__main__":
    import asyncio

    async def main():
        async with create_agent() as agent:
            result = await agent.ainvoke(
                {"messages": [("user", "How many suppliers are in the database?")]}
            )
            print(result["messages"][-1].content)

    asyncio.run(main())
