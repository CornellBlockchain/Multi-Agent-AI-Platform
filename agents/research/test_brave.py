
import asyncio
import os
from unittest.mock import patch
from tools.brave import brave_search


async def main():
    queries = [
        "What is artificial intelligence?",
        "How does blockchain technology work?",
        "What causes earthquakes?"
    ]

    for query in queries:
        print(f"\nSEARCHING: {query}")
        print("-" * 50)

        try:
            result = await brave_search(query)

            print("MESSAGE:", result["message"])
            print("SOURCES:")

            for source in result["sources"]:
                print(f"  Title: {source['title']}")
                print(f"  URL: {source['url']}")
                print()

        except Exception as e:
            print(f"ERROR: {e}")

    # ADD THIS HERE (outside the for loop)
    await test_errors()


async def test_errors():
    # Test 1: Empty query
    try:
        await brave_search("")
        print("FAIL: Empty query was accepted")
    except ValueError:
        print("PASS: Empty query rejected")

    # Test 2: Missing API key
    with patch.dict(os.environ, {"BRAVE_API_KEY": ""}):
        try:
            await brave_search("artificial intelligence")
            print("FAIL: Missing API key was accepted")
        except RuntimeError:
            print("PASS: Missing API key detected")


if __name__ == "__main__":
    asyncio.run(main())
