import type { RunState } from "../types";
import { isTerminalRun } from "../types";
import type { FollowerState } from "../lib/runFollower";
import { formatClock, formatTimeOfDay } from "../lib/format";
import { CheckIcon, CrossIcon, OfflineIcon, QueuedIcon, SpinnerIcon, WarningIcon } from "./icons";
import { StatusLabel } from "./Status";

type StepState = "done" | "current" | "upcoming" | "failed" | "skipped" | "partial";

const PHASES = ["planning", "agents", "synthesis", "done"] as const;

export function phaseSteps(run: RunState): { label: string; state: StepState }[] {
  const labels = ["Planning", "Agents working", "Combining findings", "Done"];
  const idx = Math.max(0, PHASES.indexOf(run.phase));

  if (run.status === "completed") return labels.map((label) => ({ label, state: "done" }));
  if (run.status === "partial") {
    return labels.map((label, i) => (i < 3 ? { label, state: "done" } : { label: "Partial", state: "partial" }));
  }
  if (run.status === "failed") {
    // Planning failed if no plan; agents failed if none completed; otherwise synthesis.
    const anyCompleted = Object.values(run.agents).some((a) => a?.status === "completed");
    const failIdx = !run.plan ? 0 : !anyCompleted || run.phase === "agents" ? 1 : 2;
    const effective = run.phase === "done" ? failIdx : Math.min(idx, failIdx);
    return labels.map((label, i) => {
      if (i === 3) return { label: "Failed", state: "failed" };
      if (i < effective) return { label, state: "done" };
      if (i === effective) return { label, state: "failed" };
      return { label, state: "skipped" };
    });
  }
  return labels.map((label, i) => ({ label, state: i < idx ? "done" : i === idx ? "current" : "upcoming" }));
}

function StepIcon({ state }: { state: StepState }) {
  switch (state) {
    case "done":
      return <CheckIcon size={14} className="text-ink" />;
    case "current":
      return <SpinnerIcon size={14} className="text-amber" />;
    case "failed":
      return <CrossIcon size={14} className="text-danger" />;
    case "partial":
      return <WarningIcon size={14} className="text-amber" />;
    default:
      return <QueuedIcon size={14} className="text-ink-faint" />;
  }
}

const STEP_SR: Record<StepState, string> = {
  done: "done",
  current: "in progress",
  upcoming: "not started",
  failed: "failed",
  skipped: "skipped",
  partial: "finished with missing findings",
};

interface Props {
  state: FollowerState;
  now: number;
}

export function RunHeader({ state, now }: Props) {
  const run = state.run;
  const question = run?.query ?? state.query ?? "";
  const startedAt = run ? Date.parse(run.started_at) : null;
  const end = state.finishedAt ?? now;
  const elapsed = startedAt !== null && !Number.isNaN(startedAt) ? end - startedAt : null;
  const terminal = isTerminalRun(run?.status);

  return (
    <section aria-label="Current run" className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <p className="text-sm text-ink-faint">Question</p>
        <p className="max-w-[72ch] text-[1.4rem] leading-snug font-medium break-words text-ink">{question}</p>
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        {run ? (
          <StatusLabel status={run.status} />
        ) : (
          <span className="inline-flex items-center gap-1.5 text-sm text-ink-muted">
            <SpinnerIcon size={15} className="text-amber" />
            {state.submitting ? "Sending question" : "Waiting for the first update"}
          </span>
        )}

        {run && (
          <ol className="flex flex-wrap items-center gap-x-3 gap-y-2 sm:gap-x-1" aria-label="Workflow">
            {phaseSteps(run).map((s, i) => (
              <li key={s.label} className="flex items-center gap-1">
                {i > 0 && <span aria-hidden className="mx-1 hidden h-px w-6 bg-line-strong sm:block" />}
                <StepIcon state={s.state} />
                <span
                  className={`text-sm ${
                    s.state === "current"
                      ? "font-semibold text-ink"
                      : s.state === "upcoming" || s.state === "skipped"
                        ? "text-ink-faint"
                        : s.state === "failed"
                          ? "text-danger-ink"
                          : s.state === "partial"
                            ? "text-amber-ink"
                            : "text-ink-muted"
                  }`}
                >
                  {s.label}
                </span>
                <span className="sr-only">({STEP_SR[s.state]})</span>
              </li>
            ))}
          </ol>
        )}

        {elapsed !== null && (
          <p className="text-sm text-ink-muted">
            {terminal ? "Took" : "Elapsed"} <span className="font-medium tabular-nums text-ink">{formatClock(elapsed)}</span>
          </p>
        )}

        {run?.final_answer && (
          <a href="#answer" className="text-sm text-amber-ink underline underline-offset-4 xl:hidden">
            Jump to the answer
          </a>
        )}
      </div>

      {state.connection === "offline" && state.following && (
        <div role="status" className="flex items-start gap-2.5 rounded-lg border border-amber/40 bg-amber-wash px-4 py-3 text-sm text-amber-ink">
          <OfflineIcon size={16} className="mt-0.5 shrink-0" />
          <p>
            <span className="font-semibold">Connection to the backend lost.</span>{" "}
            {state.lastUpdatedAt
              ? `Showing the last update from ${formatTimeOfDay(state.lastUpdatedAt)}.`
              : "No update has arrived yet."}{" "}
            Agents may still be working; this view refreshes when the connection returns.
            <span className="sr-only"> {state.connectionMessage}</span>
          </p>
        </div>
      )}

      {state.followError && (
        <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-danger/40 bg-danger-wash px-4 py-3 text-sm text-danger-ink">
          <CrossIcon size={16} className="mt-0.5 shrink-0" />
          <p>{state.followError}</p>
        </div>
      )}
    </section>
  );
}
