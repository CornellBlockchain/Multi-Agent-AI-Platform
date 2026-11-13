"""Tool tests for the developer agent.

Two kinds of test live here:

    python -m pytest test_tools.py            offline: GitHub is faked, no keys, ~1 s
    python -m pytest test_tools.py -m live    live: real GitHub API, needs GITHUB_TOKEN

Offline tests run the real tool code; only the network is swapped out (see
`fake_github`). Live tests check that GitHub still answers the way the fakes
assume.

Adding a tool? Copy one of the tool sections below:
  1. offline tests for its success, empty and failure cases,
  2. one or two @pytest.mark.live tests against the real service.
The registry tests at the bottom check the TOOLS / TOOL_DECLARATIONS wiring
automatically.
"""

import asyncio
import inspect
import os
import shutil
from types import SimpleNamespace

import duckdb
import httpx
import pytest
from dotenv import load_dotenv

import tools
from tools import ToolError

load_dotenv(".env")


# --- Helpers -------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def new_ctx():
    return {"run_id": "r1", "task_id": "t1", "events": [], "sources": [], "artifacts": []}


def call_tool(name, **args):
    """Run a tool through run_tool, the way the agent does. Returns (result, ctx)."""
    ctx = new_ctx()
    result = run(tools.run_tool(name, args, ctx))
    return result, ctx


def json_response(data, status=200):
    return httpx.Response(status, json=data)


def text_response(text, status=200):
    return httpx.Response(status, text=text, headers={"content-type": "text/plain"})


@pytest.fixture
def fake_github(monkeypatch):
    """Answer GitHub requests from a dict of {url path: httpx.Response}.

    Every httpx.AsyncClient in tools.py gets a fake transport, so the real tool
    code runs -- headers, status handling, parsing -- without the network.
    Unknown paths return 404, like GitHub. Requests are recorded in `.requests`.
    """
    routes: dict[str, httpx.Response] = {}
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return routes.get(request.url.path, httpx.Response(404, json={"message": "Not Found"}))

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        tools.httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")

    class Fake:
        pass

    fake = Fake()
    fake.routes = routes
    fake.requests = requests
    return fake


needs_token = pytest.mark.skipif(not os.getenv("GITHUB_TOKEN"), reason="GITHUB_TOKEN not set")


# --- Event contract (applies to every tool) -------------------------------------

def assert_event_pair(ctx, expected_end):
    """One started event, then exactly one terminal event for the same call."""
    started, end = ctx["events"]
    assert started["type"] == "tool.started"
    assert end["type"] == expected_end
    assert started["tool_call_id"] == end["tool_call_id"]
    assert started["event_id"] != end["event_id"]
    for e in ctx["events"]:
        assert e["run_id"] == "r1" and e["task_id"] == "t1" and e["agent"] == "developer"
        assert e["timestamp"].endswith("+00:00")
    if expected_end == "tool.completed":
        assert end["duration_ms"] >= 0


def test_unknown_tool_fails_cleanly():
    result, ctx = call_tool("does_not_exist")
    assert "error" in result
    assert_event_pair(ctx, "tool.failed")


def test_search_limit_refuses_the_third_search_in_a_task(fake_github):
    fake_github.routes["/search/repositories"] = json_response({"items": []})
    ctx = new_ctx()
    for _ in range(2):
        assert "error" not in run(tools.run_tool("github_search", {"query": "x"}, ctx))

    result = run(tools.run_tool("github_search", {"query": "x"}, ctx))

    assert "Limit of 2 github_search calls" in result["error"]
    assert len(fake_github.requests) == 2, "the refused search never reaches GitHub"
    started, failed = ctx["events"][-2:]
    assert (started["type"], failed["type"]) == ("tool.started", "tool.failed")
    assert started["tool_call_id"] == failed["tool_call_id"]

    _, fresh = call_tool("github_search", query="x")
    assert_event_pair(fresh, "tool.completed")


def test_unexpected_exception_hides_detail(monkeypatch, capsys):
    async def broken(**kwargs):
        raise RuntimeError("token ghp_SECRET leaked")

    monkeypatch.setitem(tools.TOOLS, "broken", {"fn": broken, "start": "Breaking"})
    result, ctx = call_tool("broken")

    assert result == {"error": "RuntimeError"}
    assert "ghp_SECRET" not in ctx["events"][-1]["message"]
    assert "ghp_SECRET" in capsys.readouterr().out, "detail must still reach the log"


def test_tool_error_message_is_shown(monkeypatch):
    async def fails(**kwargs):
        raise ToolError("readable reason")

    monkeypatch.setitem(tools.TOOLS, "fails", {"fn": fails, "start": "Failing"})
    result, ctx = call_tool("fails")

    assert result == {"error": "readable reason"}
    assert "readable reason" in ctx["events"][-1]["message"]


def test_each_call_gets_a_new_tool_call_id(fake_github):
    fake_github.routes["/search/repositories"] = json_response({"items": []})
    ctx = new_ctx()
    run(tools.run_tool("github_search", {"query": "a"}, ctx))
    run(tools.run_tool("github_search", {"query": "a"}, ctx))
    assert len({e["tool_call_id"] for e in ctx["events"]}) == 2


