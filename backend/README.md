# Team C · Backend & Integration Plan

[Project overview](../README.md) · [Shared interface plan](../shared/README.md) · [Dashboard plan](../frontend/README.md)

**Status: planning only.** This folder contains this guide. No backend, routes, planner, storage, deployment configuration, or launch commands are provided.

## Goal & Ownership

Build the coordinator for one question: plan two assignments, call both agents concurrently, collect live activity, and synthesize their findings. Team C also owns the dashboard and integrated deployment.

The planned backend should use FastAPI and serve the built dashboard alongside its API. Keep run history in a plain in-memory dictionary and use one backend process; document that restarting will clear history.

## Start Here

1. Agree the [shared task, result, and event fields](../shared/README.md#task-and-result-fields) with Teams A and B in Meeting 1.
2. Build query acceptance and run-state retrieval before adding model calls.
3. Implement Gemini planning, concurrent agent requests, and synthesis as separate ordinary functions.
4. Develop the [dashboard](../frontend/README.md) against the agreed data shapes.
5. Connect team services, containerize the application, and deploy on Akash in Meeting 3.

During Meetings 1–2, use independent local checks. Do not depend on another team's running implementation before Meeting 3.

**First working checkpoint:** Submit a nonempty question, receive a run identifier, and retrieve the same question with two queued agent states and distinct task identifiers. Check this before adding Gemini or agent requests.

## Implementation TODOs

| Component | Work to build | Completion criteria |
| :--- | :--- | :--- |
| **Run API** | Accept a query, create identifiers, and store run state. | Return a run identifier promptly and make its current state retrievable. |
| **Gemini planner** | Turn a question into research and developer instructions. | Both assignments are specific and self-contained. |
| **Concurrent requests** | Call both agents at the same time, with request timeouts. | One slow or failed agent does not prevent collecting the other agent's result. |
| **Activity collection** | Receive events and attach them to the matching run/task. | Tool starts are visible before final results; repeated event IDs do not create duplicates. |
| **Gemini synthesis** | Combine returned summaries, sources, and artifacts. | The answer cites available evidence and explains missing findings. |
| **Dashboard serving** | Serve the built interface with the API. | The browser can submit a query and follow the full run. |
| **Deployment** | Containerize the services and configure their addresses/credentials. | The integrated application runs on Akash and can be presented from its actual URL. |

Use ordinary async functions for the workflow. A single concurrent wait, such as Python's `asyncio.gather()`, is sufficient for the two agent requests.

## Planned Request Flow

1. Accept the question and create a queued run.
2. Ask Gemini for independent research and developer assignments.
3. Mark both agents running and send the requests concurrently.
4. Receive activity callbacks while the agent requests remain in progress.
5. Collect each agent's final result and merge any missing events by identifier.
6. Ask Gemini to combine the available findings.
7. Mark the run completed, partial, or failed and make the final state available to the dashboard.

The planned routes and payload fields are listed in the [shared HTTP specification](../shared/README.md#proposed-http-interfaces). They are not implemented.

## Independent Checks · Meetings 1–2

- [ ] A valid query creates a retrievable run; an empty query and an unknown run return clear errors.
- [ ] Local test responders show that both agent requests start before either finishes.
- [ ] One failed or timed-out responder preserves the other's findings and ends unfinished tool indicators.
- [ ] Repeated event IDs are ignored, and final-result events fill gaps in the callback log.
- [ ] Planning and synthesis failures end the run clearly without losing available agent findings.

These checks should use Team C's own test responders until Meeting 3. Agree the [shared handoff items](../shared/README.md#meeting-3-handoff) with Teams A and B before integration.

## State & Failure Behavior

| Situation | Planned outcome |
| :--- | :--- |
| Planning succeeds | Move from planning to agent execution. |
| Both agents succeed | Synthesize both results and complete the run. |
| One agent fails | Preserve the successful result and produce a clearly labeled partial answer. |
| Both agents fail | Finish with an error rather than an invented answer. |
| Synthesis fails | Preserve agent findings and explain that the final answer could not be generated. |
| An agent disconnects during a tool | End its running indicators with a failure message after the request timeout. |

Use `queued`, `running`, `completed`, `partial`, and `failed` for overall status as appropriate. Use `planning`, `agents`, `synthesis`, and `done` for workflow phases. The dashboard should fetch a full snapshot about once per second.

## Integration & Deployment · Meeting 3

- [ ] Merge the team implementations and confirm matching contracts.
- [ ] Configure agent addresses, model settings, and server-side credentials.
- [ ] Build and run each service in its own container.
- [ ] Connect the backend, both agents, and dashboard.
- [ ] Verify concurrent requests, start/completion/failure events, sources, and artifacts.
- [ ] Deploy on Akash and check the actual public application.
- [ ] Record working launch instructions and rehearse one complete question.

Choose one presentation question with the teams and confirm which sources and artifacts are expected. Check both the successful path and an agent-failure case before the presentation; use actual provider/tool outputs for the full application walkthrough.

No container definitions, deployment files, or hosted application currently exist in this repository.

## Four-Meeting Roadmap

| Meeting | Team C's backend work |
| :--- | :--- |
| **1 · Foundations** | Agree contracts; build initial query/run routes and independent checks. |
| **2 · Development** | Build planning, concurrent requests, synthesis, state tracking, and activity collection. |
| **3 · Integration** | Connect both agents and dashboard; verify real outputs; deploy on Akash; rehearse. |
| **4 · Presentation** | Explain the architecture and run the complete application. |

## Definition of Success

- [ ] One question produces two independent assignments.
- [ ] Both agents run concurrently and return actual findings.
- [ ] Tool activity appears while operations are still running.
- [ ] Source links and text/code artifacts reach the dashboard.
- [ ] Gemini produces a combined answer grounded in the returned evidence.
- [ ] A failed tool or agent produces an understandable outcome.
- [ ] The complete application runs in Docker on Akash.

Team C should coordinate shared-interface changes and integration. Use branches such as `team-c/orchestration` or `team-c/dashboard` when implementation begins. The [main README](../README.md#meeting-4--joint-presentation) contains the presentation agenda.
