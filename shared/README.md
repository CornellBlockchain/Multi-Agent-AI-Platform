# Shared Interface Plan

[Project overview](../README.md) · [Research](../agents/research/README.md) · [Developer](../agents/developer/README.md) · [Backend](../backend/README.md) · [Dashboard](../frontend/README.md)

**Status: specification only.** No shared code, schemas, helpers, examples, configuration, or services are provided. The tables below are proposed agreements for Meeting 1, to be implemented by the teams.

## Meeting 1 · Agreements

Team C should coordinate these decisions with Teams A and B before independent development:

- [ ] Confirm task, result, source, artifact, and event fields.
- [ ] Confirm agent names: `research` and `developer`.
- [ ] Agree one shared Gemini calling interface and who will implement it.
- [ ] Confirm how local credentials will be configured and excluded from version control.
- [ ] Agree service addresses and callback authentication for Meeting 3.
- [ ] Write down contract changes here before affected teams implement them.

Agreeing interfaces is preparation. Connecting independently built services remains a Meeting 3 task.

## Task and Result Fields

These are planned payload fields, not existing models or endpoints.

| Payload | Proposed fields | Required behavior |
| :--- | :--- | :--- |
| **Agent task** | `run_id`, `task_id`, `instruction`, optional `context` | Identify the assignment and give enough information to work independently. |
| **Agent result** | `run_id`, `task_id`, `agent`, `status`, `summary`, `sources`, `artifacts`, `events`, optional `error` | Echo the assigned identifiers and return findings or an understandable failure. |
| **Agent state** | `task_id`, `status`, `result` | Track one assigned task; keep `result` null until the agent finishes. |
| **Source** | `title`, `url` | Identify a retrieved source; use a null URL for local documents. |
| **Artifact** | `name`, `content` | Return portable text, such as code, extracted passages, or query output. |
| **Plan** | `research`, `developer` | Supply two self-contained assignments that can run concurrently. |
| **Run state** | `run_id`, `query`, `started_at`, `status`, `phase`, `plan`, `agents`, `events`, `final_answer`, optional `error` | Give the dashboard the complete current view of a question and its execution. |

Use `completed` or `failed` for an agent's final result. A failed result should explain the limitation. Empty source/artifact lists are valid when a search finds no matches.

Confirm these field conventions before coding:

- Identifiers and text fields are strings. The backend creates one `run_id` per question and a separate `task_id` for each agent; agents must echo them.
- `agents` maps `research` and `developer` to their agent states. Agent-state status is `queued`, `running`, `completed`, or `failed`.
- `sources`, `artifacts`, and `events` are lists. `plan`, `result`, and `final_answer` may be null until available; `error` is a message or null.
- `started_at` and event `timestamp` use UTC ISO 8601 strings. `duration_ms` is a nonnegative number. Source URLs use HTTP/HTTPS or null for a local document.

Return content the receiving service can display. A path inside one agent's container is not a portable artifact.

## Proposed HTTP Interfaces

All routes below need implementation. Teams should confirm request fields and failure responses in Meeting 1.

| Owner | Proposed route | Planned behavior |
| :--- | :--- | :--- |
| Both agents | `GET /health` | Report that the service can respond. |
| Both agents | `POST /execute` | Accept an agent task and return its final result. |
| Backend | `GET /api/health` | Provide dashboard connection status. |
| Backend | `POST /api/runs` | Accept a `query` string; return HTTP `202` with `run_id` while work continues. |
| Backend | `GET /api/runs/{run_id}` | Return the full run state and activity list. |
| Backend · internal | `POST /internal/runs/{run_id}/events` | Receive an event while an agent is working. |

The two agents should share the same HTTP contract. Their internal tool names may differ.

Propose HTTP `200` for successful reads, agent results, and event acknowledgments; `404` for an unknown run; and `422` for malformed input or an empty query. An agent's execution failure should return a structured failed result so Team C can preserve its event log.

## Shared Gemini Calling Convention

