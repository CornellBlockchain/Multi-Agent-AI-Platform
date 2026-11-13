# PAPER SEARCH TOOL
# Takes research keywords (like "zero knowledge proofs") and returns matching
# academic papers from arXiv, a free site for research papers. No API key needed.

# This file has 3 parts, same as weather_tool.py:
#   1. search_papers()           -> does the actual arXiv search
#   2. run_papers_with_events()  -> wraps it with "started/completed/failed" updates
#   3. if __name__ == "__main__" -> tests you can run from the terminal

import asyncio                      # lets Python wait for websites without freezing
import json                         # used at the bottom to print events nicely
import xml.etree.ElementTree as ET  # reads XML (arXiv answers in XML, not JSON)
import httpx                        # the library that sends requests to websites

from uuid import uuid4              # makes random unique IDs

# Loads create_tool_event from events.py (same as the weather tool)
if __package__:
    from .events import create_tool_event
else:
    from events import create_tool_event


# The arXiv search web address
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# arXiv puts this prefix in front of every tag name in its XML.
# Without it, find() can't find anything. Think of it as a "last name"
# every tag has: "title" is really "{http://www.w3.org/2005/Atom}title".
ATOM = "{http://www.w3.org/2005/Atom}"


# PART 1: THE ACTUAL ARXIV SEARCH
# Takes keywords and how many papers you want, gives back a dictionary.
async def search_papers(query: str, limit: int = 5) -> dict:
    """Search arXiv and return paper titles, authors, abstracts and links."""

    # Remove extra spaces from the start and end
    query = query.strip()

    # Nothing typed -> stop with a clear error
    if not query:
        raise ValueError("The search query cannot be empty.")

    # Keep the number of papers reasonable
    if not 1 <= limit <= 10:
        raise ValueError("Choose between 1 and 10 papers.")

    params = {
        # Turns "zero knowledge proofs" into
        #   "all:zero AND all:knowledge AND all:proofs"
        # so every word has to appear. "all:" means "search title, abstract, authors, etc."
        "search_query": " AND ".join(f"all:{word}" for word in query.split()),
        "max_results": limit,       # how many papers to return
        "sortBy": "relevance",      # best matches first
    }

    # Send the request. follow_redirects=True means "if arXiv points us
    # to a different address, go there automatically."
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(ARXIV_API_URL, params=params)
        response.raise_for_status()     # stop if the website errored

    # Turn the XML text into something Python can search through.
    # "root" is the outermost box that holds everything.
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        raise RuntimeError("arXiv returned a response that could not be read.")

    sources = []    # titles + links (become citations in the final answer)
    passages = []   # short readable descriptions (become the summary)
    artifacts = []  # full details for each paper (extra info for the dashboard)

    # Each paper is inside its own <entry> box. findall() grabs ALL of them.
    for entry in root.findall(f"{ATOM}entry"):

        # find() grabs the FIRST box with that label, .text gets what's inside.
        # split/join removes the line breaks arXiv puts inside long titles.
        title = " ".join(entry.find(f"{ATOM}title").text.split())
        abstract = " ".join(entry.find(f"{ATOM}summary").text.split())

        # A paper can have many authors, so findall() again.
        # Each <author> box has a <name> box inside it.
        authors = [a.find(f"{ATOM}name").text for a in entry.findall(f"{ATOM}author")]

        # The <id> box holds the paper's page link
        url = entry.find(f"{ATOM}id").text

        # Each paper has several <link> boxes. The PDF one has title="pdf".
        pdf_url = None
        for link in entry.findall(f"{ATOM}link"):
            if link.get("title") == "pdf":      # .get() reads a setting on the tag
                pdf_url = link.get("href")      # href = the actual web address

        # Show at most 3 authors, then "et al." (academic for "and others")
        author_text = ", ".join(authors[:3])
        if len(authors) > 3:
            author_text += " et al."

        # Abstracts are long, so cut the summary version to 300 characters
        short_abstract = abstract[:300]
        if len(abstract) > 300:
            short_abstract += "..."

        sources.append({
            "title": title,
            "url": url,
        })

        passages.append(f"{title}\n{author_text}\n{short_abstract}")

        # The full version: all authors, PDF link, and the whole abstract
        artifacts.append({
            "name": f"arXiv: {title}",
            "content": (
                f"{title}\n"
                f"Authors: {', '.join(authors)}\n"
                f"PDF: {pdf_url}\n\n"
                f"{abstract}"
            ),
        })

    # Put the short descriptions together, with a blank line between papers
    summary = "\n\n".join(passages)

    # Return the 4 keys EVERY tool must return.
    # If no papers matched, passages is empty, so summary falls back to the "or" text.
    return {
        "message": f"Found {len(sources)} papers.",
        "summary": summary or "No matching arXiv papers found.",
        "sources": sources,
        "artifacts": artifacts,
    }


# PART 2: THE "PACKAGE TRACKING" WRAPPER
# Same as the weather tool: send "started" before, then "completed" or "failed".
async def run_papers_with_events(
    query: str,      # the keywords to search
    limit: int,      # how many papers
    run_id: str,     # ID of the overall question (from the backend)
    task_id: str,    # ID of the research agent's job (from the backend)
    events: list,    # list we add every update to
) -> dict:

    # One shared ID so "started" and "completed" are paired on the dashboard
    tool_call_id = str(uuid4())

    # Helper: build one update with events.py and save it
    def emit(event_type: str, message: str):
        event = create_tool_event(
            run_id=run_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            event_type=event_type,
            message=message,
            tool="paper_search",            # tells the dashboard which tool this is
        )
        events.append(event)
        print(f"[{event_type}] {message}", flush=True)

    # Update #1: about to start
    emit("tool.started", "Searching arXiv")

    try:
        result = await search_papers(query, limit)
    except asyncio.CancelledError:
        emit("tool.failed", "arXiv search was cancelled")
        raise
    except Exception:
        emit("tool.failed", "arXiv search failed")
        raise
    else:
        # Update #2: finished successfully
        emit("tool.completed", result["message"])
        return result


# PART 3: Testing code you can run from the terminal. It runs 3 tests:
# Only runs when you type "python3 paper_search_tool.py" in the terminal.
if __name__ == "__main__":

    # TEST 1: real topic -> started, then completed, with papers
    print("Test 1: real topic")
    events = []
    result = asyncio.run(
        run_papers_with_events("zero knowledge proofs", 3, "local-run", "local-task", events)
    )
    print(result["summary"])
    print(result["sources"])
    print(json.dumps(events, indent=2))

    # TEST 2: nonsense topic -> started, then completed, with "No matching"
    print("\nTest 2: nonsense topic")
    events = []
    result = asyncio.run(
        run_papers_with_events("xqzvbnmkqq", 3, "local-run", "local-task", events)
    )
    print(result["summary"])
    print(json.dumps(events, indent=2))

    # TEST 3: empty query -> started, then failed (raises an error)
    print("\nTest 3: empty query")
    events = []
    try:
        asyncio.run(
            run_papers_with_events("", 3, "local-run", "local-task", events)
        )
    except ValueError as error:
        print(f"Got the expected error: {error}")
    print(json.dumps(events, indent=2))