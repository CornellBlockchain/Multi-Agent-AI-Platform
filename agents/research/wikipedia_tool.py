import asyncio
import httpx

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


async def search_wikipedia(query: str) -> dict:
    """Search Wikipedia and return useful text and source links."""
    query = query.strip()

    if not query:
        raise ValueError("The search query cannot be empty.")

        params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 3,
        "format": "json",
    }

    headers = {
        "User-Agent": (
            "MultiAgentAIPlatform/0.1 "
            "(https://github.com/yalah5084/Multi-Agent-AI-Platform)"
        )
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            WIKIPEDIA_API_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        raise RuntimeError(data["error"].get("info", "Wikipedia API error"))

    return data