# --- github_get / check_repo -----------------------------------------------------

@pytest.mark.parametrize("given, expected", [
    ("duckdb/duckdb", "duckdb/duckdb"),
    ("  duckdb/duckdb  ", "duckdb/duckdb"),
    ("https://github.com/duckdb/duckdb", "duckdb/duckdb"),
    ("https://github.com/duckdb/duckdb/", "duckdb/duckdb"),
    ("my-org/my.repo_name", "my-org/my.repo_name"),
])
def test_check_repo_accepts(given, expected):
    assert tools.check_repo(given) == expected


@pytest.mark.parametrize("bad", ["justaword", "a/b/c", "", "owner/", "/name", "a b/c"])
def test_check_repo_rejects(bad):
    with pytest.raises(ToolError, match="owner/name"):
        tools.check_repo(bad)


def test_github_get_sends_token_and_headers(fake_github):
    fake_github.routes["/repos/a/b"] = json_response({"ok": True})
    run(tools.github_get("/repos/a/b"))

    sent = fake_github.requests[0]
    assert sent.headers["Authorization"] == "Bearer test-token"
    assert sent.headers["Accept"] == "application/vnd.github+json"


def test_github_get_raw_asks_for_plain_text(fake_github):
    fake_github.routes["/repos/a/b/readme"] = text_response("# Hello")
    r = run(tools.github_get("/repos/a/b/readme", raw=True))

    assert r.text == "# Hello"
    assert fake_github.requests[0].headers["Accept"] == "application/vnd.github.raw"


def test_github_get_404(fake_github):
    with pytest.raises(ToolError, match="Not found on GitHub"):
        run(tools.github_get("/repos/nobody/nothing"))


def test_github_get_other_error(fake_github):
    fake_github.routes["/repos/a/b"] = httpx.Response(403, json={"message": "rate limited"})
    with pytest.raises(ToolError, match="HTTP 403"):
        run(tools.github_get("/repos/a/b"))


def test_github_get_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(ToolError, match="GITHUB_TOKEN"):
        run(tools.github_get("/repos/a/b"))


# --- github_search ---------------------------------------------------------------

def repo_item(name, stars=100, language="Python", description="A repo"):
    return {
        "full_name": name, "html_url": f"https://github.com/{name}",
        "stargazers_count": stars, "language": language, "description": description,
    }


def test_github_search_returns_repos(fake_github):
    fake_github.routes["/search/repositories"] = json_response({"items": [
        repo_item("duckdb/duckdb", 40000, "C++"),
        repo_item("duckdb/duckdb-wasm", 1500, "TypeScript", None),
    ]})
    result, ctx = call_tool("github_search", query="duckdb")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Found 2 repositories"
    assert "duckdb/duckdb (C++, 40000 stars)" in result["summary"]
    assert "no description" in result["summary"]
    assert ctx["sources"] == [
        {"title": "duckdb/duckdb", "url": "https://github.com/duckdb/duckdb"},
        {"title": "duckdb/duckdb-wasm", "url": "https://github.com/duckdb/duckdb-wasm"},
    ]
    assert fake_github.requests[0].url.params["q"] == "duckdb"


def test_github_search_no_results_is_success(fake_github):
    fake_github.routes["/search/repositories"] = json_response({"items": []})
    result, ctx = call_tool("github_search", query="zzqxv")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "No repositories found"
    assert ctx["sources"] == []


def test_github_search_http_error(fake_github):
    fake_github.routes["/search/repositories"] = httpx.Response(422, json={})
    result, ctx = call_tool("github_search", query="x")

    assert_event_pair(ctx, "tool.failed")
    assert "422" in result["error"]


def test_github_search_without_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result, ctx = call_tool("github_search", query="x")

    assert_event_pair(ctx, "tool.failed")
    assert "GITHUB_TOKEN" in result["error"]


@pytest.mark.live
@needs_token
def test_live_github_search():
    result, ctx = call_tool("github_search", query="duckdb")
    assert_event_pair(ctx, "tool.completed")
    assert any(s["url"].startswith("https://github.com/") for s in ctx["sources"])


@pytest.mark.live
@needs_token
def test_live_github_search_results_follow_the_query():
    _, a = call_tool("github_search", query="vector database")
    _, b = call_tool("github_search", query="rust web framework")
    assert {s["url"] for s in a["sources"]} != {s["url"] for s in b["sources"]}


# --- repo_overview ---------------------------------------------------------------

def overview_routes(fake_github, repo="acme/app", files=("README.md", "src/main.py"), readme="# App"):
    fake_github.routes[f"/repos/{repo}"] = json_response({
        "full_name": repo, "html_url": f"https://github.com/{repo}", "default_branch": "main",
        "description": "Demo app", "stargazers_count": 42, "language": "Python",
    })
    if readme is not None:
        fake_github.routes[f"/repos/{repo}/readme"] = text_response(readme)
    fake_github.routes[f"/repos/{repo}/git/trees/main"] = json_response({"tree": [
        {"path": p, "type": "blob"} for p in files
    ] + [{"path": "src", "type": "tree"}]})


