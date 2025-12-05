from business_agent_loop.config import SearchConfig
from business_agent_loop.runtime import ddg_search
from business_agent_loop.runtime.ddg_search import SearchClient, SearchResult


class FakeDDGS:
    last_instance: "FakeDDGS | None" = None

    def __init__(self, *, proxy=None, timeout=None):
        self.proxy = proxy
        self.timeout = timeout
        self.calls = []
        FakeDDGS.last_instance = self

    def text(
        self,
        query: str,
        *,
        backend: str,
        region: str,
        safesearch: str,
        max_results: int,
        page: int,
        timelimit: str | None,
    ):
        self.calls.append(
            {
                "query": query,
                "backend": backend,
                "region": region,
                "safesearch": safesearch,
                "max_results": max_results,
                "page": page,
                "timelimit": timelimit,
            }
        )
        return [
            {"title": "Example", "href": "https://example.com", "body": "Snippet"},
            {"title": "Missing fields", "url": "https://example.org"},
        ]


def test_search_client_uses_config(monkeypatch):
    monkeypatch.setattr(ddg_search, "DDGS", FakeDDGS)
    config = SearchConfig(
        region="jp-jp", safesearch="strict", max_results=3, timeout=8, backend="google"
    )
    client = SearchClient.from_config(config)

    results = client.search("test query")

    assert isinstance(results[0], SearchResult)
    assert results[0].href == "https://example.com"
    assert results[1].snippet == ""
    assert FakeDDGS.last_instance is not None
    assert FakeDDGS.last_instance.proxy is None
    assert FakeDDGS.last_instance.timeout == 8
    assert FakeDDGS.last_instance.calls[0]["backend"] == "google"
    assert FakeDDGS.last_instance.calls[0]["region"] == "jp-jp"
    assert FakeDDGS.last_instance.calls[0]["max_results"] == 3
