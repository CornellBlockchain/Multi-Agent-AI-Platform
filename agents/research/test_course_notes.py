"""Tests for course notes search. Uses synthetic notes in temp dirs; no network or keys."""
import os
import stat

import pytest

from tools.course_notes import (
    CourseNotesError, course_notes_search, course_notes_search_with_events, split_passages,
)

REQUIRED = {"event_id", "run_id", "task_id", "agent", "tool_call_id",
            "tool", "type", "timestamp", "message"}


@pytest.fixture
def notes(tmp_path):
    (tmp_path / "networking.md").write_text(
        "# TCP Basics\n\nTCP provides reliable ordered delivery using acknowledgements "
        "and retransmission.\n\n## UDP\n\nUDP is connectionless and has no delivery guarantee.\n",
        encoding="utf-8")
    sub = tmp_path / "week2"
    sub.mkdir()
    (sub / "photosynthesis.txt").write_text(
        "Photosynthesis converts light energy into chemical energy in chloroplasts.\n\n"
        "The Calvin cycle fixes carbon dioxide into sugar.\n", encoding="utf-8")
    (tmp_path / "ignored.pdf").write_text("tcp tcp tcp", encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    monkeypatch.delenv("COURSE_NOTES_DIR", raising=False)


@pytest.mark.asyncio
async def test_relevant_passages_for_different_queries(notes):
    tcp = await course_notes_search("how does TCP guarantee delivery?", notes)
    assert [s["title"] for s in tcp["sources"]] == ["networking.md"]
    assert "acknowledgements" in tcp["artifacts"][0]["content"]
    assert "Calvin" not in tcp["artifacts"][0]["content"]

    bio = await course_notes_search("Calvin cycle carbon", notes)
    assert [s["title"] for s in bio["sources"]] == ["week2/photosynthesis.txt"]
    assert "sugar" in bio["artifacts"][0]["content"]


@pytest.mark.asyncio
async def test_result_contract_and_null_urls(notes):
    result = await course_notes_search("udp connectionless", notes)
    assert set(result) == {"message", "summary", "sources", "artifacts"}
    assert result["message"] == "Found 1 matching passages"
    assert all(s["url"] is None for s in result["sources"])
    assert "UDP" in result["artifacts"][0]["content"]  # heading preserved


@pytest.mark.asyncio
async def test_best_match_ranked_first(notes):
    result = await course_notes_search("reliable delivery", notes)
    content = result["artifacts"][0]["content"]
    assert content.index("reliable ordered") < content.index("connectionless")


@pytest.mark.asyncio
async def test_no_match_is_successful_and_empty(notes):
    result = await course_notes_search("quantum chromodynamics", notes)
    assert result["sources"] == [] and result["artifacts"] == []
    assert result["message"] == "Found 0 matching passages"
    assert "No matching passages" in result["summary"]


@pytest.mark.asyncio
async def test_pdf_files_not_searched(notes):
    result = await course_notes_search("tcp", notes)
    assert all(not s["title"].endswith(".pdf") for s in result["sources"])


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   ", None, "the and of"])
async def test_empty_query_rejected(notes, query):
    with pytest.raises(ValueError):
        await course_notes_search(query, notes)


@pytest.mark.asyncio
async def test_missing_directory(tmp_path):
    with pytest.raises(CourseNotesError, match="not found"):
        await course_notes_search("tcp", tmp_path / "nope")


@pytest.mark.asyncio
async def test_unset_directory():
    with pytest.raises(CourseNotesError, match="COURSE_NOTES_DIR"):
        await course_notes_search("tcp")


@pytest.mark.asyncio
async def test_env_directory_used(notes, monkeypatch):
    monkeypatch.setenv("COURSE_NOTES_DIR", str(notes))
    result = await course_notes_search("calvin")
    assert result["sources"][0]["title"] == "week2/photosynthesis.txt"


@pytest.mark.asyncio
async def test_unreadable_files_skipped(notes):
    (notes / "binary.md").write_bytes(b"\xff\xfe\x00bad tcp")
    locked = notes / "locked.md"
    locked.write_text("tcp secret", encoding="utf-8")
    locked.chmod(0)
    try:
        result = await course_notes_search("tcp", notes)
    finally:
        locked.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert [s["title"] for s in result["sources"]] == ["networking.md"]
    assert "skipped" in result["summary"]
    if os.geteuid() != 0:
        assert "2 file(s)" in result["summary"]


@pytest.mark.asyncio
async def test_only_unreadable_files_reports_no_readable_notes(tmp_path):
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\xfa")
    result = await course_notes_search("anything", tmp_path)
    assert result["sources"] == []
    assert "No readable course notes" in result["summary"]


@pytest.mark.asyncio
async def test_symlink_outside_directory_not_read(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("confidential zebra password", encoding="utf-8")
    inside = tmp_path / "notes"
    inside.mkdir()
    (inside / "ok.md").write_text("zebra stripes are black and white", encoding="utf-8")
    (inside / "link.md").symlink_to(outside / "secret.md")
    result = await course_notes_search("zebra", inside)
    assert [s["title"] for s in result["sources"]] == ["ok.md"]
    assert "confidential" not in result["artifacts"][0]["content"]


def test_split_passages_tracks_headings():
    parts = split_passages("# A\n\none\n\n## B\n\ntwo\nlines\n")
    assert parts == [("A", "one"), ("B", "two\nlines")]


@pytest.mark.asyncio
async def test_events_success(notes, capsys):
    events = []
    result = await course_notes_search_with_events(
        "acknowledgements retransmission", run_id="run-1", task_id="task-1", events=events, notes_dir=notes)
    assert [e["type"] for e in events] == ["tool.started", "tool.completed"]
    assert events[0]["message"] == "Searching course notes"
    assert events[1]["message"] == "Found 1 matching passages"
    assert events[1]["result_count"] == len(result["sources"]) == 1
    assert events[0]["tool_call_id"] == events[1]["tool_call_id"]
    assert events[0]["event_id"] != events[1]["event_id"]
    assert events[0]["timestamp"] <= events[1]["timestamp"]
    for e in events:
        assert REQUIRED <= set(e)
        assert (e["run_id"], e["task_id"], e["agent"], e["tool"]) == (
            "run-1", "task-1", "research", "course_notes_search")
    assert "Searching course notes" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_events_failure(tmp_path):
    events = []
    with pytest.raises(CourseNotesError):
        await course_notes_search_with_events(
            "tcp", run_id="r", task_id="t", events=events, notes_dir=tmp_path / "missing")
    assert [e["type"] for e in events] == ["tool.started", "tool.failed"]
    assert events[1]["message"] == "Course notes search failed"
    assert events[0]["tool_call_id"] == events[1]["tool_call_id"]


@pytest.mark.asyncio
async def test_events_empty_query_fails_after_start(notes):
    events = []
    with pytest.raises(ValueError):
        await course_notes_search_with_events(
            " ", run_id="r", task_id="t", events=events, notes_dir=notes)
    assert [e["type"] for e in events] == ["tool.started", "tool.failed"]


@pytest.mark.asyncio
async def test_each_call_gets_new_tool_call_id(notes):
    events = []
    for _ in range(2):
        await course_notes_search_with_events(
            "tcp", run_id="r", task_id="t", events=events, notes_dir=notes)
    ids = {e["tool_call_id"] for e in events}
    assert len(ids) == 2


# ---- relevance cutoff regression tests ----
from tools.course_notes import MAX_RESULTS, MIN_RELATIVE_SCORE, select_relevant


def _ranked(*scores):
    return [{"document": f"d{i}.md", "text": str(i), "score": s} for i, s in enumerate(scores)]


def test_select_relevant_drops_weak_matches():
    kept = select_relevant(_ranked(10.0, 9.0, 2.4, 1.0))
    assert [p["score"] for p in kept] == [10.0, 9.0]


def test_select_relevant_boundary_is_inclusive():
    assert len(select_relevant(_ranked(10.0, 10.0 * MIN_RELATIVE_SCORE))) == 2


def test_select_relevant_keeps_many_but_caps():
    kept = select_relevant(_ranked(*([5.0] * (MAX_RESULTS + 3))))
    assert len(kept) == MAX_RESULTS


def test_select_relevant_empty_and_zero():
    assert select_relevant([]) == []
    assert select_relevant(_ranked(0.0, 0.0)) == []


@pytest.fixture
def mixed_notes(tmp_path):
    (tmp_path / "ml.md").write_text(
        "# Gradient Descent\n\nGradient descent updates weights using the learning rate.\n\n"
        "A large learning rate makes gradient descent overshoot the minimum.\n",
        encoding="utf-8")
    (tmp_path / "econ.md").write_text(
        "# Monetary Policy\n\nPooling of savings is shaped by the interest rate.\n", encoding="utf-8")
    (tmp_path / "net.md").write_text(
        "# TCP Congestion\n\nTCP congestion control reduces the window after packet loss.\n\n"
        "Slow start grows the congestion window exponentially.\n\n"
        "Routers drop a packet when queues fill.\n", encoding="utf-8")
    (tmp_path / "db.md").write_text(
        "# Transactions\n\nAtomicity means a transaction is all or nothing.\n\n"
        "Durability means committed data survives crashes.\n", encoding="utf-8")
    return tmp_path


async def _docs(query, d):
    r = await course_notes_search(query, notes_dir=d)
    return r, {s["title"] for s in r["sources"]}


@pytest.mark.asyncio
async def test_unrelated_weak_match_excluded(mixed_notes):
    r, docs = await _docs("gradient descent learning rate", mixed_notes)
    assert docs == {"ml.md"}
    assert "Pooling layers" not in r["artifacts"][0]["content"]


@pytest.mark.asyncio
async def test_multiple_relevant_passages_kept(mixed_notes):
    r, _ = await _docs("gradient descent learning rate", mixed_notes)
    content = r["artifacts"][0]["content"]
    assert "updates weights" in content and "overshoot" in content


@pytest.mark.asyncio
async def test_zero_matches_returns_nothing(mixed_notes):
    r, docs = await _docs("photosynthesis", mixed_notes)
    assert docs == set() and r["artifacts"] == [] and r["sources"] == []


@pytest.mark.asyncio
async def test_different_queries_return_different_docs(mixed_notes):
    _, tcp = await _docs("tcp congestion control packet loss", mixed_notes)
    _, acid = await _docs("atomicity and durability", mixed_notes)
    assert tcp == {"net.md"} and acid == {"db.md"}