def test_repo_overview_returns_readme_and_files(fake_github):
    overview_routes(fake_github)
    result, ctx = call_tool("repo_overview", repo="acme/app")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Inspected acme/app (2 files)"
    assert "42 stars" in result["summary"]
    assert "# App" in result["summary"]
    assert "src/main.py" in result["summary"]
    assert "\nsrc\n" not in result["summary"], "directories are not listed as files"
    assert ctx["sources"][0] == {"title": "acme/app", "url": "https://github.com/acme/app"}
    assert ctx["artifacts"][0]["name"] == "acme/app file tree"


def test_repo_overview_accepts_url(fake_github):
    overview_routes(fake_github)
    _, ctx = call_tool("repo_overview", repo="https://github.com/acme/app")
    assert_event_pair(ctx, "tool.completed")


def test_repo_overview_without_readme_still_works(fake_github):
    overview_routes(fake_github, readme=None)
    result, ctx = call_tool("repo_overview", repo="acme/app")

    assert_event_pair(ctx, "tool.completed")
    assert "(no README)" in result["summary"]


def test_repo_overview_caps_large_trees(fake_github):
    many = [f"f{i}.py" for i in range(tools.MAX_TREE_PATHS + 50)]
    overview_routes(fake_github, files=many)
    result, _ = call_tool("repo_overview", repo="acme/app")

    assert "... 50 more files" in result["summary"]
    assert f"f{tools.MAX_TREE_PATHS}.py" not in result["summary"]


def test_repo_overview_missing_repo(fake_github):
    result, ctx = call_tool("repo_overview", repo="nobody/nothing")
    assert_event_pair(ctx, "tool.failed")
    assert "Not found on GitHub" in result["error"]


def test_repo_overview_bad_input_makes_no_request(fake_github):
    result, ctx = call_tool("repo_overview", repo="justaword")
    assert_event_pair(ctx, "tool.failed")
    assert fake_github.requests == []


# A repo shaped like fastapi: the docs sort first and fill the file list.
DOCS_FIRST = ([f"docs/page{i}.md" for i in range(tools.MAX_TREE_PATHS)]
              + ["fastapi/params.py", "fastapi/dependencies/utils.py", "README.md"])


def test_repo_overview_outline_shows_folders_the_file_list_cuts_off(fake_github):
    overview_routes(fake_github, files=DOCS_FIRST)
    result, _ = call_tool("repo_overview", repo="acme/app")

    assert "fastapi/params.py" not in result["summary"], "the cap still hides it"
    assert f"docs/ ({tools.MAX_TREE_PATHS} files)" in result["summary"]
    assert "fastapi/ (2 files)" in result["summary"]
    assert "path set to a folder" in result["summary"]


def test_repo_overview_path_lists_one_folder(fake_github):
    overview_routes(fake_github, files=DOCS_FIRST)
    result, ctx = call_tool("repo_overview", repo="acme/app", path="/fastapi/")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Inspected acme/app/fastapi (2 files)"
    assert "fastapi/params.py" in result["summary"]
    assert "fastapi/dependencies/ (1 files)" in result["summary"]
    assert "docs/" not in result["summary"]
    assert ctx["sources"] == [{"title": "acme/app/fastapi",
                               "url": "https://github.com/acme/app/tree/main/fastapi"}]
    assert not any(r.url.path.endswith("/readme") for r in fake_github.requests)


def test_repo_overview_unknown_folder_fails(fake_github):
    overview_routes(fake_github)
    result, ctx = call_tool("repo_overview", repo="acme/app", path="nope")

    assert_event_pair(ctx, "tool.failed")
    assert "No folder 'nope'" in result["error"]


def test_repo_overview_rejects_parent_path_without_a_request(fake_github):
    result, ctx = call_tool("repo_overview", repo="acme/app", path="../secrets")

    assert_event_pair(ctx, "tool.failed")
    assert fake_github.requests == []


@pytest.mark.live
@needs_token
def test_live_repo_overview_follows_renames():
    """tiangolo/fastapi moved to fastapi/fastapi; GitHub answers with a 301."""
    result, ctx = call_tool("repo_overview", repo="tiangolo/fastapi")
    assert_event_pair(ctx, "tool.completed")
    assert "fastapi" in result["summary"].lower()


# --- read_repo_file ----------------------------------------------------------------

def test_read_repo_file_returns_contents(fake_github):
    fake_github.routes["/repos/acme/app/contents/src/main.py"] = text_response("print('hi')")
    result, ctx = call_tool("read_repo_file", repo="acme/app", path="src/main.py")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Read src/main.py"
    assert result["summary"] == "print('hi')"
    assert ctx["sources"] == [{"title": "acme/app/src/main.py",
                               "url": "https://github.com/acme/app/blob/HEAD/src/main.py"}]
    assert ctx["artifacts"] == [{"name": "acme/app/src/main.py", "content": "print('hi')"}]


def test_read_repo_file_strips_leading_slash(fake_github):
    fake_github.routes["/repos/acme/app/contents/src/main.py"] = text_response("x")
    _, ctx = call_tool("read_repo_file", repo="acme/app", path="/src/main.py")
    assert_event_pair(ctx, "tool.completed")


