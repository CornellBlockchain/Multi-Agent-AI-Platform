import {
  AGENT_NAMES,
  isTerminalAgent,
  isTerminalRun,
  type AgentName,
  type RunState,
  type Source,
  type ToolEvent,
} from "../types";

/**
 * `stopped` is a dashboard-only state: the call started, never reported an
 * outcome, and its agent (or the whole run) has already finished. We stop the
 * spinner but do not claim the tool failed.
 */
export type CallStatus = "running" | "completed" | "failed" | "stopped";

/** One row in the activity timeline: one tool invocation. */
export interface ToolCall {
  key: string;
  agent: AgentName;
  taskId: string;
  toolCallId: string;
  tool: string;
  status: CallStatus;
  startMessage: string | null;
  endMessage: string | null;
  /** Epoch ms, from event timestamps. */
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
}

function parseTime(iso: string | undefined): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
}

/**
 * All events for a run: the live callback log plus any events returned with
 * agent results (which recover callbacks the backend missed), de-duplicated
 * by event_id and limited to this run.
 */
export function collectEvents(run: RunState): ToolEvent[] {
  const seen = new Set<string>();
  const out: ToolEvent[] = [];
  const add = (e: ToolEvent) => {
    if (!e || typeof e.event_id !== "string" || seen.has(e.event_id)) return;
    if (e.run_id && e.run_id !== run.run_id) return;
    seen.add(e.event_id);
    out.push(e);
  };
  run.events.forEach(add);
  for (const name of AGENT_NAMES) run.agents[name]?.result?.events?.forEach(add);
  return out;
}

/**
 * Group start and terminal events into one row per (task_id, tool_call_id).
 *
 * Order-independent: a terminal event always wins, so a late `tool.started`
 * cannot turn a finished row back into a running one. It only fills in the
 * start message and time.
 */
export function groupToolCalls(run: RunState): ToolCall[] {
  const rows = new Map<string, ToolCall & { firstSeen: number }>();

  collectEvents(run).forEach((e, index) => {
    const key = `${e.task_id}::${e.tool_call_id}`;
    let row = rows.get(key);
    if (!row) {
      row = {
        key,
        agent: e.agent,
        taskId: e.task_id,
        toolCallId: e.tool_call_id,
        tool: e.tool,
        status: "running",
        startMessage: null,
        endMessage: null,
        startedAt: null,
        endedAt: null,
        durationMs: null,
        firstSeen: index,
      };
      rows.set(key, row);
    }
    const at = parseTime(e.timestamp);

    if (e.type === "tool.started") {
      row.startMessage = e.message;
      row.startedAt = at;
      return;
    }
    if (e.type === "tool.completed" || e.type === "tool.failed") {
      // Exactly one terminal event per call is expected; if duplicates
      // arrive with different IDs, keep the first outcome we saw.
      if (row.status === "completed" || row.status === "failed") return;
      row.status = e.type === "tool.completed" ? "completed" : "failed";
      row.endMessage = e.message;
      row.endedAt = at;
      if (typeof e.duration_ms === "number" && e.duration_ms >= 0) row.durationMs = e.duration_ms;
    }
  });

  const runOver = isTerminalRun(run.status);
  const result: ToolCall[] = [];
  for (const { firstSeen: _firstSeen, ...row } of rows.values()) {
    if (row.durationMs === null && row.startedAt !== null && row.endedAt !== null) {
      row.durationMs = Math.max(0, row.endedAt - row.startedAt);
    }
    if (row.startedAt === null && row.endedAt !== null && row.durationMs !== null) {
      row.startedAt = row.endedAt - row.durationMs;
    }
    if (row.status === "running") {
      const agentOver = isTerminalAgent(run.agents[row.agent]?.status);
      if (runOver || agentOver) row.status = "stopped";
    }
    result.push(row);
  }

  const sortKey = (r: ToolCall) => r.startedAt ?? r.endedAt ?? Number.MAX_SAFE_INTEGER;
  // Array.prototype.sort is stable, so ties keep arrival order.
  return result.sort((a, b) => sortKey(a) - sortKey(b));
}

export interface AgentActivity {
  calls: ToolCall[];
  /** Most recently started call that is still running. */
  active: ToolCall | null;
  completed: number;
  failed: number;
  /** First and last event times for this agent, for elapsed-time display. */
  firstAt: number | null;
  lastAt: number | null;
}

export function agentActivity(calls: ToolCall[], agent: AgentName): AgentActivity {
  const mine = calls.filter((c) => c.agent === agent);
  let active: ToolCall | null = null;
  let firstAt: number | null = null;
  let lastAt: number | null = null;
  let completed = 0;
  let failed = 0;
  for (const c of mine) {
    if (c.status === "running") {
      if (!active || (c.startedAt ?? 0) >= (active.startedAt ?? 0)) active = c;
    }
    if (c.status === "completed") completed++;
    if (c.status === "failed") failed++;
    for (const t of [c.startedAt, c.endedAt]) {
      if (t === null) continue;
      if (firstAt === null || t < firstAt) firstAt = t;
      if (lastAt === null || t > lastAt) lastAt = t;
    }
  }
  return { calls: mine, active, completed, failed, firstAt, lastAt };
}

/** http(s) only; anything else (javascript:, file:, container paths) is not a link. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

export function sourceHost(url: string | null): string | null {
  const href = safeHref(url);
  if (!href) return null;
  return new URL(href).hostname.replace(/^www\./, "");
}

export interface AttributedSource extends Source {
  agent: AgentName;
  key: string;
}

/** Every returned source across both agents, de-duplicated per agent. */
export function allSources(run: RunState): AttributedSource[] {
  const out: AttributedSource[] = [];
  for (const agent of AGENT_NAMES) {
    const seen = new Set<string>();
    for (const s of run.agents[agent]?.result?.sources ?? []) {
      const key = `${agent}::${s.url ?? `local:${s.title}`}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ ...s, agent, key });
    }
  }
  return out;
}
