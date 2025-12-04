from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..config import IPProfile, ProjectConfig, load_configs, validate_configs
from ..models import IdeaRecord, IterationLog, Task
from ..runtime.harmony_client import HarmonyClient, HarmonyRequest
from ..storage import StateStore
from .policies.mode_selection import ModeSelector
from .policies.stagnation import StagnationPolicy
from .prompts.builder import PromptBuilder


logger = logging.getLogger(__name__)


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
        prompt_builder: PromptBuilder | None = None,
        mode_selector: ModeSelector | None = None,
        stagnation_policy: StagnationPolicy | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.context = context
        self.state_store = StateStore(base_dir)
        self.model_client = model_client or HarmonyClient()
        self.prompt_builder = prompt_builder or PromptBuilder(context)
        self.mode_selector = mode_selector or ModeSelector()
        self.stagnation_policy = stagnation_policy or StagnationPolicy()

    @classmethod
    def from_config_dir(cls, base_dir: Path, config_dir: Path) -> "AgentLoop":
        ip_profile, project_config = load_configs(config_dir)
        validate_configs(ip_profile, project_config)
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

    def process_next_task(self, client: HarmonyClient, mode: str = "explore") -> bool:
        self.initialize()
        task = self.next_task()
        if task is None:
            return False

        request = self.render_prompt(task)
        result = client.run(request)

        if task.meta is None:
            task.meta = {}
        task.meta["llm_note"] = result
        task.status = "done"

        updated_tasks: list[Task] = []
        for existing in self.state_store.load_tasks():
            if existing.id == task.id:
                existing.status = task.status
                existing.meta = task.meta
            updated_tasks.append(existing)
        self.state_store.save_tasks(updated_tasks)

        self.record_iteration(task, mode=mode, prompt=request, response=result)
        return True

    def render_prompt(self, task: Task) -> HarmonyRequest:
        related_ideas = self.state_store.load_ideas_by_ids(task.related_idea_ids)
        recent_history: list[str] | None = None
        if task.type == "shake_up_idea" and task.related_idea_ids:
            idea_history = self.state_store.load_idea_history()
            recent_history = idea_history.get(task.related_idea_ids[0], [])[-3:]
        return self.prompt_builder.build(
            task,
            related_ideas=related_ideas,
            recent_summaries=recent_history,
        )

    def run_next(self, mode: Optional[str] = None) -> Path | None:
        self.initialize()
        task = self.next_task()
        if task is None:
            return None

        iteration_state = self._load_iteration_state()
        resolved_mode = mode or self.mode_selector.select_mode(
            iteration_state, self.context.project_config.iteration_policy
        )
        prompt = self.render_prompt(task)
        response = self.model_client.run(prompt)
        ideas, follow_up_tasks, summary = self._parse_model_response(response)

        if ideas:
            self.state_store.append_ideas(ideas)

        idea_history = self.state_store.load_idea_history()
        iteration_policy = self.context.project_config.iteration_policy
        stagnation_threshold = float(iteration_policy["stagnation_threshold"])
        stagnation_runs = int(iteration_policy["stagnation_runs"])
        stagnation_tasks = []
        for idea in ideas:
            prior_history = idea_history.get(idea.id, [])
            if self.stagnation_policy.is_stalled(
                prior_history, idea.summary, threshold=stagnation_threshold, runs=stagnation_runs
            ):
                stagnation_tasks.append(
                    self.stagnation_policy.create_shake_up_task(idea, prior_history)
                )
            self.state_store.append_idea_history(idea.id, idea.summary)

        updated_tasks = self._update_tasks(task, [*follow_up_tasks, *stagnation_tasks])
        self.state_store.save_tasks(updated_tasks)

        iteration = IterationLog(
            iteration_id=task.id,
            mode=resolved_mode,
            task_summary=summary or (task.meta.get("note", "") if task.meta else ""),
            details={
                "role": self.prompt_builder.role_for_task(task.type),
                "prompt": prompt.__dict__,
                "response": response,
            },
        )
        return self.record_iteration(iteration=iteration, task=None, mode=resolved_mode, prompt=prompt, response=response)

    def _parse_model_response(
        self, response: object
    ) -> tuple[list[IdeaRecord], list[Task], str]:
        payload: Dict[str, object]
        if isinstance(response, str):
            try:
                payload = json.loads(response)
            except json.JSONDecodeError as exc:
                logger.error("Model response is out of spec: not JSON")
                raise ValueError("Model response must be valid JSON") from exc
        elif isinstance(response, Dict):
            payload = response
        else:
            logger.error(
                "Model response is out of spec: expected JSON object, got %s",
                type(response).__name__,
            )
            raise ValueError("Model response must be a JSON object")

        required_keys = ("ideas", "follow_up_tasks", "summary")
        missing = [key for key in required_keys if key not in payload]
        if missing:
            logger.error(
                "Model response is out of spec: missing keys %s", ", ".join(missing)
            )
            raise ValueError(f"Model response missing keys: {', '.join(missing)}")

        ideas_raw = payload.get("ideas")
        follow_up_raw = payload.get("follow_up_tasks")
        summary = payload.get("summary")

        if not isinstance(ideas_raw, list) or not isinstance(follow_up_raw, list):
            logger.error(
                "Model response is out of spec: ideas and follow_up_tasks must be lists"
            )
            raise ValueError("ideas and follow_up_tasks must be lists")
        if not isinstance(summary, str):
            logger.error(
                "Model response is out of spec: summary must be a string"
            )
            raise ValueError("summary must be a string")

        ideas = [self._idea_from_payload(payload) for payload in ideas_raw]
        follow_up_tasks = [self._task_from_payload(payload) for payload in follow_up_raw]
        return ideas, follow_up_tasks, summary

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

    def record_iteration(
        self,
        task: Task | None = None,
        mode: str = "explore",
        prompt: HarmonyRequest | None = None,
        response: object | None = None,
        iteration: IterationLog | None = None,
    ) -> Path:
        if iteration is None:
            task_summary = task.meta.get("note") if task and task.meta else "no-op"
            iteration = IterationLog(
                iteration_id=task.id if task else "no-task",
                mode=mode,
                task_summary=task_summary,
                details={
                    "project_name": self.context.project_config.project_name,
                    "ip_name": self.context.ip_profile.ip_name,
                    "prompt": prompt.__dict__ if prompt else None,
                    "response": response,
                },
            )
        state = self._load_iteration_state()
        state[mode] = state.get(mode, 0) + 1
        self._save_iteration_state(state)
        return self.state_store.record_iteration(iteration)

    def status(self) -> Dict[str, str | int]:
        tasks = self.state_store.load_tasks()
        latest_iteration = self.state_store.latest_iteration()
        return {
            "task_count": len(tasks),
            "ready_tasks": len([task for task in tasks if task.status == "ready"]),
            "latest_iteration": latest_iteration.name if latest_iteration else "none",
        }

    def _load_iteration_state(self) -> Dict[str, int]:
        if not self.state_store.iteration_state_file.exists():
            return {}
        try:
            data = json.loads(self.state_store.iteration_state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return {k: int(v) for k, v in data.items()}

    def _save_iteration_state(self, state: Dict[str, int]) -> None:
        self.state_store.iteration_state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
