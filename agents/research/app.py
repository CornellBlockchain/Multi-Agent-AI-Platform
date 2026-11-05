"""Research Agent service: GET /health and POST /execute."""
from typing import Any, Optional

from fastapi import FastAPI
from pydantic import BaseModel, field_validator

from tools.brave import BraveSearchError, brave_search_with_events

app = FastAPI(title="Research Agent")


class AgentTask(BaseModel):
    """The assignment sent by the backend."""
    run_id: str
    task_id: str
    instruction: str
    context: Optional[Any] = None

    @field_validator("run_id", "task_id", "instruction")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "research"}


@app.post("/execute")
async def execute(task: AgentTask):
    events: list = []  # filled in by the event helper, kept even if the search fails
    result = {
        "run_id": task.run_id,
        "task_id": task.task_id,
        "agent": "research",
        "status": "completed",
        "summary": "",
        "sources": [],
        "artifacts": [],
        "events": events,
        "error": None,
    }

    try:
        # Until Gemini is added, the instruction is used directly as the search query.
        search = await brave_search_with_events(
            task.instruction, run_id=task.run_id, task_id=task.task_id, events=events,
        )
        result["summary"] = search["summary"]
        result["sources"] = search["sources"]
        result["artifacts"] = search["artifacts"]
    except (BraveSearchError, ValueError, RuntimeError) as exc:
        # These messages are written by us and never contain the API key.
        result["status"] = "failed"
        result["error"] = str(exc)
        result["summary"] = f"Research could not be completed: {exc}"
    except Exception:
        result["status"] = "failed"
        result["error"] = "Unexpected error while running the search"
        result["summary"] = "Research could not be completed."

    return result
