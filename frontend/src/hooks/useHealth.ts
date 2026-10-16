import { useEffect, useState } from "react";
import { isAbortError, type Backend } from "../api/client";
import type { Connection } from "../lib/runFollower";

/**
 * Checks GET /api/health while no run is being polled (the run polling itself
 * reports connection status during a run).
 */
export function useHealth(backend: Backend, paused: boolean, intervalMs = 10_000): Connection {
  const [status, setStatus] = useState<Connection>("unknown");

  useEffect(() => {
    if (paused) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    const check = async () => {
      try {
        await backend.health(controller.signal);
        setStatus("online");
      } catch (err) {
        if (isAbortError(err)) return;
        setStatus("offline");
      }
      if (!controller.signal.aborted) timer = setTimeout(check, intervalMs);
    };
    void check();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [backend, paused, intervalMs]);

  return status;
}
