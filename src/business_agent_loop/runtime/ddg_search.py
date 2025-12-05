from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from duckduckgo_search import DDGS

from ..config import SearchConfig

__all__ = ["SearchClient", "SearchResult"]


@dataclass
class SearchResult:
    title: str
    href: str
    snippet: str


class SearchClient:
    """Wrapper around duckduckgo_search for text queries."""

    def __init__(
        self,
        *,
        backend: str = "duckduckgo",
        region: str = "wt-wt",
        safesearch: str = "moderate",
        max_results: int = 5,
        timeout: int = 10,
        proxy: str | None = None,
    ) -> None:
        self.backend = backend
        self.region = region
        self.safesearch = safesearch
        self.max_results = max_results
        self.timeout = timeout
        self.proxy = proxy

    @classmethod
    def from_config(cls, config: SearchConfig) -> "SearchClient":
        return cls(
            backend=config.backend,
            region=config.region,
            safesearch=config.safesearch,
            max_results=config.max_results,
            timeout=config.timeout,
            proxy=config.proxy,
        )

    def search(self, query: str, **overrides: Any) -> list[SearchResult]:
        params = {
            "region": overrides.get("region", self.region),
            "safesearch": overrides.get("safesearch", self.safesearch),
            "max_results": overrides.get("max_results", self.max_results),
            "timeout": overrides.get("timeout", self.timeout),
            "proxy": overrides.get("proxy", self.proxy),
        }
        if self.backend != "duckduckgo":
            raise ValueError(f"Unsupported search backend: {self.backend}")

        client = DDGS(proxies=params["proxy"], timeout=params["timeout"])
        results = client.text(
            query,
            region=params["region"],
            safesearch=params["safesearch"],
            max_results=params["max_results"],
            timeout=params["timeout"],
        )
        return [self._normalize_result(entry) for entry in results]

    def _normalize_result(self, entry: Mapping[str, Any]) -> SearchResult:
        title = str(entry.get("title") or "").strip()
        href = str(entry.get("href") or entry.get("url") or "").strip()
        snippet = str(entry.get("snippet") or entry.get("body") or "").strip()
        return SearchResult(title=title, href=href, snippet=snippet)
