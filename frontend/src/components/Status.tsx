import type { AgentStatus, RunStatus } from "../types";
import type { CallStatus } from "../lib/timeline";
import { CheckIcon, CrossIcon, QueuedIcon, SpinnerIcon, StopIcon, WarningIcon } from "./icons";

type AnyStatus = AgentStatus | RunStatus | CallStatus | "idle";

const LABELS: Record<AnyStatus, string> = {
  idle: "Waiting for a question",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Partial",
  failed: "Failed",
  stopped: "Stopped",
};

/**
 * Status glyph. Colour is never the only signal: every glyph has a distinct
 * shape and is paired with a text label (visible or screen-reader only).
 */
export function StatusIcon({ status, size = 16, className = "" }: { status: AnyStatus; size?: number; className?: string }) {
  switch (status) {
    case "running":
      return <SpinnerIcon size={size} className={`text-[var(--lane,var(--color-amber))] ${className}`} />;
    case "completed":
      return <CheckIcon size={size} className={`text-[var(--lane-ink,var(--color-ink))] ${className}`} />;
    case "failed":
      return <CrossIcon size={size} className={`text-danger ${className}`} />;
    case "partial":
      return <WarningIcon size={size} className={`text-amber ${className}`} />;
    case "stopped":
      return <StopIcon size={size} className={`text-amber ${className}`} />;
    default:
      return <QueuedIcon size={size} className={`text-ink-faint ${className}`} />;
  }
}

export function StatusLabel({ status, className = "" }: { status: AnyStatus; className?: string }) {
  const tone =
    status === "failed"
      ? "text-danger-ink"
      : status === "partial" || status === "stopped"
        ? "text-amber-ink"
        : status === "idle" || status === "queued"
          ? "text-ink-faint"
          : "text-ink";
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-medium ${tone} ${className}`}>
      <StatusIcon status={status} size={15} />
      {LABELS[status]}
    </span>
  );
}

export function statusText(status: AnyStatus): string {
  return LABELS[status];
}
