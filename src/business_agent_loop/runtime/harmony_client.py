from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class HarmonyRequest:
    system: str
    developer: str
    user: str


class HarmonyClient:
    """Placeholder for Harmony-compatible model calls.

    The design expects gpt-oss-20b served through vLLM or Ollama. This stub keeps the
    interface explicit so the orchestrator can be wired without pulling heavy
    dependencies during early development.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or "http://localhost:8000/v1"

    def run(self, request: HarmonyRequest) -> str:
        endpoint = os.getenv("BUSINESS_AGENT_LLM_ENDPOINT", self.base_url)
        if not endpoint:
            raise RuntimeError("LLM endpoint is not configured")

        url = endpoint.rstrip("/") + "/generate"
        payload: dict[str, Any] = {
            "system": request.system,
            "developer": request.developer,
            "user": request.user,
        }
        data = json.dumps(payload).encode("utf-8")
        http_request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(http_request) as response:
                body = response.read().decode("utf-8")
        except (HTTPError, URLError, OSError) as exc:  # pragma: no cover - network error
            raise RuntimeError(f"Failed to call LLM endpoint: {exc}") from exc

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid JSON response from LLM endpoint") from exc

        output = parsed.get("output")
        if output is None:
            raise RuntimeError("LLM response missing output")

        return output
