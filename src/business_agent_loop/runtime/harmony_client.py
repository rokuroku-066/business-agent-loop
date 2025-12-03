from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


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

    def run(self, request: HarmonyRequest) -> Dict[str, Any]:
        raise NotImplementedError(
            "HarmonyClient.run must be implemented once a model backend is available"
        )