def test_read_repo_file_truncates_big_files(fake_github):
    big = "x" * (tools.MAX_FILE_CHARS + 100)
    fake_github.routes["/repos/acme/app/contents/big.py"] = text_response(big)
    result, _ = call_tool("read_repo_file", repo="acme/app", path="big.py")

    assert result["message"] == "Read big.py (truncated)"
    assert len(result["summary"]) == tools.MAX_FILE_CHARS


def test_read_repo_file_directory(fake_github):
    fake_github.routes["/repos/acme/app/contents/src"] = json_response([{"name": "main.py"}])
    result, ctx = call_tool("read_repo_file", repo="acme/app", path="src")

    assert_event_pair(ctx, "tool.failed")
    assert "is a directory" in result["error"]


def test_read_repo_file_missing(fake_github):
    result, ctx = call_tool("read_repo_file", repo="acme/app", path="nope.py")
    assert_event_pair(ctx, "tool.failed")
    assert "Not found on GitHub" in result["error"]


@pytest.mark.parametrize("path", ["../../etc/passwd", "src/../../x", "", "   "])
def test_read_repo_file_rejects_bad_paths_without_a_request(fake_github, path):
    result, ctx = call_tool("read_repo_file", repo="acme/app", path=path)

    assert_event_pair(ctx, "tool.failed")
    assert "Invalid file path" in result["error"]
    assert fake_github.requests == []


# --- duckdb_query ------------------------------------------------------------------

@pytest.fixture
def tiny_repos(monkeypatch, tmp_path):
    """Point duckdb_query at a three-repo snapshot written for the test."""
    path = tmp_path / "repos.parquet"
    con = duckdb.connect()
    con.execute(f"""COPY (SELECT * FROM (VALUES
        ('a/one', 'First', 'Python', 300, 'MIT', ['llm']),
        ('b/two', 'Second', 'Python', 100, NULL, []),
        ('c/three', NULL, 'Rust', 200, 'MIT', ['cli', 'llm'])
    ) t(full_name, description, language, stars, license, topics)) TO '{path}' (FORMAT parquet)""")
    con.close()
    monkeypatch.setattr(tools, "REPOS_PARQUET", path)
    return tmp_path


def test_duckdb_query_aggregates(tiny_repos):
    result, ctx = call_tool("duckdb_query",
                            sql="SELECT language, count(*) AS n FROM repos GROUP BY language ORDER BY n DESC")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Query returned 2 rows"
    assert result["summary"].startswith("2 rows. Columns: language, n")
    assert "Python | 2" in result["summary"]
    assert ctx["sources"] == [{"title": f"GitHub repos snapshot {tools.REPOS_SNAPSHOT}", "url": None}]
    assert ctx["artifacts"][0]["content"] == "language,n\nPython,2\nRust,1\n"


def test_duckdb_query_reads_lists_and_nulls(tiny_repos):
    result, _ = call_tool("duckdb_query",
                          sql="SELECT full_name, description FROM repos WHERE list_contains(topics, 'cli')")
    assert "c/three | NULL" in result["summary"]


def test_duckdb_query_caps_rows(tiny_repos):
    result, _ = call_tool("duckdb_query", sql=f"SELECT * FROM range({tools.MAX_QUERY_ROWS + 25})")

    assert result["message"] == f"Query returned {tools.MAX_QUERY_ROWS + 25} rows"
    assert result["summary"].startswith(f"First {tools.MAX_QUERY_ROWS} of {tools.MAX_QUERY_ROWS + 25} rows")
    assert result["artifacts"][0]["content"].count("\n") == tools.MAX_QUERY_ROWS + 1  # header + rows


def test_duckdb_query_caps_cell_text(tiny_repos):
    result, _ = call_tool("duckdb_query", sql="SELECT repeat('x', 5000) AS long")
    assert "x" * tools.MAX_CELL_CHARS + "..." in result["summary"]
    assert "x" * (tools.MAX_CELL_CHARS + 1) not in result["summary"]


@pytest.mark.parametrize("sql", ["", "   "])
def test_duckdb_query_empty_sql_opens_nothing(monkeypatch, sql):
    monkeypatch.setattr(tools.duckdb, "connect", lambda *a, **kw: pytest.fail("connected"))
    result, ctx = call_tool("duckdb_query", sql=sql)

    assert_event_pair(ctx, "tool.failed")
    assert result["error"] == "Empty SQL query"


def test_duckdb_query_bad_sql_shows_duckdb_message(tiny_repos):
    result, ctx = call_tool("duckdb_query", sql="SELECT nope FROM repos")

    assert_event_pair(ctx, "tool.failed")
    assert result["error"].startswith("DuckDB: Binder Error")
    assert "nope" in result["error"]


def test_duckdb_query_one_statement_only(tiny_repos):
    result, _ = call_tool("duckdb_query", sql="SELECT 1; SELECT 2")
    assert result["error"] == "Send exactly one SQL statement"


