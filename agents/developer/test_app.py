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


# --- playwright_browse --------------------------------------------------------
# The browser is faked, and public addresses are numeric so no DNS is needed.

PUBLIC_URL = "https://8.8.8.8/docs"


class FakePage:
    def __init__(self, text="Install with pip.", final_url=PUBLIC_URL, status=200, goto_error=None):
        self.text = text
        self.url = final_url
        self.status = status
        self.goto_error = goto_error

    def set_default_timeout(self, ms):
        pass

    async def route(self, pattern, handler):
        pass

    async def goto(self, url, wait_until):
        if self.goto_error is not None:
            raise self.goto_error
        return SimpleNamespace(status=self.status)

    async def wait_for_load_state(self, state, timeout):
        pass

    async def title(self):
        return "DuckDB docs"

    async def inner_text(self, selector):
        return self.text


def stub_browser(monkeypatch, page):
    """Replace async_playwright so nothing launches. Returns the fake browser."""

    class FakeBrowser:
        closed = False

        async def new_page(self, **kwargs):
            return page

        async def close(self):
            self.closed = True

    browser = FakeBrowser()

    async def launch(headless):
        return browser

    class FakePlaywright:
        chromium = SimpleNamespace(launch=launch)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(tools, "async_playwright", FakePlaywright)
    return browser


def browse(url=PUBLIC_URL):
    return asyncio.run(tools.playwright_browse(url))


def test_every_tool_is_declared_to_gemini():
    assert {d.name for d in tools.TOOL_DECLARATIONS} == set(tools.TOOLS)


def test_browse_returns_title_text_and_final_url(monkeypatch):
    browser = stub_browser(monkeypatch, FakePage(final_url="https://8.8.8.8/final"))
    result = browse()

    assert result["message"] == "Read DuckDB docs"
    assert result["sources"] == [{"title": "DuckDB docs", "url": "https://8.8.8.8/final"}]
    assert result["artifacts"][0]["content"] == "Install with pip."
    assert browser.closed


def test_browse_cuts_long_pages_and_says_so(monkeypatch):
    stub_browser(monkeypatch, FakePage(text="x" * (tools.MAX_PAGE_CHARS + 1)))
    result = browse()

    assert len(result["artifacts"][0]["content"]) == tools.MAX_PAGE_CHARS
    assert f"first {tools.MAX_PAGE_CHARS} characters" in result["summary"]


def test_browse_page_without_text_still_reports_the_source(monkeypatch):
    stub_browser(monkeypatch, FakePage(text="   "))
    result = browse()

    assert result["artifacts"] == []
    assert result["sources"][0]["url"] == PUBLIC_URL


@pytest.mark.parametrize("url", [
    "http://localhost:8000/internal",
    "http://127.0.0.1/",
    "http://10.0.0.5/",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "file:///etc/passwd",
    "ftp://8.8.8.8/",
    "not a url",
])
def test_browse_refuses_unsafe_addresses_before_opening_a_browser(monkeypatch, url):
    browser = stub_browser(monkeypatch, FakePage())

    with pytest.raises(ToolError):
        browse(url)
    assert not browser.closed, "the browser must never have been launched"


def test_browse_refuses_a_redirect_to_a_private_address(monkeypatch):
    stub_browser(monkeypatch, FakePage(final_url="http://127.0.0.1/admin", text="secret"))

    with pytest.raises(ToolError, match="private"):
        browse()


def test_browse_reports_http_errors(monkeypatch):
    stub_browser(monkeypatch, FakePage(status=404))

    with pytest.raises(ToolError, match="HTTP 404"):
        browse()


@pytest.mark.parametrize("error, message", [
    (tools.PlaywrightTimeoutError("slow"), "too long"),
    (tools.PlaywrightError("net::ERR_FAILED"), "could not be opened"),
])
def test_browse_failures_close_the_browser_with_a_clear_message(monkeypatch, error, message):
    browser = stub_browser(monkeypatch, FakePage(goto_error=error))

    with pytest.raises(ToolError, match=message):
        browse()
    assert browser.closed
