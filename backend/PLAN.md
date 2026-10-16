# Team C Backend (FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI coordinator that turns one question into two agent assignments, calls the Research and Developer agents concurrently, collects their live tool events, synthesizes one answer with Gemini, and streams the run state to the dashboard.

**Architecture:** One FastAPI process with an in-memory run store. `POST /api/runs` creates a run and starts `run_workflow()` as a background asyncio task: plan (Gemini JSON) → both agents via `asyncio.gather` → synthesis (Gemini). Agents push tool events to `/internal/runs/{id}/events`; every state change wakes the SSE stream at `/api/runs/{id}/stream`.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, pydantic-settings, httpx, google-genai.

**Spec:** [backend/README.md](README.md) and [shared/README.md](../shared/README.md) (contract fields and routes). Decisions below override the spec where they differ.

## Global Constraints

- Scope: **FastAPI backend only.** The dashboard, Dockerfiles, docker-compose, Akash deployment, and the shared `call_gemini` helper belong to other people.
- No automated tests and no fake agent services. Each task ends with a manual `curl` check.
- Python 3.12; dependencies in `backend/requirements.txt`.
- Run storage: plain in-memory `dict`; **exactly one Uvicorn worker**; restarting clears history.
- Live updates: Server-Sent Events, not polling. `GET /api/runs/{id}` stays for one-off reads.
- Planner output: Gemini native JSON mode (`response_mime_type="application/json"`, `response_schema=Plan`), validated with Pydantic.
- Agent call: blocking `POST {agent_url}/execute` that returns the final `AgentResult`.
- Timeouts: `AGENT_TIMEOUT_S=120`, `GEMINI_TIMEOUT_S=30` (env).
- Event callback route has **no authentication**.
- Agent names are exactly `research` and `developer`.
- Overall status: `queued | running | completed | partial | failed`. Phase: `planning | agents | synthesis | done`. Agent status: `queued | running | completed | failed`.
- Timestamps are UTC ISO 8601 strings.
- Do not create `scripts/setup_env.py` and do not edit the root README.
- Branch: `team-c/orchestration`. One commit per task.

## Review Focus

Things no task "tests" automatically but that will bite in the demo. Each one has a manual check in the owning task.

1. **Whitespace-only question** (`"   "`) must return 422, not create a run. *(Task 2, check 3)*
2. **An agent is down or unreachable**: the run must still finish (`partial` or `failed`), never hang in `running`. *(Task 5, check 2)*
3. **The same event posted twice**: it appears once in `events`. *(Task 4, check 3)*
4. **An event for the wrong run/task**: rejected with 422, never attached to another run. *(Task 4, check 4)*
5. **SSE client connects after the run finished**: it gets one final snapshot and the stream closes. It must not hang. *(Task 6, check 2)*

---

## File Structure

```
backend/
  PLAN.md            # this file
  README.md          # existing guide; Task 7 appends "Run the backend"
  requirements.txt   # Task 1
  .env.example       # Task 1: setting names with empty/default values
  .gitignore         # Task 1
  app/
    __init__.py      # Task 1 (empty)
    config.py        # Task 1: Settings loaded from env/.env
    models.py        # Task 1: all Pydantic contract models
    store.py         # Task 2 (+Task 4): RunStore, event dedupe, change signal
    main.py          # Task 2 (+4, 5, 6): FastAPI app and routes
    gemini.py        # Task 3: TEMPORARY call_gemini until the shared helper lands
    planner.py       # Task 3: make_plan(query) -> Plan
    agents.py        # Task 4: call_agent(...) -> AgentResult (never raises)
    synthesis.py     # Task 5: synthesize(...) -> str
    workflow.py      # Task 5: run_workflow(run_id)
```

All commands below run from `backend/` with the virtualenv active.

---

### Task 1: Project setup, config, and contract models

**Files:**
- Create: `backend/requirements.txt`, `backend/.env.example`, `backend/.gitignore`
- Create: `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/models.py`

