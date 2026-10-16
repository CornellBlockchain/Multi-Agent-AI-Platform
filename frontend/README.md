# Team C · Dashboard Plan

[Project overview](../README.md) · [Backend plan](../backend/README.md) · [Shared interface plan](../shared/README.md)

**Status: planning only.** This folder contains this guide. No interface, assets, dependencies, build configuration, or development server is provided.

## Goal & Ownership

Build a React + Tailwind dashboard that lets a user ask a question, follow both agents, and review their combined findings. Team C should build the interface and coordinate its data contract with the backend.

## Start Here

1. Read the [planned run-state and event fields](../shared/README.md#task-and-result-fields).
2. Design the query form, two agent cards, activity timeline, and answer area.
3. Build the views and state handling independently during Meetings 1–2.
4. Connect the actual backend and agent activity in Meeting 3.
5. Check the deployed application before the joint presentation.

No setup or build commands are available yet. Add those instructions after choosing dependencies and creating the implementation.

**First working checkpoint:** Build a query form and two agent cards, then check waiting, running, and completed views with locally prepared data matching the shared fields. Confirm these views before adding polling and the full timeline.

## Dashboard TODOs

| View | Work to build | Completion criteria |
| :--- | :--- | :--- |
| **Query form** | Text input, submit action, and a useful example question. | A valid question starts a run; empty input does not. |
| **Task plan** | Show the research and developer assignments. | Users can see what each agent is responsible for. |
| **Agent cards** | Show both agents, current status, active tool, and elapsed time. | Concurrent work is visible without switching views. |
| **Activity timeline** | Group start and terminal events into one row per tool invocation. | Running calls change to completed or failed with a concise message and duration. |
| **Sources** | Display returned source titles and actual links. | Users can trace findings to retrieved material; local documents remain clearly identified. |
| **Artifacts** | Show returned code, extracted text, or data results. | Content is readable, expandable where useful, and matches agent output. |
| **Combined answer** | Render the final synthesis clearly. | The answer and citations are easy to read alongside the supporting findings. |
| **Connection and errors** | Show pending requests, unavailable services, and partial failures. | Users can understand what happened without reading server logs. |

## Planned Live Updates

Use the [proposed backend API](../shared/README.md#proposed-http-interfaces) to start a run and fetch its complete snapshot about once per second. Stop polling once the run is complete, partial, or failed.

Apply the final snapshot's events before stopping. When a new question starts, stop following the old run so delayed responses cannot replace the new question's state. Use `started_at` and event timestamps for elapsed-time displays.

Show the start message while a tool is working, then update the same row when completion or failure arrives. Group by the task and tool-call identifiers so repeated calls to the same tool remain distinct.

A completed or failed tool row should stay finished if an older start event arrives late.

Display actual events, elapsed time, source counts, and outcomes. Avoid invented progress percentages. All provider credentials should remain on the server.

## Presentation & Interaction

- Plan a dark charcoal workspace, teal research lane, blue developer lane, and restrained amber accents.
- Keep the question, both agent cards, live activity, and final answer easy to find.
- Use lightweight spinners, timers, and transitions tied to real state changes.
- Pair status colors with text/icons, support keyboard use, and keep text readable.
- Stack the agent lanes on narrow screens and keep long source titles or code from breaking the layout.

Use these design requirements when building the interface.

## States to Check

| State | Expected interface |
| :--- | :--- |
| Before a question | Ready query form and inactive agent cards. |
| Planning | Visible waiting state until assignments are available. |
| Agents running | Two active lanes and tool-start messages as they arrive. |
| Completed | Final answer, sources, artifacts, and completed activity. |
| Partial | Available findings plus a clear explanation of the failed agent. |
| Failed | An understandable error with running indicators ended for stopped work. |
| Disconnected | A connection message and the last known state; refresh when the connection returns. |

Connection loss alone should not claim that an agent has failed; use the backend's reported result when it becomes available.

## Meeting 3 Handoff

Prepare the [shared handoff items](../shared/README.md#meeting-3-handoff) and record how to build/serve the interface after it exists. With the backend, verify one complete question, a partial result, and a connection interruption. Confirm that displayed source links and artifact content come from returned results.

## Finish Checklist

- [ ] A submitted question shows two independent assignments.
- [ ] Each agent's current tool and actual status are visible.
- [ ] Tool-start messages appear before their final results.
- [ ] Completion/failure updates the matching tool call.
- [ ] Sources, artifacts, and final answer match backend data.
- [ ] Long content, narrow screens, keyboard access, and connection failures are checked.
- [ ] The integrated interface works on Akash in Meeting 3.

## Four-Meeting Milestones

| Meeting | Team C's dashboard work |
| :--- | :--- |
| **1 · Foundations** | Agree data fields; design and build the query form and agent cards independently. |
| **2 · Development** | Complete plan, timeline, source, artifact, and answer views independently. |
| **3 · Integration** | Connect the backend and both agents; verify live updates and rehearse on Akash. |
| **4 · Presentation** | Present the dashboard and run the complete application. |
