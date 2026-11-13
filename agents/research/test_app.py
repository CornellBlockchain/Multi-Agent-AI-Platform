"""Tests for the Research Agent API. Brave responses are mocked: no network, no real key."""
import httpx
import pytest
from fastapi.testclient import TestClient

from app import app
from tools import brave

RealAsyncClient = httpx.AsyncClient
client = TestClient(app)

SAMPLE = {"web": {"results": [
    {"title": "One", "url": "https://one.example", "description": "first snippet"},
    {"title": "Two", "url": "https://two.example", "description": "second snippet"},
]}}
TASK = {"run_id": "run-42", "task_id": "task-7", "instruction": "what is blockchain"}
FIELDS = {"run_id", "task_id", "agent", "status", "summary", "sources", "artifacts", "events", "error"}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")


def mock_brave(monkeypatch, handler):
    def factory(*args, **kwargs):
        return RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(brave.httpx, "AsyncClient", factory)


def respond(monkeypatch, status=200, json=None):
    mock_brave(monkeypatch, lambda r: httpx.Response(status, json=json if json is not None else {}))


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_execute_success(monkeypatch):
    respond(monkeypatch, json=SAMPLE)
    response = client.post("/execute", json=TASK)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == FIELDS
    assert (body["run_id"], body["task_id"], body["agent"]) == ("run-42", "task-7", "research")
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["sources"] == [
        {"title": "One", "url": "https://one.example"},
        {"title": "Two", "url": "https://two.example"},
    ]
    assert "first snippet" in body["artifacts"][0]["content"]
    assert "what is blockchain" in body["summary"]


def test_execute_events(monkeypatch):
    respond(monkeypatch, json=SAMPLE)
    events = client.post("/execute", json=TASK).json()["events"]
    assert [e["type"] for e in events] == ["tool.started", "tool.completed"]
    assert events[0]["tool_call_id"] == events[1]["tool_call_id"]
    assert events[1]["result_count"] == 2
    assert all(e["run_id"] == "run-42" and e["task_id"] == "task-7" for e in events)


def test_query_reaches_brave(monkeypatch):
    seen = {}

    def handler(request):
        seen["q"] = request.url.params["q"]
        return httpx.Response(200, json=SAMPLE)

    mock_brave(monkeypatch, handler)
    client.post("/execute", json={**TASK, "instruction": "earthquake causes", "context": {"x": 1}})
    assert seen["q"] == "earthquake causes"


def test_empty_results_completed(monkeypatch):
    respond(monkeypatch, json={})
    body = client.post("/execute", json=TASK).json()
    assert body["status"] == "completed"
    assert body["sources"] == [] and body["artifacts"] == []
    assert "No results found" in body["summary"]


@pytest.mark.parametrize("status,text", [(401, "invalid"), (429, "rate limit"), (500, "server error")])
def test_provider_failure(monkeypatch, status, text):
    respond(monkeypatch, status=status)
    response = client.post("/execute", json=TASK)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert text in body["error"]
    assert body["sources"] == [] and body["artifacts"] == []
    assert [e["type"] for e in body["events"]] == ["tool.started", "tool.failed"]
    assert "test-key" not in response.text


def test_missing_key_is_failed_result(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY")
    body = client.post("/execute", json=TASK).json()
    assert body["status"] == "failed"
    assert "BRAVE_API_KEY" in body["error"]
    assert [e["type"] for e in body["events"]] == ["tool.started", "tool.failed"]


@pytest.mark.parametrize("payload", [
    {"task_id": "t", "instruction": "q"},
    {"run_id": "r", "instruction": "q"},
    {"run_id": "r", "task_id": "t"},
    {**TASK, "instruction": ""},
    {**TASK, "instruction": "   "},
    {**TASK, "run_id": ""},
    {**TASK, "task_id": 123},
])
def test_invalid_requests(payload):
    assert client.post("/execute", json=payload).status_code == 422