**Interfaces:**
- Produces: `settings` (instance of `Settings`) with fields `gemini_api_key`, `gemini_model`, `research_agent_url`, `developer_agent_url`, `callback_base_url`, `dashboard_origin`, `agent_timeout_s`, `gemini_timeout_s`.
- Produces: models `Source`, `Artifact`, `Event`, `AgentTask`, `AgentResult`, `AgentState`, `Plan`, `RunState`, `CreateRunRequest`, `CreateRunResponse`; type aliases `AgentName`, `RunStatus`; constant `FINAL_STATUSES`; function `utc_now() -> str`.

- [ ] **Step 1: Create the branch**

```bash
git checkout -b team-c/orchestration
```

- [ ] **Step 2: Write `backend/requirements.txt`**

```text
fastapi>=0.115
uvicorn[standard]>=0.30
pydantic>=2.8
pydantic-settings>=2.4
httpx>=0.27
google-genai>=1.0
```

- [ ] **Step 3: Write `backend/.gitignore`**

```text
.env
.venv/
__pycache__/
```

- [ ] **Step 4: Write `backend/.env.example`**

```text
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
RESEARCH_AGENT_URL=http://localhost:8001
DEVELOPER_AGENT_URL=http://localhost:8002
# Address the AGENTS use to reach this backend (in compose: http://backend:8000)
CALLBACK_BASE_URL=http://localhost:8000
DASHBOARD_ORIGIN=http://localhost:5173
AGENT_TIMEOUT_S=120
GEMINI_TIMEOUT_S=30
```

- [ ] **Step 5: Create the virtualenv and install**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then put your Gemini key into `.env`.

- [ ] **Step 6: Write `backend/app/__init__.py`** as an empty file.

- [ ] **Step 7: Write `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    research_agent_url: str = "http://localhost:8001"
    developer_agent_url: str = "http://localhost:8002"
    callback_base_url: str = "http://localhost:8000"
    dashboard_origin: str = "http://localhost:5173"
    agent_timeout_s: float = 120
    gemini_timeout_s: float = 30


settings = Settings()
```

- [ ] **Step 8: Write `backend/app/models.py`**

```python
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
```

- [ ] **Step 9: Manual check: imports and settings load**

Run:
```bash
python -c "from app.config import settings; from app.models import RunState; print(settings.research_agent_url)"
```
Expected: `http://localhost:8001` (or your `.env` value), no traceback.

- [ ] **Step 10: Commit**

```bash
git add requirements.txt .env.example .gitignore app/__init__.py app/config.py app/models.py
git commit -m "feat(backend): add settings and shared contract models"
```

---

### Task 2: Run store and run routes (Meeting 1 checkpoint)

**Files:**
- Create: `backend/app/store.py`
- Create: `backend/app/main.py`

**Interfaces:**
- Consumes: `RunState`, `AgentState`, `utc_now`, `CreateRunRequest`, `CreateRunResponse`, `settings` from Task 1.
- Produces: `store` (a `RunStore`) with `create(query: str) -> RunState`, `get(run_id: str) -> RunState | None`, `notify(run_id: str) -> None`, `changed(run_id: str) -> asyncio.Event`.
- Produces: `app` (FastAPI) and helper `_get_run_or_404(run_id: str) -> RunState` in `main.py`.

- [ ] **Step 1: Write `backend/app/store.py`**

```python
import asyncio
import uuid

from .models import AgentState, RunState, utc_now


class RunStore:
    """In-memory run history. Only valid with ONE Uvicorn worker."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._seen_events: dict[str, set[str]] = {}
        self._changed: dict[str, asyncio.Event] = {}

    def create(self, query: str) -> RunState:
        run_id = uuid.uuid4().hex
        run = RunState(
            run_id=run_id,
            query=query,
            started_at=utc_now(),
            agents={
                "research": AgentState(task_id=uuid.uuid4().hex),
                "developer": AgentState(task_id=uuid.uuid4().hex),
            },
        )
        self._runs[run_id] = run
        self._seen_events[run_id] = set()
        self._changed[run_id] = asyncio.Event()
        return run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def changed(self, run_id: str) -> asyncio.Event:
        """The Event that will be set on the next change to this run."""
        return self._changed[run_id]

    def notify(self, run_id: str) -> None:
        # Wake everyone waiting on the current Event, then swap in a fresh one
        # so later waiters block until the *next* change.
        self._changed[run_id].set()
        self._changed[run_id] = asyncio.Event()


store = RunStore()
```