Create one lightweight model-access helper with the same name and input/output conventions across Python services. It should read the current service's key/model settings, make an async model request with a timeout, and return the model response.

**Proposed helper contract:** name it `call_gemini`, accept `contents` and optional `config`, and return the Gemini SDK response so each team can access text, structured planning output, or tool-call results. Team C should coordinate the helper's implementation and availability before teams depend on it. This is a proposed interface; no helper exists yet.

| Owner | Configuration to supply |
| :--- | :--- |
| Team A | Research instructions and completed research tools. |
| Team B | Developer instructions and completed developer tools. |
| Team C | Structured planning instructions and final-answer synthesis instructions. |

Each team should keep its own prompts and tool implementation. Coordinate changes to the shared calling interface rather than creating incompatible model clients.

## Tool Results and Live Activity

Every tool should return the following information after its work finishes:

| Field | Planned contents |
| :--- | :--- |
| `message` | Short public outcome, such as “Found 3 repositories”. |
| `summary` | Findings derived from the actual input and retrieved/computed result. |
| `sources` | Retrieved titles and URLs, or named local documents. |
| `artifacts` | Named text outputs useful to the answer or dashboard. |

A return value arrives after the work finishes. To show activity during execution, implement a separate event before starting the operation.

| Stage | Event type | Example public message |
| :--- | :--- | :--- |
| Before the operation | `tool.started` | “Searching Wikipedia” |
| Successful completion | `tool.completed` | “Found 3 pages” |
| Failure or interruption | `tool.failed` | “Wikipedia search failed” |

Each event should identify `event_id`, `run_id`, `task_id`, `agent`, `tool_call_id`, `tool`, `type`, `timestamp`, and `message`. Completion/failure events may include `duration_ms` and small result counts.

Use the same call identifier for the start and terminal event. Print public events promptly and send callbacks asynchronously. Do not include provider keys, raw credentials, or private model reasoning in messages.

The agent should create a new `tool_call_id` for each invocation and a distinct `event_id` for each event. Every started call should receive exactly one completion or failure event, including unsuccessful requests. Reusing a tool name must not reuse the invocation's identifier.

The planned backend should collect callbacks and ignore repeated event IDs. Returning the agent's event list with the final result can recover callbacks that were missed. The dashboard can then group events into one row per tool invocation.

## Credentials to Configure

Each team must create its own local environment configuration when implementation begins. None is currently included.

| Service | Planned credentials/settings |
| :--- | :--- |
| Research | Gemini key/model, Brave key, and settings required by additional tools. |
| Developer | Gemini key/model, GitHub token if used, and execution/data settings. |
| Backend | Gemini key/model, both agent addresses, request timeouts, and callback settings. |

Teams may use different Gemini keys. Agree a common server-side callback token if callbacks require authentication. Create version-control and container-build exclusions before storing keys, and document setting names using empty values rather than real credentials. Provider keys must remain outside the browser.

## Independent Checks & Integration

During Meetings 1–2, each team should check its component against these field definitions using its own local tests. Verify identifiers, real tool inputs/outputs, event ordering, empty results, and failure handling.

In Meeting 3, connect the services and verify that start events reach the dashboard before agent results. Check source/artifact rendering, concurrent execution, partial failures, and the combined answer.

Use team-prefixed branches when implementation begins. Team C should coordinate shared-contract changes with affected teams. Add actual setup and launch instructions only after the implementation and configuration exist.

## Meeting 3 Handoff

Before connecting services, each team should prepare:

- [ ] A reviewed implementation branch and clear ownership of any shared changes.
- [ ] Working start/container instructions and required setting names, without actual keys.
- [ ] A successful request/result and a failed request/result checked against this specification.
- [ ] Start and terminal event examples with matching run, task, and tool-call identifiers.
- [ ] The local data or documents needed by its tools, with instructions for making them available.

Team C should confirm service addresses and callback settings, then run one complete question and one agent-failure case. The launch instructions and example payloads above are deliverables to create; none are currently supplied.
