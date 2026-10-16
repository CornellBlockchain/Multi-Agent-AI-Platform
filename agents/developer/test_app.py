"""Contract checks for the developer agent service.

Covers the agreements Team C depends on: echoed identifiers, the
start-before-terminal event rule, and a structured failed result. The tool is
stubbed, so these need no network, no keys and no tools.py.
"""

from fastapi.testclient import TestClient

import app as service

client = TestClient(service.app)

TASK = {"run_id": "run-1", "task_id": "task-dev-1", "instruction": "duckdb python"}

TOOL_RESULT = {
    "message": "Found 2 repositories",
    "summary": "GitHub search for 'duckdb python' returned 2 repositories.",
    "sources": [{"title": "duckdb/duckdb", "url": "https://github.com/duckdb/duckdb"}],
    "artifacts": [{"name": "github_search_results.md", "content": "- duckdb/duckdb"}],
}


def stub_tool(monkeypatch, result=None, error=None):
    async def fake_github_search(query, limit=5):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(service, "github_search", fake_github_search)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "agent": "developer"}


def test_execute_echoes_identifiers_and_returns_findings(monkeypatch):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    body = client.post("/execute", json=TASK).json()

    assert body["run_id"] == TASK["run_id"]
    assert body["task_id"] == TASK["task_id"]
    assert body["agent"] == "developer"
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["sources"][0]["url"] == "https://github.com/duckdb/duckdb"
    assert body["artifacts"][0]["name"] == "github_search_results.md"


def test_every_started_call_gets_exactly_one_terminal_event(monkeypatch):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    events = client.post("/execute", json=TASK).json()["events"]

    assert events, "a completed run must report tool activity"
    assert len({e["event_id"] for e in events}) == len(events), "event_ids must be distinct"

    by_call: dict[str, list[str]] = {}
    for event in events:
        by_call.setdefault(event["tool_call_id"], []).append(event["type"])

    for types in by_call.values():
        assert types[0] == "tool.started", f"start event must come first, got {types}"
        terminal = [t for t in types if t in {"tool.completed", "tool.failed"}]
        assert len(terminal) == 1, f"expected one terminal event, got {types}"

    for event in events:
        assert event["run_id"] == TASK["run_id"]
        assert event["task_id"] == TASK["task_id"]
        assert event["agent"] == "developer"
        assert event["timestamp"].endswith("+00:00"), "timestamps must be UTC"


def test_tool_failure_returns_structured_failed_result(monkeypatch):
    stub_tool(monkeypatch, error=RuntimeError("provider unavailable"))
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "failed"
    assert body["error"]
    assert body["run_id"] == TASK["run_id"]
    assert [e["type"] for e in body["events"]] == ["tool.started", "tool.failed"]


def test_failure_leaks_no_detail_to_the_caller(monkeypatch):
    """Nothing from the exception text may reach Team C over the wire."""
    stub_tool(monkeypatch, error=RuntimeError("token abc123 rejected"))
    body = client.post("/execute", json=TASK).json()

    assert body["error"] == "RuntimeError"
    assert "abc123" not in body["error"]
    assert "abc123" not in body["summary"]
    assert not any("abc123" in event["message"] for event in body["events"])


def test_empty_instruction_fails_without_running_a_tool(monkeypatch):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    body = client.post("/execute", json={**TASK, "instruction": "   "}).json()

    assert body["status"] == "failed"
    assert body["error"] == "empty instruction"
    assert body["events"] == []


def test_malformed_task_is_rejected():
    assert client.post("/execute", json={"instruction": "no identifiers"}).status_code == 422
