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
