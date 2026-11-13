import { useMemo, useState } from "react";
import { backend, getScenario, isDemo, setScenario } from "./api";
import { EXAMPLE_QUESTION, type ScenarioId } from "./api/mockScenarios";
import { AgentLane } from "./components/AgentLane";
import { AnswerPanel } from "./components/AnswerPanel";
import { QueryForm } from "./components/QueryForm";
import { RunHeader } from "./components/RunHeader";
import { statusText } from "./components/Status";
import { useHealth } from "./hooks/useHealth";
import { useNow } from "./hooks/useNow";
import { useRunFollower } from "./hooks/useRunFollower";
import { agentActivity, groupToolCalls } from "./lib/timeline";
import type { Connection } from "./lib/runFollower";
import { AGENT_NAMES, type RunState } from "./types";

export default function App() {
  const { state, start } = useRunFollower(backend);
  const [scenario, setScenarioState] = useState<ScenarioId>(getScenario());
  const run = state.run;
  const active = state.submitting || state.following;
  const now = useNow(active);
  const health = useHealth(backend, state.following);
  const connection: Connection = state.following || state.submitting ? state.connection : health;

  const calls = useMemo(() => (run ? groupToolCalls(run) : []), [run]);
  const activity = useMemo(
    () => ({ research: agentActivity(calls, "research"), developer: agentActivity(calls, "developer") }),
    [calls],
  );
  const hasRun = Boolean(run || state.query);
  const planning = Boolean(state.submitting || (run && run.phase === "planning" && !run.plan && run.status !== "failed"));

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-10 focus:rounded focus:bg-amber focus:px-3 focus:py-2 focus:text-canvas"
      >
        Skip to content
      </a>

      <header className="border-b border-line">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex gap-[3px]">
              <span className="h-5 w-[7px] rounded-[2px] bg-research" />
              <span className="h-5 w-[7px] rounded-[2px] bg-developer" />
            </span>
            <div>
              <h1 className="text-base leading-tight font-semibold text-ink">Multi-Agent AI Platform</h1>
              <p className="text-2xs text-ink-faint">One question, two agents, one combined answer</p>
            </div>
          </div>
          <ConnectionIndicator connection={connection} demo={isDemo} />
        </div>
      </header>

      <main id="main" className="mx-auto flex max-w-[1480px] flex-col gap-8 px-4 pt-6 pb-16 sm:px-6">
        <div className="max-w-[860px]">
          <QueryForm
            onSubmit={(q) => void start(q)}
            submitting={state.submitting}
            error={state.submitError}
            example={EXAMPLE_QUESTION}
            demo={
              isDemo
                ? {
                    scenario,
                    onScenario: (id) => {
                      setScenario(id);
                      setScenarioState(id);
                    },
                  }
                : undefined
            }
          />
          {!hasRun && connection === "offline" && (
            <p className="mt-3 text-sm text-amber-ink">
              The backend isn't answering its health check. You can still ask; the dashboard will report what happens.
            </p>
          )}
        </div>

        {hasRun && <RunHeader state={state} now={now} />}

        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(360px,0.95fr)] xl:gap-5">
          {AGENT_NAMES.map((agent) => (
            <AgentLane key={agent} agent={agent} run={run} activity={activity[agent]} now={now} planning={planning} />
          ))}
          <div
            // On wide screens the answer stays beside the lanes and scrolls on its own.
            className="lg:col-span-2 xl:sticky xl:top-4 xl:col-span-1 xl:max-h-[calc(100vh-2rem)] xl:overflow-y-auto xl:rounded-xl xl:[scrollbar-color:var(--color-line-strong)_transparent] xl:[scrollbar-width:thin]"
          >
            <AnswerPanel run={run} />
          </div>
        </div>
      </main>

      <Announcer run={run} />
    </div>
  );
}

function ConnectionIndicator({ connection, demo }: { connection: Connection; demo: boolean }) {
  const text =
    connection === "online"
      ? demo
        ? "Demo backend running"
        : "Backend connected"
      : connection === "offline"
        ? "Backend unreachable"
        : "Checking backend";
  const dot = connection === "online" ? "bg-research" : connection === "offline" ? "bg-danger" : "bg-ink-faint";
  return (
    <p className="inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-2xs text-ink-muted" role="status">
      <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </p>
  );
}

/** Screen-reader announcements for status changes only (not every tick). */
function Announcer({ run }: { run: RunState | null }) {
  const message = run
    ? [
        `Run ${statusText(run.status).toLowerCase()}.`,
        ...AGENT_NAMES.map((a) => `${a === "research" ? "Research" : "Developer"} agent ${statusText(run.agents[a]?.status ?? "queued").toLowerCase()}.`),
        run.final_answer ? "Combined answer ready." : "",
      ].join(" ")
    : "";
  return (
    <div className="sr-only" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  );
}
