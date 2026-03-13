from fastapi import FastAPI
from pydantic import BaseModel

from graph.builder import build_graph

app = FastAPI()
app_graph = build_graph()


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(request: ChatRequest):
    result = await app_graph.ainvoke({"messages": [("user", request.message)]})
    return {"response": result["final_response"]}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
