from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

__all__ = ["IdeaRecord", "Task", "IterationLog"]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IdeaRecord:
    id: str
    title: str
    summary: str
    target_audience: str
    value_proposition: str
    revenue_model: str
    brand_fit_score: float
    novelty_score: float
    feasibility_score: float
    status: str
    tags: list[str]
    created_at: str = field(default_factory=_utc_iso)
    updated_at: str = field(default_factory=_utc_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IdeaRecord":
        return cls(**data)


@dataclass
class Task:
    id: str
    type: str
    priority: int
    related_idea_ids: list[str]
    status: str
    created_at: str = field(default_factory=_utc_iso)
    last_run_at: Optional[str] = None
    meta: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(**data)


@dataclass
class IterationLog:
    iteration_id: str
    mode: str
    task_summary: str
    created_at: str = field(default_factory=_utc_iso)
    details: Dict[str, Any] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IterationLog":
        return cls(**data)
