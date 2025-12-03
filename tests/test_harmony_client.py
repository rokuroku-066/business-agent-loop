from __future__ import annotations

import json
from typing import Any

from business_agent_loop.runtime.harmony_client import HarmonyClient, HarmonyRequest


class _DummyResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def __enter__(self) -> "_DummyResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:  # pragma: no cover - nothing to clean up
        return None

    def read(self) -> bytes:
        return self._body


def _make_request() -> HarmonyRequest:
    return HarmonyRequest(system="sys", developer="dev", user="user")


def test_harmony_client_uses_base_url_when_env_missing(monkeypatch):
    client = HarmonyClient(base_url="http://example.com/api")
    monkeypatch.delenv("BUSINESS_AGENT_LLM_ENDPOINT", raising=False)

    captured: dict[str, Any] = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        return _DummyResponse(json.dumps({"output": "ok"}))

    monkeypatch.setattr("business_agent_loop.runtime.harmony_client.urlopen", fake_urlopen)

    output = client.run(_make_request())

    assert output == "ok"
    assert captured["url"] == "http://example.com/api/generate"


def test_harmony_client_prefers_env_endpoint(monkeypatch):
    client = HarmonyClient(base_url="http://example.com/api")
    monkeypatch.setenv("BUSINESS_AGENT_LLM_ENDPOINT", "http://override.local/v1")

    captured: dict[str, Any] = {}

    def fake_urlopen(request):
        captured["url"] = request.full_url
        return _DummyResponse(json.dumps({"output": "from_env"}))

    monkeypatch.setattr("business_agent_loop.runtime.harmony_client.urlopen", fake_urlopen)

    output = client.run(_make_request())

    assert output == "from_env"
    assert captured["url"] == "http://override.local/v1/generate"
