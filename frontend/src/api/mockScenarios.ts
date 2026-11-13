/**
 * Scripted demo runs for developing the dashboard without the backend.
 *
 * Each scenario is a list of timed steps applied to a run snapshot, so the
 * dashboard sees the same shapes, ordering quirks, and failures it will see
 * from the real backend. All content here is canned demo data.
 */
import type { AgentName, AgentResult, Artifact, RunState, Source, ToolEvent } from "../types";

export type ScenarioId = "completed" | "partial" | "failed" | "planning-failed" | "disconnect";

export const SCENARIOS: { id: ScenarioId; label: string; hint: string }[] = [
  { id: "completed", label: "Completed", hint: "Both agents succeed and the answer is synthesized." },
  { id: "partial", label: "Partial", hint: "The developer agent fails; research findings are kept." },
  { id: "failed", label: "Failed", hint: "Both agents fail, so no answer is generated." },
  { id: "planning-failed", label: "Planning fails", hint: "Gemini planning fails before any agent starts." },
  { id: "disconnect", label: "Connection drops", hint: "Polling fails for a few seconds mid-run, then recovers." },
];

export const EXAMPLE_QUESTION =
  "How do approximate nearest-neighbor search algorithms work, and which open-source libraries implement them well?";

export interface Step {
  at: number;
  apply: (run: RunState) => void;
}

export interface Script {
  steps: Step[];
  /** Polls in [from, to) ms after start fail as if the network dropped. */
  offline?: { from: number; to: number };
}

// ---------------------------------------------------------------------------
// Canned content
// ---------------------------------------------------------------------------

const PLAN = {
  research:
    "Explain how approximate nearest-neighbor (ANN) search works: the main index families (graph-based such as HNSW, quantization such as IVF-PQ, tree and hashing methods), the recall/latency trade-off, and the papers that introduced them. Cite encyclopedic background, primary papers, and the course notes.",
  developer:
    "Find the most widely used open-source ANN libraries on GitHub, inspect how one graph-based library builds and queries its index, and run a small Python benchmark that measures recall@10 against exact search. Report repository links, the inspected file paths, and the measured results.",
};

const RESEARCH_SOURCES: Source[] = [
  { title: "Nearest neighbor search — Wikipedia", url: "https://en.wikipedia.org/wiki/Nearest_neighbor_search" },
  { title: "Hierarchical navigable small world — Wikipedia", url: "https://en.wikipedia.org/wiki/Hierarchical_navigable_small_world" },
  {
    title: "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs (Malkov & Yashunin)",
    url: "https://arxiv.org/abs/1603.09320",
  },
  { title: "Billion-scale similarity search with GPUs (Johnson, Douze & Jégou)", url: "https://arxiv.org/abs/1702.08734" },
  { title: "Course notes — Lecture 14: Vector indexes (local document)", url: null },
];

const DEVELOPER_SOURCES: Source[] = [
  { title: "facebookresearch/faiss", url: "https://github.com/facebookresearch/faiss" },
  { title: "nmslib/hnswlib", url: "https://github.com/nmslib/hnswlib" },
  { title: "spotify/annoy", url: "https://github.com/spotify/annoy" },
  { title: "hnswlib/hnswalg.h", url: "https://github.com/nmslib/hnswlib/blob/master/hnswlib/hnswalg.h" },
];

const RESEARCH_ARTIFACTS: Artifact[] = [
  {
    name: "HNSW paper — extracted passages",
    content: [
      "p. 1 — Abstract",
      "  The approach is based on a multi-layer structure of proximity graphs; the upper",
      "  layers are sparse and act as an express lane for coarse routing.",
      "",
      "p. 4 — Search algorithm",
      "  Greedy search starts from the top layer and descends, using the closest element",
      "  found at one layer as the entry point for the next.",
      "",
      "p. 5 — Construction parameters",
      "  M controls the number of bi-directional links per element; efConstruction controls",
      "  the size of the dynamic candidate list during insertion.",
      "",
      "p. 9 — Evaluation",
      "  Recall is tuned at query time through ef: larger values trade latency for recall.",
    ].join("\n"),
  },
  {
    name: "Course notes — matching passage",
    content:
      "Lecture 14, §3: Exact k-NN is linear in the dataset size. ANN indexes give up a guarantee of exactness in exchange for sub-linear query time; quality is reported as recall@k against exact search.",
  },
];

