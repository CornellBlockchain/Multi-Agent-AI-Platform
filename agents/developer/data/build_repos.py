"""Build the GitHub repos snapshot that the duckdb_query tool reads.

Collects the most-starred public repositories from a few GitHub searches
(overall, per language, and per topic), de-duplicates them, and writes
data/github_repos_<date>.parquet.

Rebuild it from agents/developer, with GITHUB_TOKEN set (or in .env):

    python data/build_repos.py

then set REPOS_SNAPSHOT in tools.py to the new date and delete the old file.
"""

import os
import time
from datetime import date, datetime
from pathlib import Path

import duckdb
import httpx
from dotenv import load_dotenv

load_dotenv()

# (search query, pages of 100). The search API allows 10 pages per query.
QUERIES = [("stars:>1000", 3)] + [
    (f"language:{lang} stars:>1000", 1)
    for lang in ["python", "javascript", "typescript", "go", "rust", "java", "c++",
                 "c", "c#", "ruby", "php", "swift", "kotlin"]
] + [
    (f"topic:{topic} stars:>100", 1)
    for topic in ["llm", "machine-learning", "deep-learning", "blockchain", "ethereum", "web3"]
]
# Authenticated search allows 30 requests a minute.
PAUSE_S = 2.5


def search(client: httpx.Client, query: str, page: int) -> list[dict]:
    r = client.get("https://api.github.com/search/repositories", params={
        "q": query, "sort": "stars", "order": "desc", "per_page": 100, "page": page,
    })
    r.raise_for_status()
    return r.json()["items"]


def parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.removesuffix("Z")) if value else None


def main() -> None:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN not set!")

    repos: dict[str, dict] = {}
    with httpx.Client(timeout=30, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }) as client:
        for query, pages in QUERIES:
            for page in range(1, pages + 1):
                items = search(client, query, page)
                print(f"{query} page {page}: {len(items)} repos")
                for x in items:
                    repos.setdefault(x["full_name"], x)
                time.sleep(PAUSE_S)

    rows = [[
        x["full_name"], x.get("description"), x.get("language"),
        x["stargazers_count"], x["forks_count"], x["open_issues_count"],
        (x.get("license") or {}).get("spdx_id"), x.get("topics") or [],
        parse_time(x.get("created_at")), parse_time(x.get("pushed_at")),
        x["archived"], x["html_url"],
    ] for x in repos.values()]

    out = Path(__file__).parent / f"github_repos_{date.today().isoformat()}.parquet"
    con = duckdb.connect()
    con.execute("""CREATE TABLE repos (
        full_name VARCHAR, description VARCHAR, language VARCHAR,
        stars INTEGER, forks INTEGER, open_issues INTEGER,
        license VARCHAR, topics VARCHAR[],
        created_at TIMESTAMP, pushed_at TIMESTAMP,
        archived BOOLEAN, html_url VARCHAR)""")
    con.executemany("INSERT INTO repos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute("COPY (SELECT * FROM repos ORDER BY stars DESC) TO ? (FORMAT parquet)", [str(out)])
    print(f"Wrote {len(rows)} repos to {out}")


if __name__ == "__main__":
    main()
