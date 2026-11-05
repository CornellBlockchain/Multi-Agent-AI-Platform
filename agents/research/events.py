"""Reusable live-activity events for research tools (tool.started / tool.completed / tool.failed)."""
import asyncio
import time
import uuid
from datetime import datetime, timezone

AGENT = "research"


def make_event(run_id, task_id, tool_call_id, tool, event_type, message, **extra):
    """Build one event dictionary. `extra` adds fields such as duration_ms or result_count."""
    return {
        "event_id": str(uuid.uuid4()),
        "run_id": run_id,
        "task_id": task_id,
        "agent": AGENT,
        "tool_call_id": tool_call_id,
        "tool": tool,
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
        **extra,
    }


def emit(events, event):
    """Print the public message right away and save the event in the list."""
    print(event["message"], flush=True)
    events.append(event)


async def run_tool_with_events(
    tool, tool_func, args, *, run_id, task_id, events,
    start_message, done_message, fail_message,
):
    """Run `tool_func(*args)` and record started -> completed/failed events in `events`.

    `done_message` is a function that turns the tool result into a short message.
    Errors (and cancellation) are re-raised after the failure event is recorded.
    """
    tool_call_id = str(uuid.uuid4())  # new for every call, shared by start + end events

    def event(event_type, message, **extra):
        return make_event(run_id, task_id, tool_call_id, tool, event_type, message, **extra)

    emit(events, event("tool.started", start_message))
    started = time.monotonic()

    def elapsed_ms():
        return round((time.monotonic() - started) * 1000)

    try:
        result = await tool_func(*args)
    except BaseException:  # includes asyncio.CancelledError
        # Cancellation is a "failure" for the event log; Exception subclasses too.
        emit(events, event("tool.failed", fail_message, duration_ms=elapsed_ms()))
        raise
    emit(events, event(
        "tool.completed", done_message(result),
        duration_ms=elapsed_ms(), result_count=len(result["sources"]),
    ))
    return result
