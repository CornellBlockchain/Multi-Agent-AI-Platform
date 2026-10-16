import { useEffect, useRef, useState, type ReactNode } from "react";
import type { AgentName, AgentState, RunState } from "../types";
import { isTerminalAgent, isTerminalRun } from "../types";
import type { AgentActivity, CallStatus, ToolCall } from "../lib/timeline";
import { formatClock, formatDuration, humanizeTool } from "../lib/format";
import { StatusIcon, StatusLabel } from "./Status";
import { ArtifactView, SourceList } from "./Findings";

export const AGENT_META: Record<AgentName, { title: string; tools: string }> = {
  research: { title: "Research agent", tools: "Web search, Wikipedia, papers, PDFs, course notes, weather" },
  developer: { title: "Developer agent", tools: "GitHub, web pages, Python and C++, DuckDB, repository analysis" },
};

type LaneStatus = "idle" | "queued" | "running" | "completed" | "failed" | "stopped";

function laneStatus(run: RunState | null, agent: AgentState | undefined): { status: LaneStatus; label?: string } {
  if (!run) return { status: "idle" };
  const s = agent?.status ?? "queued";
  if (isTerminalRun(run.status) && !isTerminalAgent(s)) {
    return s === "queued" ? { status: "stopped", label: "Not started" } : { status: "stopped", label: "Stopped" };
  }
  return { status: s };
}

interface Props {
  agent: AgentName;
  run: RunState | null;
  activity: AgentActivity;
  now: number;
  planning: boolean;
}

export function AgentLane({ agent, run, activity, now, planning }: Props) {
  const meta = AGENT_META[agent];
  const state = run?.agents[agent];
  const result = state?.result ?? null;
  const { status, label } = laneStatus(run, state);
  const assignment = run?.plan?.[agent] ?? null;
  const finished = status === "completed" || status === "failed" || status === "stopped";
  const elapsed =
    activity.firstAt === null ? null : (finished ? (activity.lastAt ?? activity.firstAt) : now) - activity.firstAt;
  const headingId = `lane-${agent}-title`;

  return (
    <section
      aria-labelledby={headingId}
      className={`lane-${agent} flex min-w-0 flex-col rounded-xl border border-line bg-surface ${
        status === "idle" ? "opacity-80" : ""
      }`}
    >
      {/* Agent card */}
      <div className="rounded-t-xl border-t-[3px] border-[var(--lane)] bg-[var(--lane-wash)] px-4 pt-3.5 pb-3 sm:px-5">
        <div className="flex items-baseline justify-between gap-3">
          <h2 id={headingId} className="min-w-0 text-[1.2rem] font-semibold leading-tight text-[var(--lane-ink)]">
            {meta.title}
          </h2>
          <StatusLabel status={status} className="shrink-0" />
          {label && <span className="sr-only">({label})</span>}
        </div>
        <p className="mt-0.5 text-2xs text-ink-faint">{meta.tools}</p>

        <CurrentTool status={status} label={label} activity={activity} now={now} error={result?.error ?? null} />

        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-2xs text-ink-muted">
          <Metric term={finished ? "Active for" : "Elapsed"} value={elapsed === null ? "—" : formatClock(elapsed)} />
          <Metric term="Tools finished" value={String(activity.completed + activity.failed)} />
          {activity.failed > 0 && <Metric term="Tools failed" value={String(activity.failed)} tone="text-danger-ink" />}
          <Metric term="Sources" value={result ? String(result.sources.length) : "—"} />
        </dl>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-5 px-4 pt-4 pb-5 sm:px-5">
        <Block title="Assignment">
          {assignment ? (
            <p className="text-sm leading-relaxed text-ink-muted">{assignment}</p>
          ) : planning ? (
            <p className="flex items-center gap-2 text-sm text-ink-faint">
              <StatusIcon status="running" size={14} />
              Waiting for the plan from Gemini
            </p>
          ) : (
            <p className="text-sm text-ink-faint">{run ? "No assignment was made." : "Assigned after you ask a question."}</p>
          )}
        </Block>

        <Block title="Activity" count={activity.calls.length || undefined}>
          {activity.calls.length ? (
            <ol className="-mx-2">
              {activity.calls.map((c) => (
                <ActivityRow key={c.key} call={c} now={now} />
              ))}
            </ol>
          ) : (
            <p className="text-sm text-ink-faint">
              {status === "running" ? "Waiting for the first tool to start." : "No tool activity yet."}
            </p>
          )}
        </Block>

        {result?.summary && (
          <Block title="Findings">
            <p className="text-sm leading-relaxed text-ink">{result.summary}</p>
          </Block>
        )}

        {result && (
          <Block title="Sources" count={result.sources.length}>
            {result.sources.length ? (
              <SourceList sources={result.sources} />
            ) : (
              <p className="text-sm text-ink-faint">This agent returned no sources.</p>
            )}
          </Block>
        )}

        {result && result.artifacts.length > 0 && (
          <Block title="Artifacts" count={result.artifacts.length}>
            <div className="flex flex-col gap-3">
              {result.artifacts.map((a, i) => (
                <ArtifactView key={`${a.name}-${i}`} artifact={a} />
              ))}
            </div>
          </Block>
        )}
      </div>
    </section>
  );
}

