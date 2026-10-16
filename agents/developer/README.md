# Team B · Developer Agent

[Project overview](../../README.md) · [Shared interface plan](../../shared/README.md)

**Status: planning only.** This folder contains this guide. All tools, the agent service, Gemini access, and event reporting still need implementation.

## Goal & Ownership

Build a service that finds repositories, reads technical material, inspects code, and returns useful execution or data results. Own the developer agent and its six tools. Team C will combine its findings with the research agent's evidence.

## Start Here

1. Read the [proposed task and result fields](../../shared/README.md#task-and-result-fields). Agree the contract with Teams A and C in Meeting 1.
2. Build a minimal agent service that accepts an assignment and returns its run/task identifiers with a structured result.
3. Implement GitHub search with actual queries and provider responses.
4. Connect completed tools to Gemini using the agreed shared calling interface.
5. Complete repository analysis, browsing, execution, and data queries; check them independently before Meeting 3.

Keep the implementation understandable: ordinary async functions, clear tool descriptions, and simple result dictionaries.

**First working checkpoint:** One question goes through Gemini to GitHub search and returns actual repository links, the assigned identifiers, and matching start/completion events. Change the query and verify that the results reflect the new input. Check this locally before adding more tools.

## Tool TODOs

All functions below are proposed responsibilities, not existing implementations.

| Tool | Input | TODO | Completion criteria |
| :--- | :--- | :--- | :--- |
| **GitHub search** | Repository query | Search repository metadata using the provider API. | Return relevant names, descriptions, and repository URLs. |
| **Playwright browsing** | Page address | Retrieve a page with async browser automation and extract readable content. | Return the actual page text, title, and final source URL. |
| **Python execution** | Python program | Run it in a separate container with an execution timeout. | Return actual stdout, stderr, exit status, and timeout information. |
| **C++ execution** | C++ program | Compile and run it in a separate container with time limits. | Return compiler output, runtime output, exit status, and measured duration. |
| **DuckDB** | Read-only query | Choose the dataset, load it, and query it. | Return column names and a bounded row list that supports the finding. |
| **Repository analysis** | Repository identifier | Retrieve the README, file tree, and relevant files. | Explain inspected code with references to repository paths or URLs. |

Choose a small dataset for DuckDB and simple successful/failing Python and C++ programs before starting those tools in Meeting 2. No datasets or execution environment are included.

Use the [shared tool-result fields](../../shared/README.md#tool-results-and-live-activity) for every tool. Register a tool with Gemini after it works independently.

## Agent Behavior to Implement

- Accept the developer instruction supplied by the backend.
- Let Gemini choose relevant completed tools and summarize their results.
- Distinguish repository discovery from code inspection and actual execution.
- Cite inspected repositories/files; return code and execution output as portable text artifacts.
- Return the assigned identifiers, outcome, findings, and activity log.

Handle empty searches, unavailable pages, compilation errors, and execution timeouts clearly. Do not report successful execution or performance measurements without corresponding tool output.

## Live Activity & Credentials

Implement the [planned event lifecycle](../../shared/README.md#tool-results-and-live-activity): announce a tool before its work begins, then report completion or failure. Useful messages include “Searching GitHub,” “Compiling C++,” and “Execution completed.”

During Meetings 1–2, check event payloads and logs locally. Connect activity callbacks to Team C only in Meeting 3.

When creating the service, keep Gemini and provider keys in ignored local configuration or environment variables. Add version-control and container-build exclusions before storing local keys. No key files or exclusion rules are currently provided.

## Meeting 3 Handoff

Prepare the [shared handoff items](../../shared/README.md#meeting-3-handoff), including how to start the agent, its setting names, successful/failed task results, and matching activity events. Include instructions for the selected dataset and execution containers. Team C should be able to call the agent without changing its internal tool code.

## Finish Checklist

- [ ] All six tools operate on actual inputs and return actual results.
- [ ] Different searches return relevant repositories and inspected sources.
- [ ] Code executes in isolation with clear compiler/runtime errors and timeouts.
- [ ] Gemini can choose completed tools and describe what was actually inspected or run.
- [ ] Results follow the agreed contract and preserve assigned identifiers.
- [ ] Start events occur before tool completion; failures have clear terminal messages.
- [ ] In Meeting 3, the containerized agent returns findings and live events to Team C.

## Four-Meeting Milestones

| Meeting | Team B's work |
| :--- | :--- |
| **1 · Foundations** | Agree interfaces; build the agent loop and GitHub search; configure credentials locally. |
| **2 · Development** | Complete browsing, Python/C++, DuckDB, and repository analysis independently. |
| **3 · Integration** | Connect to Team C in Docker; verify artifacts, errors, and live activity on Akash. |
| **4 · Presentation** | Explain the developer pipeline and show its contribution to the combined answer. |

Use branches such as `team-b/repository-analysis` when implementation begins. Coordinate shared-interface changes with Team C and affected consumers.
