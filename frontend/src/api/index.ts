import { createHttpBackend, type Backend } from "./client";
import { createMockBackend } from "./mock";
import { SCENARIOS, type ScenarioId } from "./mockScenarios";

const params = new URLSearchParams(window.location.search);

/**
 * Demo mode: `npm run dev:mock`, VITE_USE_MOCK=true, or `?demo` in the URL.
 * `?demo=partial` (or any scenario ID) preselects a scenario.
 */
export const isDemo = import.meta.env.VITE_USE_MOCK === "true" || params.has("demo");

let scenario: ScenarioId = (() => {
  const requested = params.get("demo") || params.get("scenario");
  return SCENARIOS.find((s) => s.id === requested)?.id ?? "completed";
})();

export function getScenario(): ScenarioId {
  return scenario;
}
export function setScenario(id: ScenarioId): void {
  scenario = id;
}

export const backend: Backend = isDemo
  ? createMockBackend(getScenario)
  : createHttpBackend(import.meta.env.VITE_API_BASE ?? "");