const DEVELOPER_ARTIFACTS: Artifact[] = [
  {
    name: "recall_benchmark.py",
    content: `import time
import numpy as np
import hnswlib

rng = np.random.default_rng(42)
data = rng.standard_normal((20_000, 64)).astype("float32")
queries = rng.standard_normal((200, 64)).astype("float32")

# Exact ground truth (brute force)
d2 = ((queries[:, None, :] - data[None, :, :]) ** 2).sum(-1)
truth = np.argsort(d2, axis=1)[:, :10]

index = hnswlib.Index(space="l2", dim=64)
index.init_index(max_elements=len(data), M=16, ef_construction=200)
index.add_items(data)

for ef in (16, 64, 256):
    index.set_ef(ef)
    t0 = time.perf_counter()
    labels, _ = index.knn_query(queries, k=10)
    ms = (time.perf_counter() - t0) * 1000 / len(queries)
    recall = np.mean([len(set(l) & set(t)) / 10 for l, t in zip(labels, truth)])
    print(f"ef={ef:<4} recall@10={recall:.3f}  {ms:.3f} ms/query")`,
  },
  {
    name: "Benchmark output (stdout)",
    content: ["ef=16   recall@10=0.712  0.041 ms/query", "ef=64   recall@10=0.931  0.118 ms/query", "ef=256  recall@10=0.994  0.392 ms/query", "", "exit status 0"].join("\n"),
  },
  {
    name: "DuckDB — recall by setting",
    content: [
      "ef   | recall_at_10 | ms_per_query",
      "-----+--------------+-------------",
      "16   | 0.712        | 0.041",
      "64   | 0.931        | 0.118",
      "256  | 0.994        | 0.392",
    ].join("\n"),
  },
];

const FINAL_ANSWER = `Approximate nearest-neighbor (ANN) search gives up the guarantee of an exact answer in exchange for sub-linear query time, and reports quality as **recall@k** against exact search ([Nearest neighbor search](https://en.wikipedia.org/wiki/Nearest_neighbor_search); course notes, Lecture 14).

## How the main approaches work

- **Graph-based indexes (HNSW).** Points are linked into layered proximity graphs. A query starts on the sparse top layer and greedily descends, using the best point found at each layer as the entry to the next. \`M\` sets links per node; \`ef\` sets how many candidates are explored, trading latency for recall ([Malkov & Yashunin](https://arxiv.org/abs/1603.09320)).
- **Quantization and inverted files (IVF-PQ).** Vectors are clustered and compressed into short codes, so only a few clusters are scanned and distances are estimated from the codes. This is the approach FAISS scales to billions of vectors on GPUs ([Johnson et al.](https://arxiv.org/abs/1702.08734)).
- **Trees and hashing.** Random-projection trees (Annoy) and locality-sensitive hashing partition the space; they are simple and memory-light but usually need more probes for the same recall.

## Libraries worth using

| Library | Approach | Good fit |
| --- | --- | --- |
| [FAISS](https://github.com/facebookresearch/faiss) | IVF, PQ, HNSW, GPU | Large collections, compression |
| [hnswlib](https://github.com/nmslib/hnswlib) | HNSW | Fast in-memory search, simple API |
| [Annoy](https://github.com/spotify/annoy) | Random-projection trees | Read-only, memory-mapped indexes |

The developer agent inspected \`hnswlib/hnswalg.h\` and ran a 20,000-vector benchmark: recall@10 rose from 0.712 at \`ef=16\` to 0.994 at \`ef=256\`, while query time grew from 0.041 to 0.392 ms. That matches the paper's description of \`ef\` as the recall/latency dial.`;

const PARTIAL_ANSWER = `**Partial answer.** The developer agent did not finish, so this answer covers the research findings only; no benchmark was run.

Approximate nearest-neighbor (ANN) search gives up exactness for sub-linear query time and is measured by **recall@k** against exact search ([Nearest neighbor search](https://en.wikipedia.org/wiki/Nearest_neighbor_search)).

- **Graph-based (HNSW):** layered proximity graphs searched greedily from a sparse top layer; \`ef\` trades latency for recall ([Malkov & Yashunin](https://arxiv.org/abs/1603.09320)).
- **Quantization (IVF-PQ):** clusters plus compressed codes, scanned selectively; the basis of FAISS at billion scale ([Johnson et al.](https://arxiv.org/abs/1702.08734)).
- **Trees and hashing:** simpler partitioning schemes that typically need more probes for the same recall.

The developer agent found [FAISS](https://github.com/facebookresearch/faiss), [hnswlib](https://github.com/nmslib/hnswlib), and [Annoy](https://github.com/spotify/annoy) before it stopped, but it did not complete a code inspection or measurement, so no performance comparison is given.`;

