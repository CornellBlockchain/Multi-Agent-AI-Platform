import { ApiError, type Backend } from "./client";
import { buildScript, type ScenarioId, type Script } from "./mockScenarios";
import type { RunState } from "../types";

interface MockRun {
  base: RunState;
  createdAt: number;
  script: Script;
}

const LATENCY_MS = [60, 160] as const;

function delay(signal?: AbortSignal): Promise<void> {
  const ms = LATENCY_MS[0] + Math.random() * (LATENCY_MS[1] - LATENCY_MS[0]);
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

/**
 * In-browser stand-in for the FastAPI backend. Snapshots are recomputed from
 * the scenario script on every poll, so timing behaves like a live run.
 */
export function createMockBackend(getScenario: () => ScenarioId): Backend & { isOffline(): boolean } {
  const runs = new Map<string, MockRun>();
  let counter = 0;

  const offlineRun = () => {
    const now = Date.now();
    for (const r of runs.values()) {
      const o = r.script.offline;
      if (o && now - r.createdAt >= o.from && now - r.createdAt < o.to) return true;
    }
    return false;
  };

  return {
    kind: "mock",
    isOffline: offlineRun,

    async health(signal) {
      await delay(signal);
      if (offlineRun()) throw new ApiError("network", "Couldn't reach the backend.");
    },

    async createRun(query, signal) {
      await delay(signal);
      if (!query.trim()) throw new ApiError("http", "Query must not be empty.", 422);
      counter += 1;
      const runId = `demo-${Date.now().toString(36)}-${counter}`;
      const createdAt = Date.now();
      const base: RunState = {
        run_id: runId,
        query: query.trim(),
        started_at: new Date(createdAt).toISOString(),
        status: "queued",
        phase: "planning",
        plan: null,
        agents: {
          research: { task_id: `${runId}-research`, status: "queued", result: null },
          developer: { task_id: `${runId}-developer`, status: "queued", result: null },
        },
        events: [],
        final_answer: null,
        error: null,
      };
      runs.set(runId, { base, createdAt, script: buildScript(getScenario(), runId, createdAt) });
      return { run_id: runId };
    },

    async getRun(runId, signal) {
      await delay(signal);
      const run = runs.get(runId);
      if (!run) throw new ApiError("http", "Run not found.", 404);
      const elapsed = Date.now() - run.createdAt;
      const o = run.script.offline;
      if (o && elapsed >= o.from && elapsed < o.to) throw new ApiError("network", "Couldn't reach the backend.");

      const snapshot: RunState = structuredClone(run.base);
      for (const step of [...run.script.steps].sort((a, b) => a.at - b.at)) {
        if (step.at <= elapsed) step.apply(snapshot);
      }
      // Detach from the script's shared objects, like a JSON response would be.
      return structuredClone(snapshot);
    },
  };
}
