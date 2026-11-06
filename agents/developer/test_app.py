"""Contract checks for the developer agent service.

Covers the agreements Team C depends on: echoed identifiers, the
start-before-terminal event rule, and a structured failed result. Gemini and
the tool are both stubbed, so these need no network and no keys.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.genai import types

import app as service
import tools
from tools import ToolError

client = TestClient(service.app)
REAL_CALL_GEMINI = service.call_gemini


def text_reply(text):
    return SimpleNamespace(function_calls=None, text=text, candidates=[])


def tool_reply(name, args):
    call = types.FunctionCall(name=name, args=args)
    content = types.Content(role="model", parts=[types.Part(function_call=call)])
    return SimpleNamespace(
        function_calls=[call], text=None, candidates=[SimpleNamespace(content=content)]
    )


def stub_gemini(monkeypatch, replies):
    """Replace call_gemini with a script of replies; record what it was sent."""
    script = iter(replies)
    seen = []

    async def fake_call_gemini(contents, config=None):
        seen.append(list(contents))
        reply = next(script)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(service, "call_gemini", fake_call_gemini)
    return seen


@pytest.fixture(autouse=True)
def default_gemini(monkeypatch):
    """By default Gemini searches GitHub once, then summarises."""
    return stub_gemini(monkeypatch, [
        tool_reply("github_search", {"query": "duckdb language:python"}),
        text_reply("duckdb/duckdb is the main repository."),
    ])

TASK = {"run_id": "run-1", "task_id": "task-dev-1", "instruction": "duckdb python"}

TOOL_RESULT = {
    "message": "Found 2 repositories",
    "summary": "GitHub search for 'duckdb python' returned 2 repositories.",
    "sources": [{"title": "duckdb/duckdb", "url": "https://github.com/duckdb/duckdb"}],
    "artifacts": [{"name": "github_search_results.md", "content": "- duckdb/duckdb"}],
}


def stub_tool(monkeypatch, result=None, error=None):
    """Swap the registry entry, since run_tool resolves tools by name."""

    async def fake_github_search(query):
        if error is not None:
            raise error
        return result

    monkeypatch.setitem(
        tools.TOOLS, "github_search", {"fn": fake_github_search, "start": "Searching GitHub"}
    )


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


def test_unexpected_failure_keeps_its_detail_in_the_log(monkeypatch, capsys):
    """Nothing crosses the wire, but the detail must survive somewhere."""
    stub_tool(monkeypatch, error=RuntimeError("token ghp_SECRET123 rejected"))
    body = client.post("/execute", json=TASK).json()

    assert body["error"] == "RuntimeError"
    assert "ghp_SECRET123" in capsys.readouterr().out


def test_tool_error_message_reaches_the_caller(monkeypatch):
    """ToolError text is written by us and meant to be displayed, so it travels."""
    stub_tool(monkeypatch, error=ToolError("GITHUB_TOKEN not set!"))
    body = client.post("/execute", json=TASK).json()

    assert body["error"] == "GITHUB_TOKEN not set!"
    assert "GITHUB_TOKEN not set!" in body["events"][-1]["message"]


def test_empty_instruction_fails_without_running_a_tool(monkeypatch):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    body = client.post("/execute", json={**TASK, "instruction": "   "}).json()

    assert body["status"] == "failed"
    assert body["error"] == "empty instruction"
    assert body["events"] == []


def test_malformed_task_is_rejected():
    assert client.post("/execute", json={"instruction": "no identifiers"}).status_code == 422


# --- Gemini loop ---------------------------------------------------------------

def test_gemini_chooses_the_tool_input(monkeypatch):
    """The tool gets Gemini's query, not the raw instruction."""
    received = []

    async def fake_github_search(query):
        received.append(query)
        return TOOL_RESULT

    monkeypatch.setitem(
        tools.TOOLS, "github_search", {"fn": fake_github_search, "start": "Searching GitHub"}
    )
    body = client.post("/execute", json=TASK).json()

    assert received == ["duckdb language:python"]
    assert body["summary"] == "duckdb/duckdb is the main repository."


def test_tool_result_is_sent_back_to_gemini(monkeypatch, default_gemini):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    client.post("/execute", json=TASK)

    second_turn = default_gemini[1]
    response_part = second_turn[-1].parts[0].function_response
    assert response_part.name == "github_search"
    assert response_part.response["message"] == "Found 2 repositories"


def test_backend_context_object_is_accepted(monkeypatch):
    """backend/app/models.py sends context as an object, default {}."""
    stub_tool(monkeypatch, result=TOOL_RESULT)
    response = client.post("/execute", json={**TASK, "context": {"query": "original question"}})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_answer_without_tools_is_completed(monkeypatch):
    stub_gemini(monkeypatch, [text_reply("Nothing to search for.")])
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "completed"
    assert body["events"] == []


def test_gemini_failure_is_structured_and_hides_detail(monkeypatch, capsys):
    stub_gemini(monkeypatch, [RuntimeError("bad key AIzaSECRET")])
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "failed"
    assert body["error"] == "RuntimeError"
    assert "AIzaSECRET" not in body["summary"]
    assert "AIzaSECRET" in capsys.readouterr().out


def test_gemini_timeout_is_a_failed_result(monkeypatch):
    stub_gemini(monkeypatch, [asyncio.TimeoutError()])
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "failed"
    assert body["error"] == "TimeoutError"


def test_missing_gemini_key_is_reported(monkeypatch):
    monkeypatch.setattr(service, "call_gemini", REAL_CALL_GEMINI)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "failed"
    assert body["error"] == "GEMINI_API_KEY not set!"


def test_unknown_tool_from_gemini_does_not_crash(monkeypatch):
    stub_gemini(monkeypatch, [
        tool_reply("does_not_exist", {}),
        text_reply("I could not use that tool."),
    ])
    body = client.post("/execute", json=TASK).json()

    assert [e["type"] for e in body["events"]] == ["tool.started", "tool.failed"]
    assert body["status"] == "failed"


def test_last_turn_forces_an_answer(monkeypatch, default_gemini):
    """A model that keeps searching is made to answer; findings are kept."""
    stub_tool(monkeypatch, result=TOOL_RESULT)
    configs = []
    replies = iter([tool_reply("github_search", {"query": "x"})] * (service.MAX_TURNS - 1)
                   + [text_reply("Summary from what I found.")])

    async def fake_call_gemini(contents, config=None):
        configs.append(config)
        return next(replies)

    monkeypatch.setattr(service, "call_gemini", fake_call_gemini)
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "completed"
    assert body["summary"] == "Summary from what I found."
    assert configs[-1].tool_config.function_calling_config.mode == "NONE"
    assert configs[0].tool_config is None
    # Same repository from repeated searches is listed once.
    assert len(body["sources"]) == 1


def test_model_ignoring_the_final_turn_still_fails_cleanly(monkeypatch):
    stub_tool(monkeypatch, result=TOOL_RESULT)
    stub_gemini(monkeypatch, [tool_reply("github_search", {"query": "x"})] * service.MAX_TURNS)
    body = client.post("/execute", json=TASK).json()

    assert body["status"] == "failed"
    assert "No final answer" in body["error"]
    assert body["sources"], "partial findings are still returned to Team C"
