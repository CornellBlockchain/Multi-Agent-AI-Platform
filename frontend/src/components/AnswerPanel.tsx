import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { RunState } from "../types";
import { AGENT_NAMES, isTerminalAgent } from "../types";
import { allSources } from "../lib/timeline";
import { CrossIcon, SpinnerIcon, WarningIcon } from "./icons";
import { SourceItem } from "./Findings";

const markdownComponents: Components = {
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

function Waiting({ run }: { run: RunState }) {
  if (run.phase === "synthesis") {
    return (
      <p className="flex items-center gap-2 text-sm text-ink-muted">
        <SpinnerIcon size={15} className="text-amber" />
        Gemini is combining both agents' findings.
      </p>
    );
  }
  const done = AGENT_NAMES.filter((a) => isTerminalAgent(run.agents[a]?.status)).length;
  return (
    <p className="text-sm text-ink-muted">
      {run.phase === "planning"
        ? "The answer is written after the plan is made and both agents report back."
        : `Waiting for both agents to report: ${done} of 2 finished.`}
    </p>
  );
}

export function AnswerPanel({ run }: { run: RunState | null }) {
  const sources = run ? allSources(run) : [];
  const answer = run?.final_answer ?? null;
  const ended = run && (run.status === "completed" || run.status === "partial" || run.status === "failed");

  return (
    <section
      id="answer"
      aria-labelledby="answer-title"
      className="flex min-w-0 scroll-mt-4 flex-col rounded-xl border border-line bg-raised"
    >
      <div className="rounded-t-xl border-t-[3px] border-amber px-5 pt-3.5 pb-3 sm:px-6">
        <h2 id="answer-title" className="text-[1.2rem] font-semibold leading-tight text-ink">
          Combined answer
        </h2>
        <p className="mt-0.5 text-2xs text-ink-faint">Written by Gemini from both agents' findings</p>
      </div>

      <div className="flex flex-col gap-5 px-5 pt-2 pb-6 sm:px-6">
        {!run && <p className="text-sm text-ink-faint">The answer appears here once both agents have reported.</p>}

        {run?.status === "partial" && (
          <div className="flex items-start gap-2.5 rounded-lg border border-amber/40 bg-amber-wash px-4 py-3 text-sm text-amber-ink">
            <WarningIcon size={16} className="mt-0.5 shrink-0" />
            <p>
              <span className="font-semibold">Partial result.</span>{" "}
              {run.error ?? "One agent did not finish; the answer uses the findings that were returned."}
            </p>
          </div>
        )}

        {run?.status === "failed" && (
          <div role="alert" className="flex items-start gap-2.5 rounded-lg border border-danger/40 bg-danger-wash px-4 py-3 text-sm text-danger-ink">
            <CrossIcon size={16} className="mt-0.5 shrink-0" />
            <p>
              <span className="font-semibold">No answer was generated.</span> {run.error ?? "The run failed."}
              {sources.length > 0 && " The findings that were returned are listed in the agent lanes."}
            </p>
          </div>
        )}

        {run && !ended && <Waiting run={run} />}

        {answer ? (
          <div className="answer-prose">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {answer}
            </ReactMarkdown>
          </div>
        ) : (
          ended &&
          run.status !== "failed" && (
            <p className="text-sm text-ink-muted">
              The final answer couldn't be generated. {run.error ?? ""} The agents' findings are still shown in their lanes.
            </p>
          )
        )}

        {sources.length > 0 && (ended || answer) && (
          <div>
            <h3 className="mb-1 flex items-baseline gap-2 text-sm font-semibold text-ink-muted">
              Sources returned by the agents
              <span className="font-normal tabular-nums text-ink-faint">{sources.length}</span>
            </h3>
            <ul className="divide-y divide-line/70">
              {sources.map((s) => (
                <SourceItem
                  key={s.key}
                  source={s}
                  marker={
                    <span
                      className={`lane-${s.agent} mt-0.5 h-fit shrink-0 rounded-sm bg-[var(--lane-wash)] px-1.5 py-0.5 text-[0.7rem] font-medium text-[var(--lane-ink)]`}
                    >
                      {s.agent === "research" ? "Research" : "Developer"}
                    </span>
                  }
                />
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
