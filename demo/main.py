import logging
import uuid

from fastapi import FastAPI
from pydantic import BaseModel
from langgraph.types import Command

from graph.builder import build_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI()
app_graph = build_graph()


class ChatRequest(BaseModel):
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    feedback: str | dict = "ok"


async def check_state(config: dict):
    state = await app_graph.aget_state(config)
    if state.next:
        interrupts = []
        for task in state.tasks or []:
            interrupts.extend(task.interrupts or [])
        interrupt_value = interrupts[0].value if interrupts else None
        return False, interrupt_value
    return True, None


@app.post("/chat")
async def chat(request: ChatRequest):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = await app_graph.ainvoke({"messages": [("user", request.message)]}, config=config)
    done, pending = await check_state(config)
    if not done:
        return {"status": "waiting_for_approval", "thread_id": thread_id, "plan": pending}
    return {
        "status": "complete",
        "thread_id": thread_id,
        "response": result["final_response"],
        "agent_results": result.get("agent_results"),
        "timings": result.get("timings"),
    }


@app.post("/resume")
async def resume(request: ResumeRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    result = await app_graph.ainvoke(Command(resume=request.feedback), config=config)
    done, pending = await check_state(config)
    if not done:
        return {"status": "waiting_for_approval", "thread_id": request.thread_id, "plan": pending}
    return {
        "status": "complete",
        "thread_id": request.thread_id,
        "response": result["final_response"],
        "agent_results": result.get("agent_results"),
        "timings": result.get("timings"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