// ---------------------------------------------------------------------------
// Script builder
// ---------------------------------------------------------------------------

class ScriptBuilder {
  steps: Step[] = [];
  private eventN = 0;
  private callN = 0;
  /** Events recorded per agent so they can be echoed in the agent result. */
  private agentEvents: Record<AgentName, ToolEvent[]> = { research: [], developer: [] };

  constructor(
    private runId: string,
    private startedAt: number,
  ) {}

  at(ms: number, apply: (run: RunState) => void) {
    this.steps.push({ at: ms, apply });
    return this;
  }

  private event(agent: AgentName, callId: string, tool: string, type: ToolEvent["type"], at: number, message: string, durationMs?: number): ToolEvent {
    this.eventN += 1;
    const e: ToolEvent = {
      event_id: `${this.runId}-evt-${this.eventN}`,
      run_id: this.runId,
      task_id: `${this.runId}-${agent}`,
      agent,
      tool_call_id: callId,
      tool,
      type,
      timestamp: new Date(this.startedAt + at).toISOString(),
      message,
    };
    if (durationMs !== undefined) e.duration_ms = durationMs;
    this.agentEvents[agent].push(e);
    return e;
  }

  /**
   * One tool invocation. `end` omitted = the call never reports an outcome.
   * `callbackMissed` = the start event never reaches the live log and is only
   * recovered from the agent's final result. `terminalFirst` = the terminal
   * event is appended to the log before the start event.
   */
  tool(
    agent: AgentName,
    tool: string,
    start: number,
    startMsg: string,
    end?: { at: number; ok: boolean; message: string },
    quirks: { callbackMissed?: boolean; terminalFirst?: boolean } = {},
  ) {
    this.callN += 1;
    const callId = `${agent}-call-${this.callN}`;
    const started = this.event(agent, callId, tool, "tool.started", start, startMsg);
    const finished = end
      ? this.event(agent, callId, tool, end.ok ? "tool.completed" : "tool.failed", end.at, end.message, end.at - start)
      : null;

    if (quirks.terminalFirst && finished) {
      this.at(end!.at, (r) => r.events.push(finished));
      this.at(end!.at + 400, (r) => r.events.push(started));
      return this;
    }
    if (!quirks.callbackMissed) this.at(start, (r) => r.events.push(started));
    if (finished) this.at(end!.at, (r) => r.events.push(finished));
    return this;
  }

  plan(at: number) {
    return this.at(at, (r) => {
      r.plan = { ...PLAN };
      r.phase = "agents";
      r.status = "running";
      for (const a of ["research", "developer"] as const) r.agents[a] = { task_id: `${this.runId}-${a}`, status: "running", result: null };
    });
  }

  finishAgent(agent: AgentName, at: number, result: Omit<AgentResult, "run_id" | "task_id" | "agent" | "events">) {
    // Echo every event this agent produced, like a real agent result would.
    const events = () => [...this.agentEvents[agent]];
    return this.at(at, (r) => {
      r.agents[agent] = {
        task_id: `${this.runId}-${agent}`,
        status: result.status,
        result: { run_id: this.runId, task_id: `${this.runId}-${agent}`, agent, events: events(), ...result },
      };
    });
  }

  phase(at: number, phase: RunState["phase"]) {
    return this.at(at, (r) => {
      r.phase = phase;
    });
  }

  end(at: number, patch: Partial<RunState>) {
    return this.at(at, (r) => {
      Object.assign(r, { phase: "done" }, patch);
    });
  }
}

const P = 1800; // planning time before agents start

function researchHappyPath(b: ScriptBuilder) {
  b.tool("research", "wikipedia", P + 300, "Searching Wikipedia for nearest neighbor search", { at: P + 1900, ok: true, message: "Found 2 pages" })
    .tool("research", "paper_search", P + 2100, "Searching arXiv for ANN graph and quantization indexes", { at: P + 4400, ok: true, message: "Found 4 papers" })
    .tool("research", "course_notes", P + 4600, "Searching course notes for vector indexes", { at: P + 5500, ok: true, message: "Found 1 matching passage" }, { terminalFirst: true })
    .tool("research", "pdf_extraction", P + 5700, "Extracting text from the HNSW paper (arXiv:1603.09320)", { at: P + 8200, ok: true, message: "Extracted 4 passages from 13 pages" }, { callbackMissed: true });
}

