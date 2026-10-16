"""Team B developer agent service.

Implements the two routes both agents share
(shared/README.md#proposed-http-interfaces):

    GET  /health   report that the service can respond
    POST /execute  accept an agent task, return its final structured result

Division of labour inside Team B: this file owns the HTTP contract, the
identifiers and the tool-event lifecycle. tools.py owns doing the work -- each
tool returns the four shared tool-result fields (message, summary, sources,
artifacts) and knows nothing about runs, tasks or events.

Run it with:  uv run uvicorn app:app --reload --port 8002
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

AGENT = "developer"

from tools import github_search


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


# --- Tool events (shared/README.md#tool-results-and-live-activity) -----------

class EventLog:
    """Collects the tool events for one agent task.

    ponytail: events are collected and printed, never POSTed. The guide defers
    callbacks to Meeting 3, and the result carries `events` regardless, so Team C
    can recover them without a callback channel existing yet.
    """

    def __init__(self, run_id: str, task_id: str) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self.events: list[dict[str, Any]] = []

    def emit(self, **fields: Any) -> dict[str, Any]:
        event = {
            "event_id": str(uuid.uuid4()),
            "run_id": self.run_id,
            "task_id": self.task_id,
            "agent": AGENT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self.events.append(event)
        print(f"[{event['type']}] {event['tool']}: {event['message']}", flush=True)
        return event


async def run_tool(
    log: EventLog,
    tool: str,
    started_message: str,
    fn: Callable[..., Awaitable[dict[str, Any]]],
    *args: Any,
) -> dict[str, Any]:
    """Announce `tool`, run it, then emit exactly one terminal event.

    One fresh tool_call_id per invocation, shared by the start and terminal
    event. Failures report before re-raising, so no started call is left open.
    """
    tool_call_id = str(uuid.uuid4())
    log.emit(type="tool.started", tool=tool, tool_call_id=tool_call_id, message=started_message)
    began = time.monotonic()

    try:
        result = await fn(*args)
    except Exception as exc:
        # Exception type only: the contract forbids provider keys in messages.
        log.emit(
            type="tool.failed",
            tool=tool,
            tool_call_id=tool_call_id,
            message=f"{tool} failed: {type(exc).__name__}",
            duration_ms=round((time.monotonic() - began) * 1000),
        )
        raise

    log.emit(
        type="tool.completed",
        tool=tool,
        tool_call_id=tool_call_id,
        message=result["message"],
        duration_ms=round((time.monotonic() - began) * 1000),
    )
    return result


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
    log = EventLog(task.run_id, task.task_id)
    identifiers = {"run_id": task.run_id, "task_id": task.task_id}

    def failed(summary: str, error: str) -> AgentResult:
        return AgentResult(
            **identifiers, status="failed", summary=summary, error=error, events=log.events
        )

    if not task.instruction.strip():
        return failed("No instruction was supplied, so no tool ran.", "empty instruction")

    if github_search is None:
        return failed("No developer tools are available yet.", "tools.py not implemented")

    # ponytail: one tool, called directly. Gemini-driven tool selection is step 4
    # of agents/developer/README.md and needs the shared call_gemini helper that
    # Team C has not built -- swap this call for the model loop once it lands.
    try:
        result = await run_tool(log, "github_search", "Searching GitHub", github_search, task.instruction)
    except Exception as exc:
        # The exception type only. Tool exceptions can carry provider responses,
        # and `error` crosses the wire to Team C; the contract forbids keys and
        # raw credentials in messages. Detail stays in this service's own log.
        print(f"[error] github_search: {type(exc).__name__}: {exc}", flush=True)
        return failed(
            f"GitHub search could not complete for {task.instruction!r}.",
            type(exc).__name__,
        )

    return AgentResult(
        **identifiers,
        status="completed",
        summary=result["summary"],
        sources=result["sources"],
        artifacts=result["artifacts"],
        events=log.events,
    )
