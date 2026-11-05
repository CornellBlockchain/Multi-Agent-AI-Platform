"""Tests for live activity events around brave_search. Brave responses are mocked."""
import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from tools import brave
from tools.brave import BraveSearchError, brave_search, brave_search_with_events

RealAsyncClient = httpx.AsyncClient
SAMPLE = {"web": {"results": [
    {"title": "One", "url": "https://one.example", "description": "snippet"},
]}}
REQUIRED = {"event_id", "run_id", "task_id", "agent", "tool_call_id",
            "tool", "type", "timestamp", "message"}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")


def mock_brave(monkeypatch, handler):
    def factory(*args, **kwargs):
        return RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(brave.httpx, "AsyncClient", factory)


def respond(monkeypatch, status=200, json=None):
    mock_brave(monkeypatch, lambda r: httpx.Response(status, json=json if json is not None else {}))


async def search(query="ai", events=None):
    events = [] if events is None else events
    result = await brave_search_with_events(query, run_id="run-1", task_id="task-1", events=events)
    return result, events


@pytest.mark.asyncio
async def test_success_started_then_completed(monkeypatch, capsys):
    respond(monkeypatch, json=SAMPLE)
    _, events = await search()
    assert [e["type"] for e in events] == ["tool.started", "tool.completed"]
    assert events[1]["result_count"] == 1
    assert events[1]["message"] == "Found 1 web results"
    for e in events:
        assert REQUIRED <= set(e)
        assert (e["run_id"], e["task_id"], e["agent"], e["tool"]) == ("run-1", "task-1", "research", "brave_search")
    # messages were printed immediately
    assert "Searching the web with Brave" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_zero_results_still_completed(monkeypatch):
    respond(monkeypatch, json={})
    _, events = await search()
    assert [e["type"] for e in events] == ["tool.started", "tool.completed"]
    assert events[1]["result_count"] == 0


@pytest.mark.asyncio
async def test_failure_started_then_failed(monkeypatch):
    respond(monkeypatch, status=429)
    events = []
    with pytest.raises(BraveSearchError):
        await search(events=events)
    assert [e["type"] for e in events] == ["tool.started", "tool.failed"]
    assert "result_count" not in events[1]
    assert events[1]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_cancelled_emits_failed(monkeypatch):
    class SlowClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, *a, **k): await asyncio.sleep(10)

    monkeypatch.setattr(brave.httpx, "AsyncClient", SlowClient)
    events = []
    task = asyncio.create_task(search(events=events))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [e["type"] for e in events] == ["tool.started", "tool.failed"]


@pytest.mark.asyncio
async def test_ids_timestamps_and_duration(monkeypatch):
    respond(monkeypatch, json=SAMPLE)
    events = []
    await search(events=events)
    await search(events=events)
    first, second = events[:2], events[2:]
    # start + end share a tool_call_id; each call has its own
    assert first[0]["tool_call_id"] == first[1]["tool_call_id"]
    assert second[0]["tool_call_id"] == second[1]["tool_call_id"]
    assert first[0]["tool_call_id"] != second[0]["tool_call_id"]
    # every event_id is unique
    assert len({e["event_id"] for e in events}) == 4
    # timestamps are UTC ISO 8601
    for e in events:
        parsed = datetime.fromisoformat(e["timestamp"])
        assert parsed.utcoffset() == timedelta(0)
    # duration on terminal events only
    assert "duration_ms" not in events[0]
    assert events[1]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_results_unchanged_by_wrapper(monkeypatch):
    respond(monkeypatch, json=SAMPLE)
    plain = await brave_search("ai")
    wrapped, _ = await search("ai")
    assert wrapped == plain
