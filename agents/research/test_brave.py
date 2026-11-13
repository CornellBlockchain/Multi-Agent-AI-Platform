"""Automated tests for brave_search. All Brave responses are mocked: no network, no real key."""
import httpx
import pytest

from tools import brave
from tools.brave import BraveSearchError, brave_search

RealAsyncClient = httpx.AsyncClient

SAMPLE = {
    "web": {
        "results": [
            {"title": "Page One", "url": "https://one.example/a", "description": "First snippet"},
            {"title": "Page Two", "url": "http://two.example/b", "description": "Second snippet"},
            {"title": "Bad URL", "url": "ftp://bad.example", "description": "skipped"},
        ]
    }
}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")


def mock_brave(monkeypatch, handler):
    """Make brave_search use a client whose requests go to `handler` instead of the network."""
    def factory(*args, **kwargs):
        return RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(brave.httpx, "AsyncClient", factory)


def respond(monkeypatch, status=200, json=None):
    mock_brave(monkeypatch, lambda request: httpx.Response(status, json=json if json is not None else {}))


@pytest.mark.asyncio
async def test_success_structure_and_extraction(monkeypatch):
    respond(monkeypatch, json=SAMPLE)
    result = await brave_search("ai")
    assert set(result) == {"message", "summary", "sources", "artifacts"}
    assert result["message"] == "Found 2 web results"
    assert "ai" in result["summary"]
    assert result["sources"] == [
        {"title": "Page One", "url": "https://one.example/a"},
        {"title": "Page Two", "url": "http://two.example/b"},
    ]
    assert len(result["artifacts"]) == 1
    content = result["artifacts"][0]["content"]
    assert "First snippet" in content and "Second snippet" in content
    assert "skipped" not in content


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["blockchain", "earthquakes"])
async def test_query_and_key_sent_to_api(monkeypatch, query):
    seen = {}

    def handler(request):
        seen["q"] = request.url.params["q"]
        seen["key"] = request.headers["X-Subscription-Token"]
        return httpx.Response(200, json=SAMPLE)

    mock_brave(monkeypatch, handler)
    result = await brave_search(query)
    assert seen == {"q": query, "key": "test-key"}
    assert query in result["summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"web": None}, {"web": {"results": []}}])
async def test_zero_results(monkeypatch, body):
    respond(monkeypatch, json=body)
    result = await brave_search("nothing")
    assert result["message"] == "Found 0 web results"
    assert "No results found" in result["summary"]
    assert result["sources"] == []
    assert result["artifacts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["", "   "])
async def test_empty_query(query):
    with pytest.raises(ValueError):
        await brave_search(query)


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, ""])
async def test_missing_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("BRAVE_API_KEY")
    else:
        monkeypatch.setenv("BRAVE_API_KEY", value)
    with pytest.raises(RuntimeError, match="BRAVE_API_KEY"):
        await brave_search("ai")


@pytest.mark.asyncio
@pytest.mark.parametrize("status,text", [
    (401, "invalid"),
    (403, "invalid"),
    (429, "rate limit"),
    (500, "server error"),
    (503, "server error"),
    (400, "failed"),
])
async def test_http_errors(monkeypatch, status, text):
    respond(monkeypatch, status=status)
    with pytest.raises(BraveSearchError, match=text):
        await brave_search("ai")


@pytest.mark.asyncio
async def test_timeout(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    mock_brave(monkeypatch, handler)
    with pytest.raises(BraveSearchError, match="timed out"):
        await brave_search("ai")


@pytest.mark.asyncio
async def test_connection_failure(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    mock_brave(monkeypatch, handler)
    with pytest.raises(BraveSearchError, match="connect"):
        await brave_search("ai")


@pytest.mark.asyncio
async def test_unreadable_response(monkeypatch):
    mock_brave(monkeypatch, lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(BraveSearchError, match="unreadable"):
        await brave_search("ai")
