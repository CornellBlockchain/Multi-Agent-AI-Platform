"""Team B developer agent service.

Implements the two routes both agents share
(shared/README.md#proposed-http-interfaces):

    GET  /health   report that the service can respond
    POST /execute  accept an agent task, return its final structured result

Division of labour inside Team B: tools.py owns tool execution -- its TOOLS
registry, its run_tool, and the tool-event lifecycle -- because Gemini function
calling hands back a tool name and an args dict, which is the shape its
run_tool already takes. This file owns the HTTP boundary: the contract models,
the assigned identifiers, and turning a tool outcome into an AgentResult.

Run it with:  uv run uvicorn app:app --reload --port 8002
"""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

AGENT = "developer"

from tools import run_tool


# --- Contract models (shared/README.md#task-and-result-fields) ---------------

class AgentTask(BaseModel):
    run_id: str
    task_id: str
    instruction: str
    context: str | None = None


class Source(BaseModel):
    title: str
    url: str | None = None


class Artifact(BaseModel):
    name: str
    content: str


class AgentResult(BaseModel):
    run_id: str
    task_id: str
    agent: str = AGENT
    status: str
    summary: str
    sources: list[Source] = []
    artifacts: list[Artifact] = []
    events: list[dict[str, Any]] = []
    error: str | None = None


# --- Routes ------------------------------------------------------------------

app = FastAPI(title="Developer Agent")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "agent": AGENT}


@app.post("/execute", response_model=AgentResult)
async def execute(task: AgentTask) -> AgentResult:
    """Run the assignment and echo the identifiers the backend assigned.

    A tool failure returns a structured `failed` result rather than an HTTP
    error, so Team C keeps the event log either way.
    """
    ctx: dict[str, Any] = {
        "run_id": task.run_id,
        "task_id": task.task_id,
        "events": [],
        "sources": [],
        "artifacts": [],
    }
    identifiers = {"run_id": task.run_id, "task_id": task.task_id}

    def failed(summary: str, error: str) -> AgentResult:
        return AgentResult(
            **identifiers, status="failed", summary=summary, error=error, events=ctx["events"]
        )

    if not task.instruction.strip():
        return failed("No instruction was supplied, so no tool ran.", "empty instruction")

    # ponytail: one tool, named directly. Gemini picks the tool by name in step 4
    # of agents/developer/README.md -- that loop feeds run_tool the same way once
    # the shared call_gemini helper lands.
    result = await run_tool("github_search", {"query": task.instruction}, ctx)

    # run_tool reports failures rather than raising, and has already decided what
    # is safe to show: ToolError text travels, anything else is its type alone.
    if "error" in result:
        return failed(
            f"GitHub search could not complete for {task.instruction!r}.", result["error"]
        )

    return AgentResult(
        **identifiers,
        status="completed",
        summary=result["summary"],
        sources=ctx["sources"],
        artifacts=ctx["artifacts"],
        events=ctx["events"],
    )
