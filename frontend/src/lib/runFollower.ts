import { ApiError, isAbortError, type Backend } from "../api/client";
import { isTerminalRun, type RunState } from "../types";

export type Connection = "unknown" | "online" | "offline";

export interface FollowerState {
  /** The question being followed (trimmed), or null before the first one. */
  query: string | null;
  runId: string | null;
  /** Last snapshot received. Kept through connection loss. */
  run: RunState | null;
  submitting: boolean;
  /** The question could not be started (validation or unreachable backend). */
  submitError: string | null;
  /** Following stopped for a reason retrying won't fix (e.g. unknown run). */
  followError: string | null;
  connection: Connection;
  /** Why the last poll failed while we keep retrying. */
  connectionMessage: string | null;
  /** Client clock time of the last successful snapshot. */
  lastUpdatedAt: number | null;
  /** Client clock time at which a terminal snapshot was first seen. */
  finishedAt: number | null;
  /** Whether polling is active. */
  following: boolean;
}

export const INITIAL_STATE: FollowerState = {
  query: null,
  runId: null,
  run: null,
  submitting: false,
  submitError: null,
  followError: null,
  connection: "unknown",
  connectionMessage: null,
  lastUpdatedAt: null,
  finishedAt: null,
  following: false,
};

export interface FollowerOptions {
  pollMs?: number;
  maxBackoffMs?: number;
  now?: () => number;
}

/**
 * Starts a run and follows it by fetching the full snapshot about once per
 * second, until the run is completed, partial, or failed.
 *
 * Every request belongs to a "generation". Starting a new question bumps the
 * generation and aborts in-flight requests, so a slow response for an old
 * question can never overwrite the new question's state.
 */
export class RunFollower {
  private state: FollowerState = INITIAL_STATE;
  private generation = 0;
  private controller: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private failures = 0;
  private readonly pollMs: number;
  private readonly maxBackoffMs: number;
  private readonly now: () => number;

  constructor(
    private readonly backend: Backend,
    private readonly onChange: (state: FollowerState) => void,
    options: FollowerOptions = {},
  ) {
    this.pollMs = options.pollMs ?? 1000;
    this.maxBackoffMs = options.maxBackoffMs ?? 5000;
    this.now = options.now ?? Date.now;
  }

  getState(): FollowerState {
    return this.state;
  }

  async start(rawQuery: string): Promise<void> {
    const query = rawQuery.trim();
    if (!query) {
      this.set({ submitError: "Enter a question to start a run." });
      return;
    }

    const gen = this.reset();
    this.state = { ...INITIAL_STATE, connection: this.state.connection };
    this.set({ query, submitting: true });

    try {
      const { run_id } = await this.backend.createRun(query, this.controller!.signal);
      if (gen !== this.generation) return;
      this.set({ runId: run_id, submitting: false, following: true, connection: "online", connectionMessage: null });
      void this.poll(gen, run_id);
    } catch (err) {
      if (gen !== this.generation || isAbortError(err)) return;
      const unreachable = err instanceof ApiError && err.kind === "network";
      this.set({
        submitting: false,
        submitError: unreachable
          ? "Couldn't reach the backend. Check that it is running, then try again."
          : err instanceof Error
            ? err.message
            : "The question could not be started.",
        connection: unreachable ? "offline" : this.state.connection,
      });
    }
  }

  /** Stop following the current run (state is kept on screen). */
  stop(): void {
    this.reset();
    this.set({ following: false });
  }

  dispose(): void {
    this.reset();
  }

  private reset(): number {
    this.generation += 1;
    this.controller?.abort();
    this.controller = new AbortController();
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.failures = 0;
    return this.generation;
  }

  private set(patch: Partial<FollowerState>): void {
    this.state = { ...this.state, ...patch };
    this.onChange(this.state);
  }

  private schedule(gen: number, runId: string, delay: number): void {
    if (gen !== this.generation) return;
    this.timer = setTimeout(() => void this.poll(gen, runId), delay);
  }

  private async poll(gen: number, runId: string): Promise<void> {
    this.timer = null;
    try {
      const run = await this.backend.getRun(runId, this.controller!.signal);
      if (gen !== this.generation) return;
      this.failures = 0;
      const finished = isTerminalRun(run.status);
      // Apply the final snapshot (including its events) before stopping.
      this.set({
        run,
        connection: "online",
        connectionMessage: null,
        lastUpdatedAt: this.now(),
        finishedAt: finished ? (this.state.finishedAt ?? this.now()) : null,
        following: !finished,
      });
      if (!finished) this.schedule(gen, runId, this.pollMs);
    } catch (err) {
      if (gen !== this.generation || isAbortError(err)) return;

      if (err instanceof ApiError && err.kind === "http" && err.status === 404) {
        this.set({
          following: false,
          followError:
            "The backend no longer has this run. It may have restarted, which clears run history. Ask the question again to start a new run.",
        });
        return;
      }
      if (err instanceof ApiError && err.kind === "http" && err.status !== undefined && err.status < 500) {
        this.set({ following: false, followError: err.message });
        return;
      }

      // Network failure, 5xx, or an unreadable body: keep the last known
      // state on screen and retry with backoff. Never infer agent failure.
      this.failures += 1;
      const delay = Math.min(this.pollMs * 2 ** (this.failures - 1), this.maxBackoffMs);
      this.set({
        connection: "offline",
        connectionMessage: err instanceof Error ? err.message : "Couldn't reach the backend.",
      });
      this.schedule(gen, runId, delay);
    }
  }
}
