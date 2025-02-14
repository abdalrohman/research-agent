from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from research_agent import SearchAgent

app = FastAPI(title="Research Agent", description="AI-powered research assistant")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")


class ResearchRequest(BaseModel):
    question: str
    depth: int = 2


class ResearchResult(BaseModel):
    report: str


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


@app.post("/research", response_model=ResearchResult)
async def start_research(request: ResearchRequest):
    agent = SearchAgent()
    report = await agent.execute(request.question, request.depth)
    return ResearchResult(report=report)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