function developerOpening(b: ScriptBuilder) {
  b.tool("developer", "github_search", P + 500, "Searching GitHub for approximate nearest neighbor libraries", { at: P + 1700, ok: true, message: "Found 5 repositories" }).tool(
    "developer",
    "repo_analysis",
    P + 1900,
    "Reading nmslib/hnswlib",
    { at: P + 5000, ok: true, message: "Inspected README and 4 source files" },
  );
}

export function buildScript(id: ScenarioId, runId: string, startedAt: number): Script {
  const b = new ScriptBuilder(runId, startedAt);

  if (id === "planning-failed") {
    b.end(2600, { status: "failed", error: "Planning failed: the Gemini request timed out after 30 s, so no agent was started." });
    return { steps: b.steps };
  }

  b.plan(P);

  if (id === "completed" || id === "disconnect") {
    researchHappyPath(b);
    developerOpening(b);
    b.tool("developer", "python_execution", P + 5200, "Running recall benchmark in Python", { at: P + 8000, ok: true, message: "Execution completed (exit 0)" })
      .tool("developer", "duckdb", P + 8200, "Querying benchmark results", { at: P + 9000, ok: true, message: "Returned 3 rows" })
      .finishAgent("research", P + 8800, {
        status: "completed",
        summary: "ANN search trades exactness for sub-linear query time. HNSW (graph) and IVF-PQ (quantization) dominate; recall/latency is tuned at query time.",
        sources: RESEARCH_SOURCES,
        artifacts: RESEARCH_ARTIFACTS,
      })
      .finishAgent("developer", P + 9600, {
        status: "completed",
        summary: "FAISS, hnswlib, and Annoy are the most used libraries. hnswlib's index was inspected and benchmarked: recall@10 0.712 → 0.994 as ef rises 16 → 256.",
        sources: DEVELOPER_SOURCES,
        artifacts: DEVELOPER_ARTIFACTS,
      })
      .phase(P + 9700, "synthesis")
      .end(P + 12200, { status: "completed", final_answer: FINAL_ANSWER });
    return { steps: b.steps, offline: id === "disconnect" ? { from: P + 2800, to: P + 6800 } : undefined };
  }

  if (id === "partial") {
    researchHappyPath(b);
    b.tool("developer", "github_search", P + 500, "Searching GitHub for approximate nearest neighbor libraries", { at: P + 1700, ok: true, message: "Found 5 repositories" })
      .tool("developer", "python_execution", P + 1900, "Running recall benchmark in Python", { at: P + 6900, ok: false, message: "Execution timed out after 5 s" })
      .finishAgent("research", P + 8800, {
        status: "completed",
        summary: "ANN search trades exactness for sub-linear query time. HNSW (graph) and IVF-PQ (quantization) dominate; recall/latency is tuned at query time.",
        sources: RESEARCH_SOURCES,
        artifacts: RESEARCH_ARTIFACTS,
      })
      .finishAgent("developer", P + 7200, {
        status: "failed",
        summary: "Found candidate repositories, but the benchmark did not finish.",
        sources: DEVELOPER_SOURCES.slice(0, 3),
        artifacts: [],
        error: "The Python benchmark exceeded the execution time limit, so no measurements were produced.",
      })
      .phase(P + 9000, "synthesis")
      .end(P + 11200, {
        status: "partial",
        final_answer: PARTIAL_ANSWER,
        error: "The developer agent failed: the Python benchmark exceeded the execution time limit.",
      });
    return { steps: b.steps };
  }

  // Both agents fail.
  b.tool("research", "brave_search", P + 300, "Searching the web for ANN algorithms", { at: P + 1400, ok: false, message: "Brave search failed: the API key was rejected (HTTP 401)" })
    .tool("research", "wikipedia", P + 1600, "Searching Wikipedia for nearest neighbor search")
    .tool("developer", "github_search", P + 500, "Searching GitHub for approximate nearest neighbor libraries", { at: P + 2200, ok: false, message: "GitHub search failed: rate limit reached" })
    .finishAgent("developer", P + 2600, {
      status: "failed",
      summary: "",
      sources: [],
      artifacts: [],
      error: "GitHub API rate limit reached; no repositories could be retrieved.",
    })
    .finishAgent("research", P + 4200, {
      status: "failed",
      summary: "",
      sources: [],
      artifacts: [],
      error: "The research agent stopped responding and the request timed out.",
    })
    .end(P + 4400, { status: "failed", error: "Both agents failed, so no answer was generated. Agent errors are shown in each lane." });
  return { steps: b.steps };
}
