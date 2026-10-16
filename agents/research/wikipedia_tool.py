import asyncio
import html
import re

import httpx


WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"


async def search_wikipedia(query: str, limit: int = 3) -> dict:
    """Search Wikipedia and return snippets and source links."""
    query = query.strip()

    if not query:
        raise ValueError("The search query cannot be empty.")

    if not 1 <= limit <= 10:
        raise ValueError("Choose between 1 and 10 sources.")

    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
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
        raise RuntimeError(
            data["error"].get("info", "Wikipedia API error")
        )

    pages = data["query"]["search"]

    sources = []
    passages = []

    for page in pages:
        title = page["title"]

        snippet = re.sub(r"<[^>]+>", "", page["snippet"])
        snippet = html.unescape(snippet)

        url = f"https://en.wikipedia.org/?curid={page['pageid']}"

        sources.append({
            "title": title,
            "url": url,
        })

        passages.append(f"{title}\n{snippet}")

    summary = "\n\n".join(passages)

    return {
        "message": f"Found {len(pages)} Wikipedia pages.",
        "summary": summary or "No matching Wikipedia pages found.",
        "sources": sources,
        "artifacts": [],
    }


if __name__ == "__main__":
    query = input("What would you like to search on Wikipedia? ")

    try:
        limit = int(input("How many sources would you like? (1–10): "))
    except ValueError:
        print("Please enter a whole number between 1 and 10.")
    else:
        try:
            result = asyncio.run(search_wikipedia(query, limit))
        except ValueError as error:
            print(f"Invalid input: {error}")
        except httpx.TimeoutException:
            print("Wikipedia took too long to respond. Please try again.")
        except httpx.HTTPError as error:
            print(f"Could not retrieve Wikipedia results: {error}")
        except RuntimeError as error:
            print(f"Wikipedia search failed: {error}")
        else:
            print()
            print(result["message"])
            print()

            if not result["sources"]:
                print(result["summary"])
            else:
                passages = result["summary"].split("\n\n")

                for number, (source, passage) in enumerate(
                    zip(result["sources"], passages),
                    start=1,
                ):
                    print(f"{number}. {passage}")
                    print("Source:", source["url"])
                    print()