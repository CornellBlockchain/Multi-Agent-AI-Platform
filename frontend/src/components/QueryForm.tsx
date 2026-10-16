import { useId, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { SCENARIOS, type ScenarioId } from "../api/mockScenarios";

interface Props {
  onSubmit: (query: string) => void;
  submitting: boolean;
  error: string | null;
  example: string;
  demo?: { scenario: ScenarioId; onScenario: (id: ScenarioId) => void };
}

export function QueryForm({ onSubmit, submitting, error, example, demo }: Props) {
  const [value, setValue] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = useId();
  const hintId = useId();
  const shownError = localError ?? error;
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the question (up to ~8 lines), then scroll.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!value.trim()) {
      setLocalError("Enter a question to start a run.");
      return;
    }
    setLocalError(null);
    onSubmit(value);
  };

  // Enter submits; Shift+Enter adds a new line.
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-3">
      <label htmlFor={inputId} className="text-[1.0667rem] font-semibold text-ink">
        Ask a question for both agents
      </label>
      <div
        className={`rounded-lg border bg-surface transition-colors focus-within:border-amber ${
          shownError ? "border-danger" : "border-line-strong"
        }`}
      >
        <textarea
          id={inputId}
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (localError) setLocalError(null);
          }}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="What do you want researched and built on?"
          aria-invalid={Boolean(shownError)}
          aria-describedby={`${hintId}${shownError ? ` ${errorId}` : ""}`}
          className="block w-full resize-none rounded-lg bg-transparent px-4 pt-3 pb-2 text-[1.2rem] leading-snug text-ink placeholder:text-ink-faint focus:outline-none focus-visible:outline-none min-h-[5.5rem]"
        />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-3 py-2.5">
          <p id={hintId} className="text-2xs text-ink-faint">
            Press Enter to ask, Shift+Enter for a new line
          </p>
          <button
            type="submit"
            disabled={submitting}
            className="inline-flex items-center gap-2 rounded-md bg-amber px-4 py-2 text-sm font-semibold text-canvas transition-[filter] hover:brightness-110 disabled:cursor-progress disabled:opacity-70"
          >
            {submitting ? "Starting…" : "Ask both agents"}
          </button>
        </div>
      </div>

      {shownError && (
        <p id={errorId} role="alert" className="text-sm text-danger-ink">
          {shownError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <button
          type="button"
          onClick={() => {
            setValue(example);
            setLocalError(null);
            document.getElementById(inputId)?.focus();
          }}
          className="max-w-full text-left text-ink-muted underline decoration-line-strong underline-offset-4 hover:text-ink hover:decoration-ink-muted"
        >
          Use an example: <span className="text-ink">{example}</span>
        </button>
      </div>

      {demo && (
        <fieldset className="mt-1 flex flex-wrap items-center gap-2 rounded-md border border-dashed border-amber/50 px-3 py-2">
          <legend className="px-1 text-2xs text-amber-ink">Demo data — scripted runs, not real agents</legend>
          {SCENARIOS.map((s) => (
            <label
              key={s.id}
              title={s.hint}
              className={`cursor-pointer rounded-full border px-3 py-1 text-2xs transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-amber ${
                demo.scenario === s.id ? "border-amber bg-amber-wash text-amber-ink" : "border-line text-ink-muted hover:text-ink"
              }`}
            >
              <input
                type="radio"
                name="demo-scenario"
                value={s.id}
                checked={demo.scenario === s.id}
                onChange={() => demo.onScenario(s.id)}
                className="sr-only"
              />
              {s.label}
            </label>
          ))}
          <span className="text-2xs text-ink-faint">
            {SCENARIOS.find((s) => s.id === demo.scenario)?.hint}
          </span>
        </fieldset>
      )}
    </form>
  );
}