- [ ] **Step 2: Write `backend/app/main.py`**

```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import CreateRunRequest, CreateRunResponse, RunState
from .store import store

app = FastAPI(title="Multi-Agent Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_run_or_404(run_id: str) -> RunState:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Unknown run: {run_id}")
    return run


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/runs", status_code=202, response_model=CreateRunResponse)
async def create_run(body: CreateRunRequest) -> CreateRunResponse:
    run = store.create(body.query)
    return CreateRunResponse(run_id=run.run_id)


@app.get("/api/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str) -> RunState:
    return _get_run_or_404(run_id)
```

- [ ] **Step 3: Start the server** (leave it running in its own terminal)

```bash
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 4: Manual checks**

1. Create a run:
   ```bash
   curl -s -X POST localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"query":"How do vector databases work?"}'
   ```
   Expected: HTTP 202, `{"run_id":"<32 hex chars>"}`.
2. Read it back, replacing `RUN_ID`:
   ```bash
   curl -s localhost:8000/api/runs/RUN_ID
   ```
   Expected: same `query`, `status:"queued"`, both `agents.research` and `agents.developer` with `status:"queued"` and **different** `task_id`s.
3. Empty and whitespace-only query:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"query":"   "}'
   ```
   Expected: `422`.
4. Unknown run:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/runs/nope
   ```
   Expected: `404`.
5. Health: `curl -s localhost:8000/api/health` → `{"status":"ok"}`.

- [ ] **Step 5: Commit**

```bash
git add app/store.py app/main.py
git commit -m "feat(backend): add in-memory run store and run routes"
```

---

### Task 3: Temporary Gemini helper and planner

**Files:**
- Create: `backend/app/gemini.py` (TEMPORARY: replace with the shared helper when other teams deliver it)
- Create: `backend/app/planner.py`

**Interfaces:**
- Consumes: `settings`, `Plan`.
- Produces: `async call_gemini(contents, config: types.GenerateContentConfig | None = None) -> types.GenerateContentResponse` (agreed shared signature; raises `TimeoutError` after `GEMINI_TIMEOUT_S`).
- Produces: `async make_plan(query: str) -> Plan` (raises on Gemini error, timeout, or invalid JSON).

- [ ] **Step 1: Write `backend/app/gemini.py`**

```python
"""TEMPORARY local call_gemini. Delete this file and import the shared helper
once the other teams publish it. Keep the same name and signature."""
import asyncio

from google import genai
from google.genai import types

from .config import settings

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def call_gemini(
    contents, config: types.GenerateContentConfig | None = None
) -> types.GenerateContentResponse:
    return await asyncio.wait_for(
        _get_client().aio.models.generate_content(
            model=settings.gemini_model, contents=contents, config=config
        ),
        timeout=settings.gemini_timeout_s,
    )
```

- [ ] **Step 2: Write `backend/app/planner.py`**

```python
from google.genai import types

from .gemini import call_gemini
from .models import Plan

PLANNER_INSTRUCTIONS = """You split a user's question into exactly two independent assignments.

- "research": for a research agent that can search the web, Wikipedia, academic papers,
  PDFs, course notes, and weather. Ask it for background, facts, and sources.
- "developer": for a developer agent that can search GitHub, browse web pages, run Python
  and C++, query DuckDB, and analyze repositories. Ask it for code, repositories, and
  executed results.

Each assignment must be specific and self-contained: the agent will NOT see the original
question or the other assignment. The two must be able to run at the same time.
Return JSON only."""


