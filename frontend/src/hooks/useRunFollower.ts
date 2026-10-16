import { useCallback, useEffect, useRef, useState } from "react";
import type { Backend } from "../api/client";
import { INITIAL_STATE, RunFollower, type FollowerState } from "../lib/runFollower";

export function useRunFollower(backend: Backend) {
  const [state, setState] = useState<FollowerState>(INITIAL_STATE);
  const followerRef = useRef<RunFollower | null>(null);

  useEffect(() => {
    const follower = new RunFollower(backend, setState);
    followerRef.current = follower;
    return () => follower.dispose();
  }, [backend]);

  const start = useCallback((query: string) => followerRef.current?.start(query), []);
  const stop = useCallback(() => followerRef.current?.stop(), []);

  return { state, start, stop };
}
