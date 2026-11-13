"""Manual file-based smoke test for Team A's existing Course Notes tool.

Put this file and course_notes_demo/ in agents/research/, then run:
    python check_course_notes_demo.py

Uses local, shareable fictional lecture notes, not private course materials.
Does not make network requests or require a Brave/Gemini key.
"""

import asyncio
import inspect
import os
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
NOTES = HERE / "course_notes_demo"

# Set this before importing the tool in case the tool reads config at import time.
os.environ["COURSE_NOTES_DIR"] = str(NOTES)

from tools.course_notes import course_notes_search, course_notes_search_with_events


async def resolve(value):
    """Support both synchronous and asynchronous tool implementations."""
    return await value if inspect.isawaitable(value) else value


CASES = [
    (
        "How does gradient descent use the learning rate to update weights?",
        "01_machine_learning.md",
        ("gradient descent", "learning rate"),
    ),
    (
        "How does TCP congestion control respond to packet loss?",
        "02_computer_networks.md",
        ("tcp", "congestion"),
    ),
    (
        "What do atomicity and durability mean for database transactions?",
        "03_databases.md",
        ("atomicity", "durability"),
    ),
]


async def main():
    assert NOTES.is_dir(), f"Notes directory not found: {NOTES}"
    print(f"Using shareable sample notes from: {NOTES}\n")

    for idx, (question, expected_doc, expected_terms) in enumerate(CASES, 1):
        result = await resolve(course_notes_search(question))
        assert set(result) == {"message", "summary", "sources", "artifacts"}, result.keys()
        assert result["sources"], f"No sources returned for: {question}"
        assert all(src["url"] is None for src in result["sources"]), "Local sources must use null URLs"
        assert any(expected_doc in src["title"] for src in result["sources"]), (
            f"Expected {expected_doc}; got {[s['title'] for s in result['sources']]}"
        )
        passages = "\n".join(a["content"] for a in result["artifacts"]).lower()
        assert any(term in passages for term in expected_terms), "Expected passage content not found"
        print(f"PASS {idx}: {question}")
        print(f"  {result['message']}")
        print(f"  Matching documents: {', '.join(s['title'] for s in result['sources'])}\n")

    empty_result = await resolve(course_notes_search("xylophone zephyr narwhal"))
    assert empty_result["sources"] == [] and empty_result["artifacts"] == []
    print("PASS 4: Unmatched query returns no sources or artifacts\n")

    events = []
    wrapped_result = await resolve(course_notes_search_with_events(
        "How does TCP congestion control handle packet loss?",
        run_id="demo-run-001",
        task_id="demo-task-001",
        events=events,
    ))
    assert wrapped_result["sources"]
    assert len(events) == 2, events
    assert [event["type"] for event in events] == ["tool.started", "tool.completed"]
    assert events[0]["tool_call_id"] == events[1]["tool_call_id"]
    assert events[0]["event_id"] != events[1]["event_id"]
    assert all(event["run_id"] == "demo-run-001" and
               event["task_id"] == "demo-task-001" for event in events)
    assert all(datetime.fromisoformat(event["timestamp"]).utcoffset().total_seconds() == 0
               for event in events)
    assert events[1]["duration_ms"] >= 0
    print("PASS 5: Event lifecycle and assigned IDs\n")

    failed_events = []
    try:
        await resolve(course_notes_search_with_events(
            "  ", run_id="demo-run-002", task_id="demo-task-002", events=failed_events
        ))
    except ValueError:
        assert [event["type"] for event in failed_events] == ["tool.started", "tool.failed"]
        assert failed_events[0]["tool_call_id"] == failed_events[1]["tool_call_id"]
        print("PASS 6: Invalid query produces a matching failure event\n")
    else:
        raise AssertionError("Expected ValueError for a blank query")

    print("All six demo checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
