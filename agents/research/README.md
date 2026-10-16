# Team A · Research Agent

[Project overview](../../README.md) · [Shared interface plan](../../shared/README.md)

**Status: planning only.** This folder contains this guide. All tools, the agent service, Gemini access, and event reporting still need implementation.

## Goal & Ownership

Build a service that turns a research assignment into evidence, source links, and useful passages. Own the research agent and its six tools. Return findings that Team C can combine with the developer agent's results.

## Start Here

1. Read the [proposed task and result fields](../../shared/README.md#task-and-result-fields). Agree the contract with Teams B and C in Meeting 1.
2. Build a minimal agent service that accepts an assignment and returns its run/task identifiers with a structured result.
3. Implement Wikipedia and Brave search using actual queries and provider responses.
4. Connect completed tools to Gemini using the agreed shared calling interface.
5. Add the remaining tools, public activity messages, and independent checks before Meeting 3.

Arrange the implementation in a way the team can explain. Ordinary async functions and simple dictionaries are sufficient; no custom agent framework is required.

**First working checkpoint:** One question goes through Gemini to one completed search tool and returns actual source links, the assigned identifiers, and matching start/completion events. Change the question and verify that the results reflect the new input. Check this locally before adding more tools.

## Tool TODOs

All functions below are proposed responsibilities, not existing implementations.

| Tool | Input | TODO | Completion criteria |
| :--- | :--- | :--- | :--- |
| **Brave search** | Search query | Call the provider with the team's key; extract relevant results. | Return retrieved titles, snippets, and source URLs that reflect the query. |
| **Wikipedia** | Topic or query | Search for relevant pages and retrieve useful background. | Return page titles, passages or snippets, and their source URLs. |
| **Paper search** | Research keywords | Search an academic source such as arXiv. | Return paper titles, authors, abstracts, and available paper/PDF links. |
| **PDF extraction** | PDF address or selected document | Retrieve the document and extract useful text. | Return readable passages with page references and the original source. |
| **Course notes** | Question or keywords | Choose the notes to support; search their content. | Return matching passages and document names without inventing web links. |
| **Weather** | Location | Resolve the location and retrieve weather observations. | Return the location, observation time, units, and source. |

Choose the course-note collection and a PDF to check before starting those tools in Meeting 2; these materials are not included.

Use the [shared tool-result fields](../../shared/README.md#tool-results-and-live-activity) for every tool. Register a tool with Gemini after it works independently.

## Agent Behavior to Implement

- Accept the research instruction supplied by the backend.
- Let Gemini choose relevant completed tools and turn their results into a concise summary.
- Base factual findings on retrieved evidence; distinguish missing results from successful retrieval.
- Preserve source titles and URLs; include extracted text as portable artifacts where useful.
- Return the assigned identifiers, outcome, findings, and activity log.

For missing keys, provider failures, or unreadable documents, return an understandable failure or limitation. A successful empty search should say that no matches were found.

## Live Activity & Credentials

Implement the [planned event lifecycle](../../shared/README.md#tool-results-and-live-activity): announce a tool before its work begins, then report completion or failure. Send concise public messages such as “Searching Wikipedia” and “Found 3 pages.”

During Meetings 1–2, check event payloads and logs locally. Connect activity callbacks to Team C only in Meeting 3.

When creating the service, keep Gemini and search-provider keys in ignored local configuration or environment variables. Add version-control and container-build exclusions before storing local keys. No key files or exclusion rules are currently provided.

## Meeting 3 Handoff

Prepare the [shared handoff items](../../shared/README.md#meeting-3-handoff), including how to start the agent, its setting names, successful/failed task results, and matching activity events. Identify the course notes and document inputs needed to reproduce your checks. Team C should be able to call the agent without changing its internal tool code.

## Finish Checklist

- [ ] All six tools retrieve or compute actual results from their inputs.
- [ ] Different queries return relevant results rather than fixed output.
- [ ] Gemini can choose completed tools and cite the evidence it receives.
- [ ] Results follow the agreed contract and preserve assigned identifiers.
- [ ] Start events occur before tool completion; failures have clear terminal messages.
- [ ] Empty searches, missing credentials, provider errors, and invalid PDFs are checked independently.
- [ ] In Meeting 3, the containerized agent returns findings and live events to Team C.

## Four-Meeting Milestones

| Meeting | Team A's work |
| :--- | :--- |
| **1 · Foundations** | Agree interfaces; build the agent loop, Brave, and Wikipedia; configure credentials locally. |
| **2 · Development** | Complete papers, PDFs, notes, and weather; check tools and event payloads independently. |
| **3 · Integration** | Connect to Team C in Docker; verify sources, errors, and live activity on Akash. |
| **4 · Presentation** | Explain the research pipeline and show its contribution to the combined answer. |

Use branches such as `team-a/brave-search` when implementation begins. Coordinate shared-interface changes with Team C and affected consumers.
