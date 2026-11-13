"""Prompt checks: does the real model pick the right tools?

test_app.py stubs Gemini to prove the plumbing. These do the opposite: real
Gemini, real tools, no stubs, so they catch a prompt or tool-list change that
breaks the agent's judgement. They assert on structure the agent records about
itself (which tools started, which sources came back), never on the wording of
the summary, which changes every run.

Each test costs a few Gemini calls, so they never run by default:

    python -m pytest test_prompts.py -m prompt      needs GEMINI_API_KEY and GITHUB_TOKEN

Asserts are deliberately loose ("this tool was among those called", not "exactly
these calls in this order"): the model may search twice or read an extra file,
and a suite that fails on that gets ignored.
"""

import os
import re
import uuid

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

import app as service

load_dotenv()

pytestmark = [
    pytest.mark.prompt,
    pytest.mark.skipif(
        not (os.getenv("GEMINI_API_KEY") and os.getenv("GITHUB_TOKEN")),
        reason="GEMINI_API_KEY and GITHUB_TOKEN needed",
    ),
]

client = TestClient(service.app)


def ask(instruction):
    """Send one real assignment through /execute and return the result body."""
    task = {"run_id": uuid.uuid4().hex, "task_id": uuid.uuid4().hex, "instruction": instruction}
    return client.post("/execute", json=task).json()


def tools_called(body):
    return {e["tool"] for e in body["events"] if e["type"] == "tool.started"}


def explain(body):
    """What the agent did, shown when an assert fails."""
    return f"tools={sorted(tools_called(body))} status={body['status']} error={body['error']}\n{body['summary']}"


def test_discovery_question_searches_github():
    body = ask("Find popular Python libraries for vector search")

    assert body["status"] == "completed", explain(body)
    assert "github_search" in tools_called(body), explain(body)
    assert body["sources"], explain(body)


def files_read(body):
    """Paths of the files the agent opened with read_repo_file (.../blob/<ref>/<path>)."""
    return {s["url"].split("/blob/", 1)[1].split("/", 1)[1]
            for s in body["sources"] if "/blob/" in (s["url"] or "")}


def test_how_does_it_work_reads_the_code():
    # The prompt says: a named repository is inspected directly, and a "how does
    # it work" question means reading files, not answering from memory.
    body = ask("How does FastAPI's Depends work? Show me the code.")

    assert body["status"] == "completed", explain(body)
    assert {"repo_overview", "read_repo_file"} <= tools_called(body), explain(body)
    # The real repo (tiangolo/fastapi is its old name), not a tutorial named like it.
    file_urls = [s["url"] for s in body["sources"] if "/blob/" in (s["url"] or "")]
    assert any(f"github.com/{repo}/blob/" in url for url in file_urls
               for repo in ("fastapi/fastapi", "tiangolo/fastapi")), explain(body)
    # Every FastAPI file the summary names must be one it read. Seen in a file
    # list is not read: describing those is answering from memory.
    cited = set(re.findall(r"\bfastapi/[\w/]+\.py\b", body["summary"]))
    unread = cited - files_read(body)
    assert not unread, f"cited but never read: {sorted(unread)}\n" + explain(body)


def test_given_url_is_opened_in_the_browser():
    body = ask("Summarize the docs page https://duckdb.org/docs/")

    assert body["status"] == "completed", explain(body)
    assert "playwright_browse" in tools_called(body), explain(body)
    assert any("duckdb.org" in (s["url"] or "") for s in body["sources"]), explain(body)


def test_nothing_to_look_up_uses_no_tools():
    # The trap: a model that calls tools on everything is slow and costs money,
    # and this is the only real-model check of the no-tools path.
    body = ask("What's 2 + 2?")

    assert body["status"] == "completed", explain(body)
    assert tools_called(body) == set(), explain(body)
    assert body["summary"].strip(), explain(body)
