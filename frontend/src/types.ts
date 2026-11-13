/**
 * Dashboard view of the shared contract (shared/README.md, "Task and Result
 * Fields"). Keep this file in sync with the backend models; if a field name
 * changes in Meeting 1, change it here and nowhere else.
 */

export type AgentName = "research" | "developer";
export const AGENT_NAMES: readonly AgentName[] = ["research", "developer"];

/** Overall run status. */
export type RunStatus = "queued" | "running" | "completed" | "partial" | "failed";
/** Workflow phase. */
export type RunPhase = "planning" | "agents" | "synthesis" | "done";
/** One agent's assigned task. */
export type AgentStatus = "queued" | "running" | "completed" | "failed";

export interface Source {
  title: string;
  /** HTTP/HTTPS URL, or null for a local document. */
  url: string | null;
}

export interface Artifact {
  name: string;
  content: string;
}

export type ToolEventType = "tool.started" | "tool.completed" | "tool.failed";

export interface ToolEvent {
  event_id: string;
  run_id: string;
  task_id: string;
  agent: AgentName;
  tool_call_id: string;
  tool: string;
  type: ToolEventType | (string & {});
  /** UTC ISO 8601. */
  timestamp: string;
  message: string;
  /** Present on completion/failure events. */
  duration_ms?: number | null;
}

export interface AgentResult {
  run_id: string;
  task_id: string;
  agent: AgentName;
  status: "completed" | "failed";
  summary: string;
  sources: Source[];
  artifacts: Artifact[];
  events: ToolEvent[];
  error?: string | null;
}

export interface AgentState {
  task_id: string;
  status: AgentStatus;
  /** Null until the agent finishes. */
  result: AgentResult | null;
}

export interface Plan {
  research: string;
  developer: string;
}

export interface RunState {
  run_id: string;
  query: string;
  /** UTC ISO 8601. */
  started_at: string;
  status: RunStatus;
  phase: RunPhase;
  plan: Plan | null;
  agents: Partial<Record<AgentName, AgentState>>;
  events: ToolEvent[];
  final_answer: string | null;
  error?: string | null;
}

export interface CreateRunResponse {
  run_id: string;
}

export const TERMINAL_RUN_STATUSES: readonly RunStatus[] = ["completed", "partial", "failed"];

export function isTerminalRun(status: RunStatus | undefined): boolean {
  return status !== undefined && TERMINAL_RUN_STATUSES.includes(status);
}

export function isTerminalAgent(status: AgentStatus | undefined): boolean {
  return status === "completed" || status === "failed";
}
