"""Course Notes Search: keyword search over local .txt / .md files.

Ranking method (simple and explainable):
  1. Every note is split into passages (paragraphs; long ones are split further).
     Markdown headings are remembered and attached to the passages under them.
  2. The query and each passage are lowercased and split into words; common
     stop words are dropped.
  3. Each query word is weighted by rarity (IDF): words that appear in few
     passages count more than words that appear everywhere.
  4. Passage score = sum over query words of (1 + log(count in passage)) * IDF,
     plus a small bonus if the word is in the passage's heading or file name.
  5. Passages with score 0 are discarded. Of the rest, only those scoring at least
     MIN_RELATIVE_SCORE (25%) of the best passage are kept, up to MAX_RESULTS.

No embeddings, no network, no LLM. Only files inside the notes directory are read.
"""
import asyncio
import math
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from events import run_tool_with_events

load_dotenv()

NOTES_DIR_ENV = "COURSE_NOTES_DIR"
SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown"}
MAX_RESULTS = 5
MIN_RELATIVE_SCORE = 0.25  # keep passages scoring >= 25% of the top passage
MAX_PASSAGE_CHARS = 800
MAX_FILE_BYTES = 5 * 1024 * 1024  # skip unreasonably large files
HEADING_BONUS = 0.5

STOP_WORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i if in into is it "
    "its me my of on or our so than that the their them then there these they this to "
    "was we were what when where which who why will with you your about explain tell".split()
)
WORD_RE = re.compile(r"[a-z0-9]+")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")


class CourseNotesError(Exception):
    """Raised when the notes directory is not configured or cannot be used."""


def tokenize(text: str) -> list:
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOP_WORDS]


def _split_long(text: str) -> list:
    """Split an over-long paragraph on sentence/line boundaries into <= MAX_PASSAGE_CHARS pieces."""
    if len(text) <= MAX_PASSAGE_CHARS:
        return [text]
    pieces, current = [], ""
    for part in re.split(r"(?<=[.!?])\s+|\n", text):
        if current and len(current) + len(part) + 1 > MAX_PASSAGE_CHARS:
            pieces.append(current)
            current = ""
        while len(part) > MAX_PASSAGE_CHARS:  # a single huge "sentence"
            pieces.append(part[:MAX_PASSAGE_CHARS])
            part = part[MAX_PASSAGE_CHARS:]
        current = f"{current} {part}".strip()
    if current:
        pieces.append(current)
    return pieces


def split_passages(text: str) -> list:
    """Return [(heading_or_None, passage_text)] for one document."""
    passages, heading, buffer = [], None, []

    def flush():
        paragraph = "\n".join(buffer).strip()
        buffer.clear()
        if paragraph:
            passages.extend((heading, p) for p in _split_long(paragraph))

    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            flush()
            heading = match.group(1) or None
            # A heading line is context, but also searchable on its own via the heading bonus.
        elif not line.strip():
            flush()
        else:
            buffer.append(line.rstrip())
    flush()
    return passages


def _resolve_notes_dir(notes_dir) -> Path:
    raw = notes_dir if notes_dir is not None else os.getenv(NOTES_DIR_ENV)
    if not raw or not str(raw).strip():
        raise CourseNotesError(f"{NOTES_DIR_ENV} is not set")
    root = Path(str(raw)).expanduser()
    if not root.is_dir():
        raise CourseNotesError("Course notes directory was not found")
    return root.resolve()


def _find_files(root: Path) -> list:
    """Supported files under root, never following links that leave root."""
    files = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            real = path.resolve()
            if real != root and root not in real.parents:
                continue  # symlink pointing outside the notes directory
            if real.is_file():
                files.append((path.relative_to(root).as_posix(), real))
        except OSError:
            continue
    return files


def _load_passages(root: Path):
    """Read all notes. Returns (passages, files_read, files_skipped)."""
    passages, read, skipped = [], 0, 0
    for name, path in _find_files(root):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        read += 1
        for heading, body in split_passages(text):
            passages.append({"document": name, "heading": heading, "text": body})
    return passages, read, skipped


