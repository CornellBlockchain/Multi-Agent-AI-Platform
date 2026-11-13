from datetime import datetime, timezone
from uuid import uuid4
 
 
def create_tool_event(
    run_id: str,
    task_id: str,
    tool_call_id: str,
    event_type: str,
    message: str,
    tool: str = "wikipedia",
) -> dict:
    return {
        "event_id": str(uuid4()),
        "run_id": run_id,
        "task_id": task_id,
        "agent": "research",
        "tool_call_id": tool_call_id,
        "tool": tool,
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }
