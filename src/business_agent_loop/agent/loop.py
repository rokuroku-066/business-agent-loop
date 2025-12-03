from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable

from ..config import IPProfile, ProjectConfig, load_configs
from ..models import IdeaRecord, IterationLog, Task
from ..runtime.harmony_client import HarmonyClient, HarmonyRequest
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

    def __init__(
        self,
        base_dir: Path,
        context: AgentContext,
        model_client: HarmonyClient | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.context = context
        self.state_store = StateStore(base_dir)
        self.model_client = model_client or HarmonyClient()

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

    def render_prompt(self, task: Task) -> HarmonyRequest:
        role = self._role_for_task(task.type)
        ip = self.context.ip_profile
        project = self.context.project_config
        constraints = ", ".join(f"{k}: {v}" for k, v in project.constraints.items())
        templates = " | ".join(project.idea_templates)
        system = (
            f"You are {ip.ip_name}, {ip.essence}. "
            f"Brand promise: {ip.brand_promise}. Avoid: {', '.join(ip.taboos)}."
        )
        developer = (
            f"Project: {project.project_name}. Goal: {project.goal_type}. "
            f"Target audience: {ip.target_audience}. Role: {role}. "
            f"Constraints: {constraints}. Templates: {templates}."
        )
        user = self._task_instructions(task, role)
        return HarmonyRequest(system=system, developer=developer, user=user)

    def run_next(self) -> Path | None:
        task = self.next_task()
        if task is None:
            return None

        prompt = self.render_prompt(task)
        response = self.model_client.run(prompt)
        ideas, follow_up_tasks, summary = self._parse_model_response(response)

        if ideas:
            self.state_store.append_ideas(ideas)

        updated_tasks = self._update_tasks(task, follow_up_tasks)
        self.state_store.save_tasks(updated_tasks)

        iteration = IterationLog(
            iteration_id=task.id,
            mode=task.type,
            task_summary=summary or (task.meta.get("note", "") if task.meta else ""),
            details={
                "role": self._role_for_task(task.type),
                "prompt": prompt.__dict__,
                "response": response,
            },
        )
        return self.state_store.record_iteration(iteration)

    def _role_for_task(self, task_type: str) -> str:
        return {
            "plan": "planner",
            "ideate": "ideator",
            "critic": "critic",
            "edit": "editor",
        }.get(task_type, "planner")

    def _task_instructions(self, task: Task, role: str) -> str:
        related = ", ".join(task.related_idea_ids) if task.related_idea_ids else "none"
        base = [f"You are acting as the {role} for this iteration."]
        if role == "planner":
            base.append(
                "Propose follow-up tasks to progress the project. Return JSON with"
                " keys: follow_up_tasks (list), summary."
            )
        elif role == "ideator":
            base.append(
                "Generate business ideas following the provided templates."
                " Return JSON with keys: ideas (list of idea records),"
                " follow_up_tasks, summary."
            )
        elif role == "critic":
            base.append(
                "Review existing ideas and suggest improvements. Return JSON with"
                " keys: ideas (optional list of revisions), follow_up_tasks (list),"
                " summary."
            )
        elif role == "editor":
            base.append(
                "Polish selected ideas and mark readiness. Return JSON with keys:"
                " ideas (list), follow_up_tasks (optional list), summary."
            )
        if task.meta:
            base.append(f"Task note: {json.dumps(task.meta)}")
        base.append(f"Related ideas: {related}")
        return "\n".join(base)

    def _parse_model_response(
        self, response: object
    ) -> tuple[list[IdeaRecord], list[Task], str]:
        if not isinstance(response, Dict):
            return [], [], str(response)

        ideas = [self._idea_from_payload(payload) for payload in response.get("ideas", [])]
        follow_up_tasks = [
            self._task_from_payload(payload) for payload in response.get("follow_up_tasks", [])
        ]
        summary = response.get("summary", "")
        return ideas, follow_up_tasks, str(summary)

    def _task_from_payload(self, payload: Dict[str, object]) -> Task:
        defaults = {
            "priority": 50,
            "related_idea_ids": [],
            "status": "ready",
            "meta": {},
        }
        hydrated: Dict[str, object] = {**defaults, **payload}
        return Task.from_dict(hydrated)

    def _idea_from_payload(self, payload: Dict[str, object]) -> IdeaRecord:
        return IdeaRecord.from_dict(payload)

    def _update_tasks(
        self, current_task: Task, new_tasks: Iterable[Task]
    ) -> list[Task]:
        tasks = self.state_store.load_tasks()
        now = datetime.now(timezone.utc).isoformat()
        updated: list[Task] = []
        for task in tasks:
            if task.id == current_task.id:
                task.status = "done"
                task.last_run_at = now
                if task.meta is None:
                    task.meta = {}
                task.meta["last_result"] = "completed"
            updated.append(task)
        updated.extend(new_tasks)
        return updated

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
