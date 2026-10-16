import type { CreateRunResponse, RunState } from "../types";

/**
 * Everything the dashboard needs from the backend. The real HTTP client and
 * the in-browser demo backend both implement this, so components never know
 * which one they are talking to.
 */
export interface Backend {
  readonly kind: "http" | "mock";
  health(signal?: AbortSignal): Promise<void>;
  createRun(query: string, signal?: AbortSignal): Promise<CreateRunResponse>;
  getRun(runId: string, signal?: AbortSignal): Promise<RunState>;
}

/**
 * `network`: the request never got an HTTP response (offline, DNS, timeout).
 * `http`: the server answered with an error status.
 * `invalid`: the server answered 2xx but the body is not what we expect.
 */
export class ApiError extends Error {
  constructor(
    readonly kind: "network" | "http" | "invalid",
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

const REQUEST_TIMEOUT_MS = 8000;

/** Turn FastAPI's `{"detail": ...}` error bodies into one readable sentence. */
export function readErrorDetail(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : null))
      .filter((m): m is string => Boolean(m));
    if (messages.length) return messages.join("; ");
  }
  return null;
}

export function createHttpBackend(baseUrl = ""): Backend {
  const root = baseUrl.replace(/\/+$/, "");

  async function request<T>(path: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
    const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
    const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

    let res: Response;
    try {
      res = await fetch(`${root}${path}`, {
        ...init,
        signal: combined,
        headers: { Accept: "application/json", ...init.headers },
      });
    } catch (err) {
      // Caller-initiated aborts propagate unchanged so they can be ignored.
      if (signal?.aborted) throw err;
      if (timeout.aborted) throw new ApiError("network", "The backend did not respond in time.");
      throw new ApiError("network", "Couldn't reach the backend.");
    }

    let body: unknown = null;
    const text = await res.text();
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        if (res.ok) throw new ApiError("invalid", "The backend sent a response the dashboard can't read.", res.status);
      }
    }

    if (!res.ok) {
      // Gateway errors, and empty 5xx bodies from a dev or ingress proxy, mean
      // the backend itself was not reached.
      if ([502, 503, 504].includes(res.status) || (res.status >= 500 && !text)) {
        throw new ApiError("network", `Couldn't reach the backend (HTTP ${res.status} from the proxy).`, res.status);
      }
      const detail = readErrorDetail(body);
      throw new ApiError("http", detail ?? `The backend returned HTTP ${res.status}.`, res.status);
    }
    return body as T;
  }

  return {
    kind: "http",
    async health(signal) {
      await request<unknown>("/api/health", { method: "GET" }, signal);
    },
    async createRun(query, signal) {
      const body = await request<CreateRunResponse>(
        "/api/runs",
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }) },
        signal,
      );
      if (!body || typeof body.run_id !== "string") {
        throw new ApiError("invalid", "The backend accepted the question but didn't return a run ID.");
      }
      return body;
    },
    async getRun(runId, signal) {
      const body = await request<RunState>(`/api/runs/${encodeURIComponent(runId)}`, { method: "GET" }, signal);
      if (!body || typeof body.run_id !== "string" || typeof body.status !== "string") {
        throw new ApiError("invalid", "The backend sent a run snapshot the dashboard can't read.");
      }
      return normalizeRun(body);
    },
  };
}

/** Fill list/map fields defensively so a missing key never crashes a view. */
export function normalizeRun(run: RunState): RunState {
  return {
    ...run,
    plan: run.plan ?? null,
    agents: run.agents ?? {},
    events: Array.isArray(run.events) ? run.events : [],
    final_answer: run.final_answer ?? null,
    error: run.error ?? null,
  };
}
