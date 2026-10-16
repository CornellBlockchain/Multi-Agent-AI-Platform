import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Artifact, Source } from "../types";
import { safeHref, sourceHost } from "../lib/timeline";
import { ChevronIcon, CopyIcon, DocumentIcon, ExternalIcon } from "./icons";

export function SourceItem({ source, marker }: { source: Source; marker?: ReactNode }) {
  const href = safeHref(source.url);
  const host = sourceHost(source.url);
  return (
    <li className="flex min-w-0 gap-2.5 py-2">
      {marker}
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="group min-w-0 flex-1 rounded-sm"
          title={source.title}
        >
          <span className="line-clamp-2 break-words text-sm text-ink group-hover:underline group-hover:decoration-ink-faint group-hover:underline-offset-4">
            {source.title || href}
          </span>
          <span className="mt-0.5 inline-flex items-center gap-1 text-2xs text-ink-faint">
            {host}
            <ExternalIcon size={11} />
            <span className="sr-only">(opens in a new tab)</span>
          </span>
        </a>
      ) : (
        <div className="min-w-0 flex-1" title={source.title}>
          <span className="line-clamp-2 break-words text-sm text-ink">{source.title || "Untitled document"}</span>
          <span className="mt-0.5 inline-flex items-center gap-1 text-2xs text-ink-faint">
            <DocumentIcon size={12} />
            {source.url ? "Local document (not a web link)" : "Local document"}
          </span>
        </div>
      )}
    </li>
  );
}

export function SourceList({ sources }: { sources: Source[] }) {
  return (
    <ul className="divide-y divide-line/70">
      {sources.map((s, i) => (
        <SourceItem key={`${s.url ?? "local"}-${s.title}-${i}`} source={s} />
      ))}
    </ul>
  );
}

const COLLAPSED_LINES = 12;

export function ArtifactView({ artifact }: { artifact: Artifact }) {
  const content = artifact.content ?? "";
  const lines = content.split("\n").length;
  const long = lines > COLLAPSED_LINES;
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const bodyId = useId();
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1600);
    } catch {
      /* Clipboard can be unavailable (non-secure origin); the text is still selectable. */
    }
  };

  return (
    <div className="min-w-0 overflow-hidden rounded-md border border-line bg-canvas">
      <div className="flex items-center justify-between gap-2 border-b border-line px-3 py-1.5">
        <p className="min-w-0 truncate text-sm font-medium text-ink" title={artifact.name}>
          {artifact.name || "Untitled artifact"}
        </p>
        <div className="flex shrink-0 items-center gap-1">
          <span className="mr-1 text-2xs text-ink-faint">{lines === 1 ? "1 line" : `${lines} lines`}</span>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-2xs text-ink-muted hover:bg-raised hover:text-ink"
          >
            <CopyIcon size={13} />
            <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
          </button>
        </div>
      </div>
      <div className="relative">
        <pre
          id={bodyId}
          tabIndex={0}
          aria-label={`${artifact.name} content`}
          className={`overflow-x-auto px-3 py-2.5 font-mono text-[0.8rem] leading-relaxed text-ink-muted ${
            long && !open ? "max-h-56 overflow-y-hidden" : ""
          }`}
        >
          {content || "(empty)"}
        </pre>
        {long && !open && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-canvas to-transparent" />
        )}
      </div>
      {long && (
        <button
          type="button"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-center gap-1 border-t border-line py-1.5 text-2xs text-ink-muted hover:bg-raised hover:text-ink"
        >
          {open ? "Show less" : `Show all ${lines} lines`}
          <ChevronIcon size={13} className={open ? "rotate-180" : ""} />
        </button>
      )}
    </div>
  );
}
