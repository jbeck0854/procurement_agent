from langchain_core.messages import HumanMessage, SystemMessage

from graph.state import AgentState
from llm import get_llm

SYNTHESIZER_PROMPT = """You are the final synthesizer of a procurement supply-chain analysis system.
You receive the user's original question and raw results from sub-agents.
Your job: combine these results into a clear, helpful, and well-structured response for the user.
- Use the user's original question to understand what they care about.
- Present data in a readable format (use bullet points, numbered lists, or tables where appropriate).
- Highlight key insights, recommendations, and next steps.
- If the agent results contain warnings or missing data, mention them.
- Keep the response concise but complete.
- Respond in the same language the user used."""


async def synthesizer_node(state: AgentState) -> dict:
    llm = get_llm()
    agent_results = state["agent_results"]
    formatted = "\n\n".join(f"## {name}\n{value}" for name, value in agent_results.items())
    response = await llm.ainvoke([
        SystemMessage(content=SYNTHESIZER_PROMPT),
        *state["messages"],
        HumanMessage(content=f"Sub-agent results:\n\n{formatted}"),
    ])
    return {"final_response": response.content}
