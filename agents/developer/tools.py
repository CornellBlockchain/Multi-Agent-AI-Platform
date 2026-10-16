import os
import time
import uuid
from datetime import datetime, timezone

import httpx

from google.genai import types

class ToolError(Exception):
    """tool failure with displayed message"""

def emit(ctx, type, tool, tool_call_id, message, **extra):
    event = {
        "event_id": uuid.uuid4().hex,
        "run_id": ctx["run_id"],
        "task_id": ctx["task_id"],
        "agent": "developer",
        "tool_call_id": tool_call_id,
        "tool": tool,
        "type": type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": message,
        **extra,
    }
    ctx["events"].append(event)
    print(f"[{type}] {tool} {tool_call_id[:8]}: {message}", flush=True)
    return event

async def github_search(query: str) -> dict:
    """
    GitHub search function
    Can adjust results_per_page variable 
    """
    results_per_page : int = 5

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ToolError("GITHUB_TOKEN not set!")

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://api.github.com/search/repositories",
            params = {"q": query, "per_page": results_per_page},
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    if r.status_code != 200:
        raise ToolError(f"GitHub returned HTTP {r.status_code}")

    repos = r.json().get("items", [])
    if not repos:
        return {"message": "No repositories found", "summary": f"No GitHub repositories matched '{query}'.",
                "sources": [], "artifacts": []}

    lines = [
        f"- {x['full_name']} ({x.get('language') or 'n/a'}, {x['stargazers_count']} stars): {x.get('description') or 'no description'}"
        for x in repos
    ]
    return {
        "message": f"Found {len(repos)} repositories",
        "summary": "\n".join(lines),
        "sources": [{"title": x["full_name"], "url": x["html_url"]} for x in repos],
        "artifacts": [],
    }

TOOLS = {
    "github_search": {"fn": github_search, "start": "Searching GitHub"},
}

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="github_search",
        description="Search public GitHub repositories by keywords. Returns repo names, "
                    "descriptions, stars, languages and URLs.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "GitHub search query, e.g. 'vector database language:python'",
                },
            },
            "required": ["query"],
        },
    ),
]

async def run_tool(name, args, ctx):
    """Run one tool call: one started event, then exactly one completed/failed event."""
    tool = TOOLS.get(name)
    call_id = uuid.uuid4().hex
    emit(ctx, "tool.started", name, call_id, tool["start"] if tool else f"Running {name}")
    start = time.perf_counter()
    try:
        if tool is None:
            raise ToolError(f"Unknown tool '{name}'")
        result = await tool["fn"](**args)
    except Exception as e:
        ms = round((time.perf_counter() - start) * 1000)
        expected = isinstance(e, ToolError)
        msg = str(e) if expected else type(e).__name__
        if not expected:
            # Only the type travels, so keep the detail here or it is lost.
            print(f"[error] {name} {call_id[:8]}: {type(e).__name__}: {e}", flush=True)
        emit(ctx, "tool.failed", name, call_id, f"{name} failed: {msg}", duration_ms=ms)
        return {"error": msg}

    ms = round((time.perf_counter() - start) * 1000)
    emit(ctx, "tool.completed", name, call_id, result["message"],
         duration_ms=ms, result_count=len(result["sources"]))
    ctx["sources"].extend(result["sources"])
    ctx["artifacts"].extend(result["artifacts"])
    return result