@pytest.mark.parametrize("sql", [
    "DROP TABLE repos",
    "INSERT INTO repos (full_name) VALUES ('x/y')",
    "CREATE TABLE t AS SELECT 1",
    "COPY repos TO 'out.csv'",
    "ATTACH 'other.db'",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SET enable_external_access = true",
    "PRAGMA enable_profiling",
])
def test_duckdb_query_refuses_anything_but_reads(tiny_repos, sql):
    result, ctx = call_tool("duckdb_query", sql=sql)

    assert_event_pair(ctx, "tool.failed")
    assert result["error"].startswith("Only read queries are allowed")
    assert sorted(p.name for p in tiny_repos.iterdir()) == ["repos.parquet"]


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('{f}')",
    "SELECT * FROM '{f}'",
    "SELECT * FROM read_text('{f}')",
    "SELECT * FROM glob('{d}/*')",
])
def test_duckdb_query_cannot_read_files(tiny_repos, sql):
    secret = tiny_repos / "secret.csv"
    secret.write_text("token\nghp_SECRET\n")
    result, ctx = call_tool("duckdb_query", sql=sql.format(f=secret, d=tiny_repos))

    assert_event_pair(ctx, "tool.failed")
    assert "Permission Error" in result["error"]
    assert "ghp_SECRET" not in str(result)


@pytest.mark.parametrize("sql", [
    "COPY repos TO '{d}/out.csv'",
    "ATTACH '{d}/other.db'",
    "INSTALL httpfs",
    "LOAD httpfs",
    "SET enable_external_access = true",
    "SET lock_configuration = false",
])
def test_duckdb_locked_even_past_the_statement_check(tiny_repos, sql):
    """Second line of defence: had a write slipped past the type check, DuckDB still refuses it."""
    con = duckdb.connect()
    tools.open_repos_db(con)
    with pytest.raises(duckdb.Error):
        con.execute(sql.format(d=tiny_repos))
    assert sorted(p.name for p in tiny_repos.iterdir()) == ["repos.parquet"]


def test_duckdb_query_timeout_interrupts(tiny_repos, monkeypatch):
    real_connect = duckdb.connect
    spies = []

    class Spy:
        def __init__(self):
            self.con = real_connect()
            self.interrupted = False
            spies.append(self)

        def interrupt(self):
            self.interrupted = True
            self.con.interrupt()

        def __getattr__(self, name):
            return getattr(self.con, name)

    monkeypatch.setattr(tools.duckdb, "connect", lambda *a, **kw: Spy())
    monkeypatch.setattr(tools, "QUERY_TIMEOUT_S", 0.5)
    result, ctx = call_tool("duckdb_query",
                            sql="SELECT count(*) FROM range(100000000000) WHERE range % 7 = 3")

    assert_event_pair(ctx, "tool.failed")
    assert "took longer than 0.5 s" in result["error"]
    assert spies[0].interrupted  # and the test only finishes because the worker thread stopped


def test_duckdb_real_snapshot_loads():
    assert tools.REPOS_PARQUET.exists(), "run data/build_repos.py"
    result, ctx = call_tool("duckdb_query", sql="DESCRIBE repos")

    assert_event_pair(ctx, "tool.completed")
    columns = [line.split(" | ")[0] for line in result["summary"].splitlines()[3:]]
    assert columns == ["full_name", "description", "language", "stars", "forks", "open_issues",
                       "license", "topics", "created_at", "pushed_at", "archived", "html_url"]
    description = DECLARED["duckdb_query"].description
    assert all(c in description for c in columns), "Gemini must be told every column"


@pytest.mark.live
@needs_token
def test_live_read_repo_file():
    result, ctx = call_tool("read_repo_file", repo="fastapi/fastapi", path="README.md")
    assert_event_pair(ctx, "tool.completed")
    assert "FastAPI" in result["summary"]


# --- run_cpp -----------------------------------------------------------------------
#
# Docker is faked: `fake_docker` replaces asyncio.create_subprocess_exec, so the
# real tool code builds the command and parses the sandbox's output. The sample
# programs in samples/cpp/ are the inputs. With Docker installed and the image
# pulled (docker pull gcc:14), `python -m pytest -m live -k run_cpp` runs one for real.

SAMPLES = os.path.join(os.path.dirname(__file__), "samples", "cpp")


