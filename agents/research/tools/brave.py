
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


async def brave_search(query: str) -> dict:
    """Search the web using Brave Search API."""

    # 1. Check the search query
    if not query.strip():
        raise ValueError("Search query cannot be empty")

    # 2. Get API key from environment
    api_key = os.getenv("BRAVE_API_KEY")

    if not api_key:
        raise RuntimeError("BRAVE_API_KEY is missing")

    # 3. Set up the API request
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }

    params = {
        "q": query,
        "count": 5,
        "text_decorations": "false",
    }

    # 4. Call Brave Search
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            BRAVE_URL,
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()

    # 5. Extract search results
    results = (data.get("web") or {}).get("results", [])

    sources = []
    passages = []

    for result in results:
        title = result.get("title", "")
        url = result.get("url", "")
        description = result.get("description") or ""

        if not url.startswith(("https://", "http://")):
            continue

        sources.append({
            "title": title,
            "url": url,
        })

        passages.append(
            f"{title}\n{url}\n{description}"
        )

    # 6. Return the shared tool-result format
    count = len(sources)

    return {
        "message": f"Found {count} web results",
        "summary": (
            f"No results found for '{query}'"
            if count == 0
            else f"Found {count} relevant web pages for '{query}'."
        ),
        "sources": sources,
        "artifacts": (
            [{
                "name": "Brave search passages",
                "content": "\n\n".join(passages),
            }]
            if passages else []
        ),
    }
