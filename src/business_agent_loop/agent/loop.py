from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from ..config import IPProfile, ProjectConfig, load_configs
from ..models import IterationLog, Task
from ..state import StateStore


@dataclass
class AgentContext:
    ip_profile: IPProfile
    project_config: ProjectConfig


class AgentLoop:
    """Coordinator for a single-iteration agent loop.

    The current implementation focuses on filesystem wiring and config loading.
    Model calls and detailed role switching will be added on top of this skeleton.
    """

    def __init__(self, base_dir: Path, context: AgentContext) -> None:
        self.base_dir = base_dir
        self.context = context
        self.state_store = StateStore(base_dir)

    @classmethod
    def from_config_dir(cls, base_dir: Path, config_dir: Path) -> "AgentLoop":
        ip_profile, project_config = load_configs(config_dir)
        return cls(base_dir, AgentContext(ip_profile, project_config))

    def initialize(self) -> None:
        self.state_store.ensure_layout()
        self._bootstrap_task_queue()

    def _bootstrap_task_queue(self) -> None:
        tasks = self.state_store.load_tasks()
        if tasks:
            return
        seed_task = Task(
            id="planner-initialize",
            type="plan",
            priority=100,
            related_idea_ids=[],
            status="ready",
            meta={"note": "Initialize task queue based on project config"},
        )
        self.state_store.save_tasks([seed_task])

    def next_task(self) -> Task | None:
        tasks = sorted(
            self.state_store.load_tasks(),
            key=lambda task: task.priority,
            reverse=True,
        )
        for task in tasks:
            if task.status == "ready":
                return task
        return None

    def record_iteration(self, task: Task | None, mode: str) -> Path:
        task_summary = task.meta.get("note") if task and task.meta else "no-op"
        iteration = IterationLog(
            iteration_id=task.id if task else "no-task",
            mode=mode,
            task_summary=task_summary,
            details={
                "project_name": self.context.project_config.project_name,
                "ip_name": self.context.ip_profile.ip_name,
            },
        )
        return self.state_store.record_iteration(iteration)

    def status(self) -> Dict[str, str | int]:
        tasks = self.state_store.load_tasks()
        latest_iteration = self.state_store.latest_iteration()
        return {
            "task_count": len(tasks),
            "ready_tasks": len([task for task in tasks if task.status == "ready"]),
            "latest_iteration": latest_iteration.name if latest_iteration else "none",
        }