def rank_passages(query_terms: list, passages: list) -> list:
    """Score passages (see module docstring) and return those with score > 0, best first."""
    if not passages:
        return []
    doc_tokens = [set(tokenize(p["text"])) for p in passages]
    counts = [{} for _ in passages]
    for i, p in enumerate(passages):
        for w in tokenize(p["text"]):
            counts[i][w] = counts[i].get(w, 0) + 1
    n = len(passages)
    scored = []
    for i, p in enumerate(passages):
        context = set(tokenize((p["heading"] or "") + " " + Path(p["document"]).stem.replace("_", " ")))
        score = 0.0
        for term in set(query_terms):
            tf = counts[i].get(term, 0)
            in_context = term in context
            if not tf and not in_context:
                continue
            df = sum(1 for tokens in doc_tokens if term in tokens)
            idf = math.log(1 + n / (1 + df))
            score += ((1 + math.log(tf)) if tf else 0) * idf
            if in_context:
                score += HEADING_BONUS * idf
        if score > 0:
            scored.append({**p, "score": round(score, 3)})
    scored.sort(key=lambda p: (-p["score"], p["document"], p["text"]))
    return scored


def select_relevant(ranked: list) -> list:
    """Keep passages scoring at least MIN_RELATIVE_SCORE of the best one, max MAX_RESULTS.

    `ranked` must be sorted best first. No absolute threshold is used.
    """
    if not ranked:
        return []
    best = ranked[0]["score"]
    if best <= 0:
        return []
    cutoff = best * MIN_RELATIVE_SCORE
    return [p for p in ranked if p["score"] >= cutoff][:MAX_RESULTS]


def _search_sync(query: str, notes_dir) -> dict:
    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")
    terms = tokenize(query)
    if not terms:
        raise ValueError("Search query has no searchable words")

    root = _resolve_notes_dir(notes_dir)
    passages, files_read, skipped = _load_passages(root)
    matches = select_relevant(rank_passages(terms, passages))

    skip_note = f" {skipped} file(s) could not be read and were skipped." if skipped else ""
    count = len(matches)

    sources, seen = [], set()
    for m in matches:
        if m["document"] not in seen:
            seen.add(m["document"])
            sources.append({"title": m["document"], "url": None})

    if count == 0:
        if files_read == 0:
            summary = f"No readable course notes (.txt/.md) were found to search for '{query}'.{skip_note}"
        else:
            summary = f"No matching passages found for '{query}' in {files_read} course note file(s).{skip_note}"
    else:
        summary = (
            f"Found {count} matching passage(s) in {len(sources)} course note document(s) "
            f"for '{query}'.{skip_note}"
        )

    blocks = []
    for m in matches:
        where = m["document"] + (f" > {m['heading']}" if m["heading"] else "")
        blocks.append(f"[{where}] (score {m['score']})\n{m['text']}")

    return {
        "message": f"Found {count} matching passages",
        "summary": summary,
        "sources": sources,
        "artifacts": (
            [{"name": "Course notes passages", "content": "\n\n".join(blocks)}] if blocks else []
        ),
    }


async def course_notes_search(query: str, notes_dir=None) -> dict:
    """Search local course notes for passages relevant to `query`.

    `notes_dir` defaults to the COURSE_NOTES_DIR environment variable.
    """
    return await asyncio.to_thread(_search_sync, query, notes_dir)


async def course_notes_search_with_events(
    query: str, *, run_id: str, task_id: str, events: list, notes_dir=None,
) -> dict:
    """Run course_notes_search and record tool.started / tool.completed / tool.failed events."""
    return await run_tool_with_events(
        "course_notes_search", course_notes_search, (query, notes_dir),
        run_id=run_id, task_id=task_id, events=events,
        start_message="Searching course notes",
        done_message=lambda result: result["message"],
        fail_message="Course notes search failed",
    )
