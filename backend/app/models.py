from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

AgentName = Literal["research", "developer"]
AgentStatus = Literal["queued", "running", "completed", "failed"]
RunStatus = Literal["queued", "running", "completed", "partial", "failed"]
Phase = Literal["planning", "agents", "synthesis", "done"]
EventType = Literal["tool.started", "tool.completed", "tool.failed"]

FINAL_STATUSES: set[str] = {"completed", "partial", "failed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Source(BaseModel):
    title: str
    url: str | None = None


class Artifact(BaseModel):
    name: str
    content: str


class Event(BaseModel):
    # Agents may add small extras such as result counts.
    model_config = ConfigDict(extra="allow")

    event_id: str
    run_id: str
    task_id: str
    agent: AgentName
    tool_call_id: str
    tool: str
    type: EventType
    timestamp: str
    message: str
    duration_ms: float | None = Field(default=None, ge=0)


class AgentTask(BaseModel):
    run_id: str
    task_id: str
    instruction: str
    context: dict = Field(default_factory=dict)


class AgentResult(BaseModel):
    run_id: str
    task_id: str
    agent: AgentName
    status: Literal["completed", "failed"]
    summary: str = ""
    sources: list[Source] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    error: str | None = None


class AgentState(BaseModel):
    task_id: str
    status: AgentStatus = "queued"
    result: AgentResult | None = None


class Plan(BaseModel):
    research: str
    developer: str


class RunState(BaseModel):
    run_id: str
    query: str
    started_at: str
    status: RunStatus = "queued"
    phase: Phase = "planning"
    plan: Plan | None = None
    agents: dict[AgentName, AgentState]
    events: list[Event] = Field(default_factory=list)
    final_answer: str | None = None
    error: str | None = None


class CreateRunRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateRunResponse(BaseModel):
    run_id: str
