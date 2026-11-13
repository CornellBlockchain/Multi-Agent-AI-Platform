import { describe, expect, it } from "vitest";
import { agentActivity, allSources, groupToolCalls, safeHref } from "./timeline";
import type { RunState, ToolEvent } from "../types";

const T0 = Date.parse("2026-10-16T20:00:00.000Z");
const iso = (ms: number) => new Date(T0 + ms).toISOString();

let n = 0;
function ev(partial: Partial<ToolEvent> & Pick<ToolEvent, "type" | "tool_call_id">, at: number): ToolEvent {
  n += 1;
  return {
    event_id: `e${n}`,
    run_id: "run-1",
    task_id: "task-r",
    agent: "research",
    tool: "wikipedia",
    timestamp: iso(at),
    message: partial.type,
    ...partial,
  };
}

function run(events: ToolEvent[], patch: Partial<RunState> = {}): RunState {
  return {
    run_id: "run-1",
    query: "q",
    started_at: iso(0),
    status: "running",
    phase: "agents",
    plan: { research: "r", developer: "d" },
    agents: {
      research: { task_id: "task-r", status: "running", result: null },
      developer: { task_id: "task-d", status: "running", result: null },
    },
    events,
    final_answer: null,
    error: null,
    ...patch,
  };
}

describe("groupToolCalls", () => {
  it("merges start and completion into one row with duration", () => {
    const rows = groupToolCalls(
      run([
        ev({ type: "tool.started", tool_call_id: "c1", message: "Searching Wikipedia" }, 0),
        ev({ type: "tool.completed", tool_call_id: "c1", message: "Found 3 pages", duration_ms: 1500 }, 1500),
      ]),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      status: "completed",
      startMessage: "Searching Wikipedia",
      endMessage: "Found 3 pages",
      durationMs: 1500,
    });
  });

  it("shows a running row before the terminal event arrives", () => {
    const rows = groupToolCalls(run([ev({ type: "tool.started", tool_call_id: "c1" }, 0)]));
    expect(rows[0]?.status).toBe("running");
  });

  it("keeps repeated calls to the same tool distinct", () => {
    const rows = groupToolCalls(
      run([
        ev({ type: "tool.started", tool_call_id: "c1" }, 0),
        ev({ type: "tool.started", tool_call_id: "c2" }, 100),
        ev({ type: "tool.failed", tool_call_id: "c2" }, 300),
        ev({ type: "tool.completed", tool_call_id: "c1" }, 900),
      ]),
    );
    expect(rows.map((r) => [r.toolCallId, r.status])).toEqual([
      ["c1", "completed"],
      ["c2", "failed"],
    ]);
  });

  it("does not let a late start event reopen a finished row", () => {
    const rows = groupToolCalls(
      run([
        ev({ type: "tool.completed", tool_call_id: "c1", message: "Done" }, 2000),
        ev({ type: "tool.started", tool_call_id: "c1", message: "Searching" }, 500),
      ]),
    );
    expect(rows[0]).toMatchObject({ status: "completed", startMessage: "Searching", durationMs: 1500 });
  });

  it("ignores repeated event IDs and events from other runs", () => {
    const start = ev({ type: "tool.started", tool_call_id: "c1" }, 0);
    const done = ev({ type: "tool.completed", tool_call_id: "c1" }, 400);
    const foreign = { ...ev({ type: "tool.started", tool_call_id: "x" }, 10), run_id: "other" };
    const rows = groupToolCalls(run([start, start, done, done, foreign]));
    expect(rows).toHaveLength(1);
  });

  it("separates identical tool_call_ids across tasks", () => {
    const rows = groupToolCalls(
      run([
        ev({ type: "tool.started", tool_call_id: "c1" }, 0),
        ev({ type: "tool.started", tool_call_id: "c1", task_id: "task-d", agent: "developer" }, 0),
      ]),
    );
    expect(rows).toHaveLength(2);
  });

  it("recovers events that only arrived with the agent result", () => {
    const start = ev({ type: "tool.started", tool_call_id: "c1", message: "Extracting PDF" }, 0);
    const done = ev({ type: "tool.completed", tool_call_id: "c1" }, 800);
    const rows = groupToolCalls(
      run([done], {
        agents: {
          research: {
            task_id: "task-r",
            status: "completed",
            result: {
              run_id: "run-1",
              task_id: "task-r",
              agent: "research",
              status: "completed",
              summary: "",
              sources: [],
              artifacts: [],
              events: [start, done],
            },
          },
        },
      }),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ status: "completed", startMessage: "Extracting PDF" });
  });

  it("ends running indicators once the agent or run has finished", () => {
    const events = [ev({ type: "tool.started", tool_call_id: "c1" }, 0)];
    const agentFailed = groupToolCalls(
      run(events, { agents: { research: { task_id: "task-r", status: "failed", result: null } } }),
    );
    expect(agentFailed[0]?.status).toBe("stopped");

    const runFailed = groupToolCalls(run(events, { status: "failed", phase: "done" }));
    expect(runFailed[0]?.status).toBe("stopped");
  });
});

describe("agentActivity", () => {
  it("reports the most recent running call as active", () => {
    const calls = groupToolCalls(
      run([
        ev({ type: "tool.started", tool_call_id: "c1", tool: "wikipedia" }, 0),
        ev({ type: "tool.started", tool_call_id: "c2", tool: "paper_search" }, 500),
        ev({ type: "tool.completed", tool_call_id: "c1" }, 700),
      ]),
    );
    const a = agentActivity(calls, "research");
    expect(a.active?.tool).toBe("paper_search");
    expect(a.completed).toBe(1);
    expect(a.firstAt).toBe(T0);
    expect(a.lastAt).toBe(T0 + 700);
  });
});

describe("sources", () => {
  it("only links http(s) URLs", () => {
    expect(safeHref("https://arxiv.org/abs/1603.09320")).toBe("https://arxiv.org/abs/1603.09320");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("/app/data/notes.pdf")).toBeNull();
    expect(safeHref(null)).toBeNull();
  });

  it("de-duplicates per agent and keeps local documents", () => {
    const base = { run_id: "run-1", summary: "", artifacts: [], events: [], status: "completed" as const };
    const r = run([], {
      agents: {
        research: {
          task_id: "task-r",
          status: "completed",
          result: {
            ...base,
            task_id: "task-r",
            agent: "research",
            sources: [
              { title: "A", url: "https://a.example" },
              { title: "A again", url: "https://a.example" },
              { title: "Notes", url: null },
            ],
          },
        },
      },
    });
    expect(allSources(r).map((s) => s.title)).toEqual(["A", "Notes"]);
  });
});