def sample(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return f.read()


class FakeProcess:
    def __init__(self, stdout=b"", stderr=b"", returncode=0, hang=False):
        self.stdout, self.stderr, self.returncode, self.hang = stdout, stderr, returncode, hang
        self.input = None
        self.killed = False

    async def communicate(self, input=None):
        self.input = input
        if self.hang:
            await asyncio.sleep(3600)
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


@pytest.fixture
def fake_docker(monkeypatch):
    """Answer each subprocess call with the next FakeProcess in `.processes`.

    `.answer(...)` queues what the container prints: program output on stdout,
    compiler output on stderr, then the status line. Each call's argv is
    recorded in `.calls`; extra calls (docker kill) get an empty process.
    """
    class Fake:
        def answer(self, compile=0, run=0, compiler=b"", program=b""):
            status = b"\n@@cpp compile=%d run=%d\n" % (compile, run)
            self.processes.append(FakeProcess(program, compiler + status))

    fake = Fake()
    fake.calls, fake.processes = [], []

    async def fake_exec(*argv, **kwargs):
        fake.calls.append(list(argv))
        return fake.processes.pop(0) if fake.processes else FakeProcess()

    monkeypatch.setattr(tools.asyncio, "create_subprocess_exec", fake_exec)
    return fake


def test_run_cpp_success(fake_docker):
    fake_docker.answer(program=b"Hello from C++\nsum 1..10 = 55\n")
    result, ctx = call_tool("run_cpp", code=sample("hello.cpp"))

    assert_event_pair(ctx, "tool.completed")
    assert ctx["events"][0]["message"] == "Compiling C++"
    assert result["message"] == "Execution completed (exit 0)"
    assert "Compiled: yes. Exit status: 0. Timed out: no." in result["summary"]
    assert "sum 1..10 = 55" in result["summary"]
    assert ctx["sources"] == []
    assert ctx["artifacts"] == [{"name": "C++ program output", "content": "Hello from C++\nsum 1..10 = 55\n"}]


def test_run_cpp_sandbox_flags_and_code_on_stdin(fake_docker, monkeypatch):
    monkeypatch.delenv("CPP_SANDBOX_IMAGE", raising=False)
    fake_docker.answer()
    proc = fake_docker.processes[0]
    code = sample("hello.cpp")
    call_tool("run_cpp", code=code)

    argv = fake_docker.calls[0]
    joined = " ".join(argv)
    assert argv[:3] == ["docker", "run", "--rm"]
    for flag in ["--network none", "--memory 256m", "--cpus 1", "--pids-limit 64", "--read-only",
                 "--cap-drop ALL", "--security-opt no-new-privileges", "gcc:14 sh -c"]:
        assert flag in joined
    assert not any("Hello from C++" in a for a in argv), "code must go on stdin, not argv"
    assert proc.input == code.encode()


def test_run_cpp_image_can_be_overridden(fake_docker, monkeypatch):
    monkeypatch.setenv("CPP_SANDBOX_IMAGE", "gcc:13")
    fake_docker.answer()
    call_tool("run_cpp", code=sample("hello.cpp"))
    assert "gcc:13" in fake_docker.calls[0]


def test_run_cpp_compile_error_is_a_result(fake_docker):
    fake_docker.answer(compile=1, run=-1,
                       compiler=b"main.cpp:5:18: error: 'count' was not declared in this scope")
    result, ctx = call_tool("run_cpp", code=sample("compile_error.cpp"))

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Compilation failed"
    assert "Compiled: no. Exit status: not run." in result["summary"]
    assert "'count' was not declared" in result["summary"]
    assert [a["name"] for a in ctx["artifacts"]] == ["C++ compiler output"]


def test_run_cpp_runtime_crash_is_a_result(fake_docker):
    fake_docker.answer(run=134, program=b"about to read v[5]\nterminate called after throwing an instance "
                                        b"of 'std::out_of_range'\n")
    result, ctx = call_tool("run_cpp", code=sample("runtime_error.cpp"))

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Execution completed (exit 134)"
    assert "Exit status: 134 (killed by signal 6)" in result["summary"]
    assert "out_of_range" in result["summary"]


def test_run_cpp_nonzero_exit(fake_docker):
    fake_docker.answer(run=3)
    result, _ = call_tool("run_cpp", code="int main() { return 3; }")
    assert "Exit status: 3." in result["summary"]
    assert "Program output:\n(none)" in result["summary"]


def test_run_cpp_program_timeout_is_a_result(fake_docker):
    fake_docker.answer(run=124)
    result, ctx = call_tool("run_cpp", code=sample("infinite_loop.cpp"))

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == f"Program timed out after {tools.CPP_RUN_TIMEOUT_S} s"
    assert "Timed out: yes" in result["summary"]


def test_run_cpp_hung_sandbox_is_killed_by_name(fake_docker, monkeypatch):
    monkeypatch.setattr(tools, "CPP_SANDBOX_TIMEOUT_S", 0.05)
    hung = FakeProcess(hang=True)
    fake_docker.processes.append(hung)
    result, ctx = call_tool("run_cpp", code=sample("infinite_loop.cpp"))

    assert_event_pair(ctx, "tool.failed")
    assert "did not finish" in result["error"]
    run_argv, kill_argv = fake_docker.calls
    name = run_argv[run_argv.index("--name") + 1]
    assert kill_argv == ["docker", "kill", name], "killing the CLI alone leaves the container running"
    assert hung.killed


def test_run_cpp_truncates_long_output(fake_docker):
    fake_docker.answer(program=b"x" * (tools.MAX_CPP_OUTPUT_CHARS + 1))
    result, ctx = call_tool("run_cpp", code="int main() {}")

    assert f"Program output (truncated to {tools.MAX_CPP_OUTPUT_CHARS} chars)" in result["summary"]
    assert len(ctx["artifacts"][0]["content"]) == tools.MAX_CPP_OUTPUT_CHARS


def test_run_cpp_empty_code_starts_nothing(fake_docker):
    result, ctx = call_tool("run_cpp", code="   ")

    assert_event_pair(ctx, "tool.failed")
    assert "No C++ code" in result["error"]
    assert fake_docker.calls == []


def test_run_cpp_without_docker(monkeypatch):
    async def missing(*argv, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(tools.asyncio, "create_subprocess_exec", missing)
    result, ctx = call_tool("run_cpp", code=sample("hello.cpp"))

    assert_event_pair(ctx, "tool.failed")
    assert "Docker is not available" in result["error"]


@pytest.mark.parametrize("stderr, expected", [
    (b"Unable to find image 'gcc:14' locally\n", "not pulled"),
    (b"docker: Error response from daemon: secret detail\n", "could not run the program (docker exit 125)"),
])
def test_run_cpp_docker_failure(fake_docker, capsys, stderr, expected):
    fake_docker.processes.append(FakeProcess(stderr=stderr, returncode=125))
    result, ctx = call_tool("run_cpp", code=sample("hello.cpp"))

    assert_event_pair(ctx, "tool.failed")
    assert expected in result["error"]
    assert "secret detail" not in result["error"]
    assert stderr.decode().strip() in capsys.readouterr().out, "docker's text must still reach the log"


@pytest.mark.live
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_live_run_cpp():
    """Needs Docker and the image pulled first:  docker pull gcc:14"""
    result, ctx = call_tool("run_cpp", code=sample("hello.cpp"))
    assert_event_pair(ctx, "tool.completed")
    assert "sum 1..10 = 55" in result["summary"]


# --- python_execution --------------------------------------------------------------
# Offline: the tool's real code runs, only the docker subprocess is faked.
# Live: real Docker, checking that the sandbox limits actually hold.

class FakePythonProcess:
    def __init__(self, stdout=b"", stderr=b"", exit_code=0, hang=False):
        self.stdout, self.stderr, self.exit_code, self.hang = stdout, stderr, exit_code, hang
        self.returncode = None
        self.stdin = None
        self.killed = False

    async def communicate(self, data):
        self.stdin = data
        if self.hang:
            await asyncio.sleep(3600)
        self.returncode = self.exit_code
        return self.stdout, self.stderr

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


@pytest.fixture
def fake_python_docker(monkeypatch):
    """Answer `docker run` with fake.process and record every command in .calls."""
    fake = SimpleNamespace(calls=[], process=FakePythonProcess(), installed=True)

    async def create_subprocess_exec(*argv, **kwargs):
        fake.calls.append(list(argv))
        if not fake.installed:
            raise FileNotFoundError("docker")
        if argv[:2] == ("docker", "rm"):
            return FakePythonProcess()
        return fake.process

    monkeypatch.setattr(tools.asyncio, "create_subprocess_exec", create_subprocess_exec)
    return fake


def test_python_execution_returns_output(fake_python_docker):
    fake_python_docker.process = FakePythonProcess(stdout=b"45\n")
    result, ctx = call_tool("python_execution", code="print(sum(range(10)))")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Execution completed (exit 0)"
    assert "45" in result["summary"]
    assert fake_python_docker.process.stdin == b"print(sum(range(10)))"
    names = [a["name"] for a in ctx["artifacts"]]
    assert names == ["Python program", "Python output"]


def test_python_execution_runs_in_a_locked_down_container(fake_python_docker):
    call_tool("python_execution", code="print(1)")
    argv = fake_python_docker.calls[0]
    pairs = set(zip(argv, argv[1:]))

    assert argv[:2] == ["docker", "run"]
    for flag in [("--network", "none"), ("--memory", "256m"), ("--pull", "never"),
                 ("--user", "65534:65534"), ("--cap-drop", "ALL")]:
        assert flag in pairs, f"missing {flag}"
    assert "--read-only" in argv and "--rm" in argv
    for leak in ("-e", "--env", "--env-file", "-v", "--volume", "--mount", "--privileged"):
        assert leak not in argv, f"{leak} would expose our files or keys"
    assert argv[-3:] == ["python", "-I", "-"]


def test_python_error_is_a_completed_run_with_the_traceback(fake_python_docker):
    fake_python_docker.process = FakePythonProcess(stderr=b"ZeroDivisionError: division by zero\n", exit_code=1)
    result, ctx = call_tool("python_execution", code="1/0")

    assert_event_pair(ctx, "tool.completed")
    assert result["message"] == "Execution completed (exit 1)"
    assert "ZeroDivisionError" in result["summary"]


def test_python_memory_kill_is_explained(fake_python_docker):
    fake_python_docker.process = FakePythonProcess(exit_code=137)
    result, _ = call_tool("python_execution", code="x = 'a' * 10**10")
    assert "256 MB" in result["message"]


def test_python_timeout_fails(fake_python_docker):
    fake_python_docker.process = FakePythonProcess(exit_code=124)
    result, ctx = call_tool("python_execution", code="while True: pass")

    assert_event_pair(ctx, "tool.failed")
    assert result == {"error": f"Execution timed out after {tools.PYTHON_TIMEOUT_S} s"}


@pytest.mark.parametrize("stderr, expected", [
    ("Unable to find image locally. No such image: python:3.12-slim", "docker pull"),
    ("failed to connect to the docker API at unix:///x.sock", "not running"),
    ("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", "not running"),
    ("something unexpected", "could not start"),
])
def test_python_docker_problems_are_explained(fake_python_docker, stderr, expected):
    fake_python_docker.process = FakePythonProcess(stderr=stderr.encode(), exit_code=125)
    result, ctx = call_tool("python_execution", code="print(1)")

    assert_event_pair(ctx, "tool.failed")
    assert expected in result["error"]


def test_python_without_docker_installed(fake_python_docker):
    fake_python_docker.installed = False
    result, _ = call_tool("python_execution", code="print(1)")
    assert result == {"error": "Docker is not installed, so Python cannot run"}


def test_python_stuck_container_is_removed(fake_python_docker, monkeypatch):
    monkeypatch.setattr(tools, "PYTHON_TIMEOUT_S", 0)
    monkeypatch.setattr(tools, "DOCKER_START_S", 0.05)
    fake_python_docker.process = FakePythonProcess(hang=True)
    result, _ = call_tool("python_execution", code="print(1)")

    assert result == {"error": "Docker did not finish in time"}
    assert fake_python_docker.process.killed
    name = fake_python_docker.calls[0][fake_python_docker.calls[0].index("--name") + 1]
    assert ["docker", "rm", "-f", name] in fake_python_docker.calls


@pytest.mark.parametrize("code", ["", "   ", "x" * (tools.MAX_CODE_CHARS + 1)])
def test_python_bad_code_starts_no_container(fake_python_docker, code):
    result, _ = call_tool("python_execution", code=code)
    assert "error" in result
    assert fake_python_docker.calls == []


def test_python_long_output_is_cut(fake_python_docker):
    fake_python_docker.process = FakePythonProcess(stdout=b"x" * (tools.MAX_OUTPUT_CHARS + 500))
    result, _ = call_tool("python_execution", code="print('x' * 5000)")
    assert f"cut off at {tools.MAX_OUTPUT_CHARS} characters" in result["summary"]


needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")


@pytest.mark.live
@needs_docker
def test_live_python_runs_real_code():
    result, ctx = call_tool("python_execution", code="print(sum(range(10)))")
    assert_event_pair(ctx, "tool.completed")
    assert "45" in result["summary"]


@pytest.mark.live
@needs_docker
def test_live_python_sandbox_holds():
    code = "\n".join([
        "import os, socket",
        "try:",
        "    socket.create_connection(('1.1.1.1', 53), timeout=2); print('NETWORK OPEN')",
        "except OSError:",
        "    print('network blocked')",
        "try:",
        "    open('/escape.txt', 'w'); print('FILESYSTEM WRITABLE')",
        "except OSError:",
        "    print('filesystem read-only')",
        "print('uid', os.getuid())",
        "print('env', sorted(os.environ))",
    ])
    result, _ = call_tool("python_execution", code=code)

    assert "network blocked" in result["summary"]
    assert "filesystem read-only" in result["summary"]
    assert "uid 65534" in result["summary"]
    # The image sets its own GPG_KEY; none of ours may get in.
    for secret in ("GEMINI_API_KEY", "GITHUB_TOKEN"):
        assert secret not in result["summary"]


@pytest.mark.live
@needs_docker
def test_live_python_infinite_loop_times_out():
    result, ctx = call_tool("python_execution", code="while True: pass")
    assert_event_pair(ctx, "tool.failed")
    assert "timed out" in result["error"]


# --- Registry wiring (checks every tool automatically) -------------------------------

DECLARED = {d.name: d for d in tools.TOOL_DECLARATIONS}


def test_every_tool_is_declared_to_gemini():
    missing = set(tools.TOOLS) - set(DECLARED)
    assert not missing, f"add these to TOOL_DECLARATIONS so Gemini can call them: {missing}"


def test_every_declaration_has_a_tool():
    orphans = set(DECLARED) - set(tools.TOOLS)
    assert not orphans, f"declared to Gemini but missing from TOOLS: {orphans}"


@pytest.mark.parametrize("name", sorted(tools.TOOLS))
def test_tool_entry_is_well_formed(name):
    entry = tools.TOOLS[name]
    assert inspect.iscoroutinefunction(entry["fn"]), "tools must be async functions"
    assert entry["start"].strip(), "needs a start message for the dashboard"


@pytest.mark.parametrize("name", sorted(set(tools.TOOLS) & set(DECLARED)))
def test_declared_parameters_match_the_function(name):
    """Gemini sends exactly the declared parameters as keyword arguments."""
    params = DECLARED[name].parameters
    declared = set(params.properties or {})
    required = set(params.required or [])
    signature = inspect.signature(tools.TOOLS[name]["fn"]).parameters

    assert declared <= set(signature), f"declared but not accepted: {declared - set(signature)}"
    needed = {p for p, v in signature.items() if v.default is inspect.Parameter.empty}
    assert needed <= required, f"function needs these but they are not required: {needed - required}"
    assert DECLARED[name].description, "Gemini picks tools by description; write one"