function Metric({ term, value, tone = "text-ink" }: { term: string; value: string; tone?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt>{term}</dt>
      <dd className={`font-medium tabular-nums ${tone}`}>{value}</dd>
    </div>
  );
}

function Block({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <h3 className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-ink-muted">
        {title}
        {count !== undefined && <span className="font-normal tabular-nums text-ink-faint">{count}</span>}
      </h3>
      {children}
    </div>
  );
}

function CurrentTool({
  status,
  label,
  activity,
  now,
  error,
}: {
  status: LaneStatus;
  label?: string;
  activity: AgentActivity;
  now: number;
  error: string | null;
}) {
  let body: ReactNode;
  const active = activity.active;
  if (status === "running" && active) {
    body = (
      <>
        <StatusIcon status="running" size={15} className="mt-0.5 shrink-0" />
        <span className="min-w-0">
          <span className="font-medium text-ink">{humanizeTool(active.tool)}</span>
          <span className="text-ink-muted">: {active.startMessage ?? "Working"}</span>
          {active.startedAt !== null && (
            <span className="ml-2 tabular-nums text-ink-faint">{formatDuration(now - active.startedAt)}</span>
          )}
        </span>
      </>
    );
  } else if (status === "running") {
    body = <span className="text-ink-muted">Working. No tool is running right now.</span>;
  } else if (status === "completed") {
    body = <span className="text-ink-muted">Finished and returned its findings.</span>;
  } else if (status === "failed") {
    body = <span className="text-danger-ink">{error ?? "The agent reported a failure."}</span>;
  } else if (status === "stopped") {
    body = (
      <span className="text-amber-ink">
        {label === "Not started" ? "The run ended before this agent started." : "The run ended before this agent reported a result."}
      </span>
    );
  } else if (status === "queued") {
    body = <span className="text-ink-faint">Queued until the plan is ready.</span>;
  } else {
    body = <span className="text-ink-faint">Inactive.</span>;
  }
  return (
    <p className="mt-3 flex min-h-[1.5rem] items-start gap-2 text-sm leading-snug break-words">
      {body}
    </p>
  );
}

const TERMINAL: CallStatus[] = ["completed", "failed", "stopped"];

function ActivityRow({ call, now }: { call: ToolCall; now: number }) {
  // Briefly highlight a row when it changes from running to finished.
  const prev = useRef(call.status);
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    if (prev.current === "running" && TERMINAL.includes(call.status)) {
      setSettled(true);
      const t = setTimeout(() => setSettled(false), 1300);
      prev.current = call.status;
      return () => clearTimeout(t);
    }
    prev.current = call.status;
  }, [call.status]);

  const running = call.status === "running";
  const headline =
    call.status === "stopped"
      ? "No result reported before the agent stopped"
      : running
        ? (call.startMessage ?? "Working")
        : (call.endMessage ?? call.startMessage ?? "");
  const time = running
    ? call.startedAt !== null
      ? formatDuration(now - call.startedAt)
      : ""
    : call.status === "stopped"
      ? ""
      : formatDuration(call.durationMs);
  const statusWord = { running: "Running", completed: "Completed", failed: "Failed", stopped: "Stopped" }[call.status];

  return (
    <li className={`flex min-w-0 gap-2.5 rounded-md px-2 py-2 ${settled ? "row-settle" : ""}`}>
      <StatusIcon status={call.status} size={15} className="mt-[3px] shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="min-w-0 truncate text-sm font-medium text-ink" title={call.tool}>
            {humanizeTool(call.tool)}
            <span className="sr-only">, {statusWord}</span>
          </p>
          {time && (
            <span className="shrink-0 text-2xs tabular-nums text-ink-faint">
              {running ? <span className="sr-only">running for </span> : null}
              {time}
            </span>
          )}
        </div>
        <p
          className={`text-sm leading-snug break-words ${
            call.status === "failed" ? "text-danger-ink" : call.status === "stopped" ? "text-amber-ink" : "text-ink-muted"
          }`}
        >
          {headline}
        </p>
        {!running && call.startMessage && call.startMessage !== headline && (
          <p className="text-2xs leading-snug break-words text-ink-faint">{call.startMessage}</p>
        )}
      </div>
    </li>
  );
}
