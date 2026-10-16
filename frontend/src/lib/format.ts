/** "0.8 s", "12 s", "1 min 04 s". Never negative (clock skew is clamped). */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  const v = Math.max(0, ms);
  if (v < 10_000) return `${(v / 1000).toFixed(1)} s`;
  const total = Math.floor(v / 1000);
  if (total < 60) return `${total} s`;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m} min ${String(s).padStart(2, "0")} s`;
}

/** Elapsed timer style: "0:07", "1:23", "12:05". */
export function formatClock(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "0:00";
  const total = Math.floor(Math.max(0, ms) / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function formatTimeOfDay(epochMs: number): string {
  return new Date(epochMs).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

/** Display names for the tools listed in the agents' READMEs. */
const TOOL_LABELS: Record<string, string> = {
  brave_search: "Brave search",
  wikipedia: "Wikipedia",
  paper_search: "Paper search",
  pdf_extraction: "PDF extraction",
  course_notes: "Course notes",
  weather: "Weather",
  github_search: "GitHub search",
  playwright_browse: "Web page",
  browse: "Web page",
  python_execution: "Python",
  cpp_execution: "C++",
  duckdb: "DuckDB",
  repo_analysis: "Repository analysis",
};

/** Known tools get their display name; others: "some_tool" → "Some tool". */
export function humanizeTool(tool: string): string {
  const known = TOOL_LABELS[tool.toLowerCase()];
  if (known) return known;
  const words = tool.replace(/[_-]+/g, " ").trim();
  if (!words) return tool;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
