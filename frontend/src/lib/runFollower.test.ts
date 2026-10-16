import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type Backend } from "../api/client";
import { RunFollower, type FollowerState } from "./runFollower";
import type { RunState } from "../types";

function snapshot(runId: string, status: RunState["status"], query = "q"): RunState {
  return {
    run_id: runId,
    query,
    started_at: new Date().toISOString(),
    status,
    phase: status === "running" ? "agents" : "done",
    plan: null,
    agents: {},
    events: [],
    final_answer: status === "completed" ? "answer" : null,
    error: null,
  };
}

/** A backend whose responses are controlled by the test. */
function fakeBackend() {
  const calls: string[] = [];
  const pending = new Map<string, { resolve: (r: RunState) => void; reject: (e: unknown) => void }[]>();
  let next = 0;
  const backend: Backend = {
    kind: "mock",
    health: async () => {},
    createRun: async (query) => {
      if (!query) throw new ApiError("http", "Query must not be empty.", 422);
      next += 1;
      return { run_id: `run-${next}` };
    },
    getRun: (runId, signal) =>
      new Promise<RunState>((resolve, reject) => {
        calls.push(runId);
        const list = pending.get(runId) ?? [];
        list.push({ resolve, reject });
        pending.set(runId, list);
        signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      }),
  };
  const respond = (runId: string, result: RunState | Error) => {
    const p = pending.get(runId)?.shift();
    if (!p) throw new Error(`no pending poll for ${runId}`);
    if (result instanceof Error) p.reject(result);
    else p.resolve(result);
  };
  return { backend, calls, respond };
}

const flush = () => vi.advanceTimersByTimeAsync(0);

describe("RunFollower", () => {
  let states: FollowerState[];
  beforeEach(() => {
    vi.useFakeTimers();
    states = [];
  });
  afterEach(() => vi.useRealTimers());

  it("rejects an empty question without calling the backend", async () => {
    const { backend, calls } = fakeBackend();
    const f = new RunFollower(backend, (s) => states.push(s));
    await f.start("   ");
    expect(f.getState().submitError).toMatch(/enter a question/i);
    expect(calls).toHaveLength(0);
  });

  it("polls about once per second and stops after a terminal snapshot", async () => {
    const { backend, calls, respond } = fakeBackend();
    const f = new RunFollower(backend, (s) => states.push(s));
    await f.start("What is HNSW?");
    await flush();
    expect(calls).toEqual(["run-1"]);

    respond("run-1", snapshot("run-1", "running"));
    await flush();
    expect(f.getState().following).toBe(true);
    await vi.advanceTimersByTimeAsync(999);
    expect(calls).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls).toHaveLength(2);

    respond("run-1", snapshot("run-1", "completed"));
    await flush();
    expect(f.getState().run?.final_answer).toBe("answer");
    expect(f.getState().following).toBe(false);
    expect(f.getState().finishedAt).not.toBeNull();
    await vi.advanceTimersByTimeAsync(5000);
    expect(calls).toHaveLength(2);
  });

  it("ignores a late response for a previous question", async () => {
    const { backend, respond } = fakeBackend();
    const f = new RunFollower(backend, (s) => states.push(s));
    await f.start("first");
    await flush();
    await f.start("second");
    await flush();

    // The old request was aborted; even if it resolved, it must not apply.
    expect(() => respond("run-1", snapshot("run-1", "running", "first"))).not.toThrow();
    respond("run-2", snapshot("run-2", "running", "second"));
    await flush();
    expect(f.getState().run?.run_id).toBe("run-2");
    expect(f.getState().query).toBe("second");
  });

  it("keeps the last state and retries with backoff when the connection drops", async () => {
    const { backend, calls, respond } = fakeBackend();
    const f = new RunFollower(backend, (s) => states.push(s), { pollMs: 1000, maxBackoffMs: 4000 });
    await f.start("q");
    await flush();
    respond("run-1", snapshot("run-1", "running"));
    await vi.advanceTimersByTimeAsync(1000);

    respond("run-1", new ApiError("network", "Couldn't reach the backend."));
    await flush();
    expect(f.getState().connection).toBe("offline");
    expect(f.getState().run?.status).toBe("running");
    expect(f.getState().following).toBe(true);

    await vi.advanceTimersByTimeAsync(1000);
    respond("run-1", new ApiError("network", "Couldn't reach the backend."));
    await vi.advanceTimersByTimeAsync(1999);
    expect(calls).toHaveLength(3);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls).toHaveLength(4);

    respond("run-1", snapshot("run-1", "partial"));
    await flush();
    expect(f.getState().connection).toBe("online");
    expect(f.getState().run?.status).toBe("partial");
    expect(f.getState().following).toBe(false);
  });

  it("stops with an explanation when the backend no longer knows the run", async () => {
    const { backend, respond } = fakeBackend();
    const f = new RunFollower(backend, (s) => states.push(s));
    await f.start("q");
    await flush();
    respond("run-1", new ApiError("http", "Run not found.", 404));
    await flush();
    expect(f.getState().following).toBe(false);
    expect(f.getState().followError).toMatch(/restarted/);
  });
});