async def make_plan(query: str) -> Plan:
    response = await call_gemini(
        contents=f"User question: {query}",
        config=types.GenerateContentConfig(
            system_instruction=PLANNER_INSTRUCTIONS,
            response_mime_type="application/json",
            response_schema=Plan,
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty plan")
    return Plan.model_validate_json(response.text)
```

- [ ] **Step 3: Manual check: real planner call** (needs `GEMINI_API_KEY` in `.env`)

```bash
python -c "import asyncio; from app.planner import make_plan; print(asyncio.run(make_plan('Compare FAISS and pgvector for a student project')).model_dump_json(indent=2))"
```
Expected: JSON with non-empty `research` and `developer` strings that each make sense without the original question. Run again with a different question and confirm the assignments change.

- [ ] **Step 4: Commit**

```bash
git add app/gemini.py app/planner.py
git commit -m "feat(backend): add Gemini planner with JSON-schema output"
```

---

### Task 4: Agent client, event collection, and callback route

**Files:**
- Create: `backend/app/agents.py`
- Modify: `backend/app/store.py` (add `add_events`, `close_open_tool_calls`)
- Modify: `backend/app/main.py` (add `POST /internal/runs/{run_id}/events`)

**Interfaces:**
- Consumes: `store`, `AgentTask`, `AgentResult`, `Event`, `AgentName`, `settings`.
- Produces: `async call_agent(client: httpx.AsyncClient, agent: AgentName, task: AgentTask) -> AgentResult`. **Never raises**: every failure becomes `status="failed"` with `error` set.
- Produces: `store.add_events(run_id: str, events: list[Event]) -> int` (returns how many were new; silently skips duplicates and events whose `run_id`/`task_id` don't belong to the run).
- Produces: `store.close_open_tool_calls(run_id: str, agent: AgentName, message: str) -> None`.

- [ ] **Step 1: Add to `backend/app/store.py`**

Change the import line to:
```python
from .models import AgentName, AgentState, Event, RunState, utc_now
```

Add these methods to `RunStore` (below `notify`):
```python
    def add_events(self, run_id: str, events: list[Event]) -> int:
        run = self._runs[run_id]
        seen = self._seen_events[run_id]
        task_ids = {state.task_id for state in run.agents.values()}
        added = 0
        for event in events:
            if event.event_id in seen:
                continue
            if event.run_id != run_id or event.task_id not in task_ids:
                continue
            seen.add(event.event_id)
            run.events.append(event)
            added += 1
        if added:
            run.events.sort(key=lambda e: e.timestamp)
            self.notify(run_id)
        return added

    def close_open_tool_calls(self, run_id: str, agent: AgentName, message: str) -> None:
        """Give every started-but-unfinished tool call of this agent a tool.failed event."""
        run = self._runs[run_id]
        task_id = run.agents[agent].task_id
        mine = [e for e in run.events if e.task_id == task_id]
        finished = {e.tool_call_id for e in mine if e.type != "tool.started"}
        synthetic = [
            Event(
                event_id=uuid.uuid4().hex,
                run_id=run_id,
                task_id=task_id,
                agent=agent,
                tool_call_id=e.tool_call_id,
                tool=e.tool,
                type="tool.failed",
                timestamp=utc_now(),
                message=message,
            )
            for e in mine
            if e.type == "tool.started" and e.tool_call_id not in finished
        ]
        self.add_events(run_id, synthetic)
```

- [ ] **Step 2: Write `backend/app/agents.py`**

```python
import asyncio

import httpx
from pydantic import ValidationError

from .config import settings
from .models import AgentName, AgentResult, AgentTask


def _agent_url(agent: AgentName) -> str:
    return {
        "research": settings.research_agent_url,
        "developer": settings.developer_agent_url,
    }[agent]


def _failed(agent: AgentName, task: AgentTask, message: str) -> AgentResult:
    return AgentResult(
        run_id=task.run_id, task_id=task.task_id, agent=agent, status="failed", error=message
    )


async def call_agent(
    client: httpx.AsyncClient, agent: AgentName, task: AgentTask
) -> AgentResult:
    url = f"{_agent_url(agent)}/execute"
    try:
        response = await asyncio.wait_for(
            client.post(url, json=task.model_dump()), timeout=settings.agent_timeout_s
        )
        response.raise_for_status()
        result = AgentResult.model_validate(response.json())
    except TimeoutError:
        return _failed(agent, task, f"{agent} agent timed out after {settings.agent_timeout_s:.0f}s")
    except httpx.HTTPStatusError as exc:
        return _failed(agent, task, f"{agent} agent returned HTTP {exc.response.status_code}")
    except httpx.HTTPError as exc:
        return _failed(agent, task, f"Could not reach {agent} agent: {exc!r}")
    except (ValidationError, ValueError) as exc:
        return _failed(agent, task, f"{agent} agent returned an invalid result: {exc}")

    if result.run_id != task.run_id or result.task_id != task.task_id:
        return _failed(agent, task, f"{agent} agent returned mismatched run/task identifiers")
    return result
```

- [ ] **Step 3: Add the callback route to `backend/app/main.py`**

Change the models import to:
```python
from .models import CreateRunRequest, CreateRunResponse, Event, RunState
```

Add at the bottom:
```python
@app.post("/internal/runs/{run_id}/events")
async def receive_event(run_id: str, event: Event) -> dict:
    run = _get_run_or_404(run_id)
    if event.run_id != run_id or event.task_id != run.agents[event.agent].task_id:
        raise HTTPException(status_code=422, detail="Event run_id/task_id do not match this run")
    added = store.add_events(run_id, [event])
    return {"accepted": added == 1}
```

- [ ] **Step 4: Manual checks** (the server reloads by itself)

Create a run as in Task 2 and copy its `run_id` and `agents.research.task_id`. Then:

1. Write the event to a file, replacing `RUN_ID` and `TASK_ID`:
   ```bash
   cat > /tmp/ev.json <<'EOF'
   {"event_id":"e1","run_id":"RUN_ID","task_id":"TASK_ID","agent":"research","tool_call_id":"c1","tool":"wikipedia","type":"tool.started","timestamp":"2026-10-16T10:00:00+00:00","message":"Searching Wikipedia"}
   EOF
   ```
2. Post it:
   ```bash
   curl -s -X POST localhost:8000/internal/runs/RUN_ID/events -H 'Content-Type: application/json' -d @/tmp/ev.json
   ```
   Expected: `{"accepted":true}`, and `GET /api/runs/RUN_ID` shows one event.
3. Post the **same** file again. Expected: `{"accepted":false}`, and there is still exactly one event.
4. Edit `task_id` in the file to `wrong` and post. Expected: HTTP `422`.
5. Agent unreachable (no agents running):
   ```bash
   python -c "
   import asyncio, httpx
   from app.agents import call_agent
   from app.models import AgentTask
   async def main():
       async with httpx.AsyncClient(timeout=None) as c:
           r = await call_agent(c, 'research', AgentTask(run_id='r', task_id='t', instruction='x'))
           print(r.status, '|', r.error)
   asyncio.run(main())"
   ```
   Expected: `failed | Could not reach research agent: ConnectError(...)`.

- [ ] **Step 5: Commit**

```bash
git add app/agents.py app/store.py app/main.py
git commit -m "feat(backend): add agent client and deduplicated event collection"
```

---

### Task 5: Synthesis and the full workflow

**Files:**
- Create: `backend/app/synthesis.py`
- Create: `backend/app/workflow.py`
- Modify: `backend/app/main.py` (start the workflow from `POST /api/runs`)

**Interfaces:**
- Consumes: `call_gemini`, `make_plan`, `call_agent`, `store` (incl. `add_events`, `close_open_tool_calls`, `notify`), `settings`, models.
- Produces: `async synthesize(query: str, plan: Plan, results: dict[AgentName, AgentResult]) -> str` (raises on Gemini error/empty text).
- Produces: `async run_workflow(run_id: str) -> None`. **Never raises**, and always leaves the run in a final status with `phase="done"`.

- [ ] **Step 1: Write `backend/app/synthesis.py`**

```python
from google.genai import types

from .gemini import call_gemini
from .models import AgentName, AgentResult, Plan

MAX_ARTIFACT_CHARS = 2000

SYNTHESIS_INSTRUCTIONS = """You combine findings from a research agent and a developer agent into
one clear answer to the user's question.

- Use ONLY the findings provided. Do not invent facts, sources, code, or results.
- Cite sources inline as [S1], [S2], ... using the numbered source list.
- If an agent failed or found nothing, say what is missing and how that limits the answer.
- Use Markdown. Be concise."""


def _format_findings(results: dict[AgentName, AgentResult]) -> str:
    lines: list[str] = []
    n = 0
    for agent, result in results.items():
        lines.append(f"## {agent} agent: {result.status}")
        if result.error:
            lines.append(f"Error: {result.error}")
        if result.summary:
            lines.append(f"Summary:\n{result.summary}")
        for source in result.sources:
            n += 1
            lines.append(f"[S{n}] {source.title} - {source.url or 'local document'}")
        for artifact in result.artifacts:
            lines.append(f"Artifact '{artifact.name}':\n{artifact.content[:MAX_ARTIFACT_CHARS]}")
        lines.append("")
    return "\n".join(lines)


async def synthesize(
    query: str, plan: Plan, results: dict[AgentName, AgentResult]
) -> str:
    prompt = (
        f"User question: {query}\n\n"
        f"Research assignment: {plan.research}\n"
        f"Developer assignment: {plan.developer}\n\n"
        f"Findings:\n{_format_findings(results)}"
    )
    response = await call_gemini(
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=SYNTHESIS_INSTRUCTIONS),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty answer")
    return response.text
```

- [ ] **Step 2: Write `backend/app/workflow.py`**

```python
import asyncio

import httpx

from .agents import call_agent
from .config import settings
from .models import AgentName, AgentResult, AgentTask, RunState, RunStatus
from .planner import make_plan
from .store import store
from .synthesis import synthesize


def _finish(run: RunState, status: RunStatus, error: str | None = None) -> None:
    run.status = status
    run.phase = "done"
    run.error = error
    store.notify(run.run_id)


async def _run_agent(
    client: httpx.AsyncClient, run: RunState, agent: AgentName, instruction: str
) -> AgentResult:
    state = run.agents[agent]
    task = AgentTask(
        run_id=run.run_id,
        task_id=state.task_id,
        instruction=instruction,
        context={"callback_url": f"{settings.callback_base_url}/internal/runs/{run.run_id}/events"},
    )
    result = await call_agent(client, agent, task)
    store.add_events(run.run_id, result.events)  # fills gaps from missed callbacks
    store.close_open_tool_calls(
        run.run_id, agent, f"{agent} agent stopped before this tool finished"
    )
    state.status = result.status
    state.result = result
    store.notify(run.run_id)
    return result


async def _workflow(run: RunState) -> None:
    # 1. Planning
    run.status = "running"
    run.phase = "planning"
    store.notify(run.run_id)
    try:
        plan = await make_plan(run.query)
    except Exception as exc:
        _finish(run, "failed", f"Planning failed: {exc}")
        return
    run.plan = plan

    # 2. Both agents concurrently
    run.phase = "agents"
    for state in run.agents.values():
        state.status = "running"
    store.notify(run.run_id)
    async with httpx.AsyncClient(timeout=None) as client:
        research, developer = await asyncio.gather(
            _run_agent(client, run, "research", plan.research),
            _run_agent(client, run, "developer", plan.developer),
        )
    results: dict[AgentName, AgentResult] = {"research": research, "developer": developer}
    failed = [name for name, r in results.items() if r.status == "failed"]
    if len(failed) == 2:
        _finish(run, "failed", "Both agents failed; no findings to combine.")
        return

    # 3. Synthesis
    run.phase = "synthesis"
    store.notify(run.run_id)
    try:
        run.final_answer = await synthesize(run.query, plan, results)
    except Exception as exc:
        _finish(run, "failed", f"Agent findings are available, but the final answer could not be generated: {exc}")
        return

    if failed:
        _finish(run, "partial", f"The {failed[0]} agent failed; this answer uses only the other agent's findings.")
    else:
        _finish(run, "completed")


async def run_workflow(run_id: str) -> None:
    run = store.get(run_id)
    if run is None:
        return
    try:
        await _workflow(run)
    except Exception as exc:  # last-resort guard: a run must never stay "running"
        _finish(run, "failed", f"Unexpected backend error: {exc!r}")
```

- [ ] **Step 3: Start the workflow from `POST /api/runs` in `backend/app/main.py`**

Add imports at the top:
```python
import asyncio

from .workflow import run_workflow
```

Add below `app.add_middleware(...)`:
```python
# Keep references so background tasks are not garbage-collected mid-run.
_background_tasks: set[asyncio.Task] = set()
```

Replace `create_run` with:
```python
@app.post("/api/runs", status_code=202, response_model=CreateRunResponse)
async def create_run(body: CreateRunRequest) -> CreateRunResponse:
    run = store.create(body.query)
    task = asyncio.create_task(run_workflow(run.run_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return CreateRunResponse(run_id=run.run_id)
```

- [ ] **Step 4: Manual checks**

1. POST a run, then immediately GET it several times. Expected: the response to POST comes back right away (202); `status` moves `queued/running` → `phase:"planning"` → `phase:"agents"` with a filled `plan`.
2. **With no agents running** (the normal state in Meetings 1–2), wait a few seconds, then GET. Expected: both agents `status:"failed"` with "Could not reach … agent" errors, run `status:"failed"`, `phase:"done"`, error `"Both agents failed; no findings to combine."` The run must **not** be stuck in `running`.
3. Set `GEMINI_API_KEY=bad` in `.env`, restart, and POST. Expected: run `failed` with `error` starting `Planning failed:`. Restore the key afterwards.
4. Meeting 3 only (real agents up): POST the demo question. Expected: `completed`, `final_answer` with `[S1]`-style citations, events present for both agents. Stop one agent and repeat. Expected: `partial` with the explanation, and the other agent's findings kept.

- [ ] **Step 5: Commit**

```bash
git add app/synthesis.py app/workflow.py app/main.py
git commit -m "feat(backend): run planning, concurrent agents, and synthesis workflow"
```

---

### Task 6: Server-Sent Events stream

**Files:**
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `store.get`, `store.changed`, `FINAL_STATUSES`, `_get_run_or_404`.
- Produces: `GET /api/runs/{run_id}/stream` (`text/event-stream`). Each message is `data: <RunState JSON>\n\n`. A comment `: keepalive\n\n` is sent every 15 s with no change. The stream closes after it sends a snapshot whose status is final.

- [ ] **Step 1: Add the stream route to `backend/app/main.py`**

Extend the imports:
```python
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .models import FINAL_STATUSES, CreateRunRequest, CreateRunResponse, Event, RunState
```

Add the route:
```python
KEEPALIVE_S = 15


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    _get_run_or_404(run_id)

    async def snapshots():
        while True:
            # Grab the change signal BEFORE reading state so no update is missed.
            changed = store.changed(run_id)
            run = store.get(run_id)
            yield f"data: {run.model_dump_json()}\n\n"
            if run.status in FINAL_STATUSES:
                return
            while True:
                try:
                    await asyncio.wait_for(changed.wait(), timeout=KEEPALIVE_S)
                    break
                except TimeoutError:
                    if await request.is_disconnected():
                        return
                    yield ": keepalive\n\n"

    return StreamingResponse(
        snapshots(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: Manual checks**

1. Live run:
   ```bash
   RUN_ID=$(curl -s -X POST localhost:8000/api/runs -H 'Content-Type: application/json' -d '{"query":"What is RAG?"}' | python -c 'import sys,json;print(json.load(sys.stdin)["run_id"])')
   curl -N localhost:8000/api/runs/$RUN_ID/stream
   ```
   Expected: several `data: {...}` lines as `phase` moves planning → agents → done. The final one has a final `status`, then `curl` exits by itself.
2. Run `curl -N localhost:8000/api/runs/$RUN_ID/stream` again for the same, now finished run. Expected: exactly one `data:` line, then it exits immediately.
3. `curl -N localhost:8000/api/runs/nope/stream` → `{"detail":"Unknown run: nope"}` with 404.
4. Start a run, open the stream, and from another terminal post an event (Task 4 check 1) while the run is still in `agents`. Expected: a new `data:` line appears containing that event.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(backend): stream run snapshots over SSE"
```

---

### Task 7: Run instructions and Meeting 3 handoff

**Files:**
- Modify: `backend/README.md` (append a "Run the backend" section; the root README links to `backend/README.md#run-the-backend`)

**Interfaces:**
- Produces: the env-setting list and start command the deployment owner needs.

- [ ] **Step 1: Append to `backend/README.md`**

````markdown
## Run the backend

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Run exactly ONE worker.** Run history lives in memory; `--workers 2+` gives each worker
> its own history and runs will 404 at random. Restarting the backend clears all history.

| Setting | Purpose | Default |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Gemini key for planning and synthesis | (required) |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.5-flash` |
| `RESEARCH_AGENT_URL` | Research agent base URL | `http://localhost:8001` |
| `DEVELOPER_AGENT_URL` | Developer agent base URL | `http://localhost:8002` |
| `CALLBACK_BASE_URL` | Address agents use to post events back to this backend | `http://localhost:8000` |
| `DASHBOARD_ORIGIN` | Dashboard origin allowed by CORS | `http://localhost:5173` |
| `AGENT_TIMEOUT_S` | Max seconds per agent request | `120` |
| `GEMINI_TIMEOUT_S` | Max seconds per Gemini request | `30` |

Routes: `GET /api/health`, `POST /api/runs` (202 → `run_id`), `GET /api/runs/{id}`,
`GET /api/runs/{id}/stream` (SSE), `POST /internal/runs/{id}/events` (agents only; **no auth**).

Agents receive `context.callback_url` in each task and should POST events there.
````

- [ ] **Step 2: Meeting 3 integration checklist** (do these with Teams A and B and the deployment owner)

- [ ] Replace `app/gemini.py` with the shared `call_gemini` and re-run Task 3 check.
- [ ] Confirm both agents read `context.callback_url` and echo `run_id`/`task_id`.
- [ ] Give the deployment owner the settings table and start command above (one worker!).
- [ ] Run the demo question end to end (Task 5 check 4, success case) and watch the SSE stream.
- [ ] Stop one agent and confirm a `partial` run with the other's findings.
- [ ] Confirm `tool.started` events show up on the stream **before** the agent's final result.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(backend): add run instructions and settings"
```

---

## Milestone Map

| Meeting | Tasks | Checkpoint |
| :--- | :--- | :--- |
| **1** | 1–2 | Create and read a run with two queued agents; 422 / 404 errors |
| **2** | 3–6 | Planner works; a run with no agents ends `failed` cleanly; events dedupe; SSE streams |
| **3** | 7 + integration checklist | Real agents: `completed` and `partial` runs, live events on the stream |
| **4** | — | Present the architecture and run the demo |

## Known Limits (accepted)

- No auth on `/internal/runs/{id}/events`: anyone who can reach the backend can post events.
- No automated tests: the "both agents start before either finishes" and successful-run paths can't be checked until real agents exist in Meeting 3.
- History is lost on restart, and memory grows with every run (fine for a demo).
