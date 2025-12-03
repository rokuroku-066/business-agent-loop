from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

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
        role = self._role_for_task(task.type)
        ip = self.context.ip_profile
        project = self.context.project_config
        constraints = ", ".join(f"{k}: {v}" for k, v in project.constraints.items())
        templates = " | ".join(project.idea_templates)
        system = (
            f"You are {ip.ip_name}, {ip.essence}. "
            f"Brand promise: {ip.brand_promise}. Avoid: {', '.join(ip.taboos)}."
        )
        developer_lines = [
            "# IP Spec",
            f"Name: {ip.ip_name}",
            f"Essence: {ip.essence}",
            f"Personality: {', '.join(ip.core_personality)}",
            f"Visual motifs: {', '.join(ip.visual_motifs)}",
            f"Taboos: {', '.join(ip.taboos)}",
            "# Project Config",
            f"Project: {project.project_name}",
            f"Goal: {project.goal_type}",
            f"Target audience: {ip.target_audience}",
            f"Constraints: {constraints}",
            f"Idea templates: {templates}",
            f"Iteration policy: {json.dumps(project.iteration_policy)}",
            "# Role",
            f"You are acting as the {role} role for this iteration.",
        ]
        developer = "\n".join(developer_lines)
        user = self._task_instructions(task, role)
        return HarmonyRequest(system=system, developer=developer, user=user)

    def run_next(self, mode: Optional[str] = None) -> Path | None:
        task = self.next_task()
        if task is None:
            return None

        resolved_mode = mode or self._select_mode()
        prompt = self.render_prompt(task)
        response = self.model_client.run(prompt)
        ideas, follow_up_tasks, summary = self._parse_model_response(response)

        if ideas:
            self.state_store.append_ideas(ideas)

        idea_history = self.state_store.load_idea_history()
        stagnation_threshold = float(
            self.context.project_config.iteration_policy.get("stagnation_threshold", 0.9)
        )
        stagnation_runs = int(
            self.context.project_config.iteration_policy.get("stagnation_runs", 3)
        )
        stagnation_tasks = []
        for idea in ideas:
            prior_history = idea_history.get(idea.id, [])
            if self._is_stalled(
                prior_history, idea.summary, threshold=stagnation_threshold, runs=stagnation_runs
            ):
                stagnation_tasks.append(self._shake_up_task(idea, prior_history))
            self.state_store.append_idea_history(idea.id, idea.summary)

        updated_tasks = self._update_tasks(task, [*follow_up_tasks, *stagnation_tasks])
        self.state_store.save_tasks(updated_tasks)

        iteration = IterationLog(
            iteration_id=task.id,
            mode=resolved_mode,
            task_summary=summary or (task.meta.get("note", "") if task.meta else ""),
            details={
                "role": self._role_for_task(task.type),
                "prompt": prompt.__dict__,
                "response": response,
            },
        )
        return self.record_iteration(iteration=iteration, task=None, mode=resolved_mode, prompt=prompt, response=response)

    def _role_for_task(self, task_type: str) -> str:
        return {
            "plan": "planner",
            "ideate": "ideator",
            "critic": "critic",
            "edit": "editor",
            "shake_up_idea": "ideator",
        }.get(task_type, "planner")

    def _task_instructions(self, task: Task, role: str) -> str:
        related = ", ".join(task.related_idea_ids) if task.related_idea_ids else "none"
        base = [f"You are acting as the {role} for this iteration."]
        related_ideas = self.state_store.load_ideas_by_ids(task.related_idea_ids)
        if related_ideas:
            base.append("## Related ideas")
            for idea in related_ideas:
                base.append(
                    " - "
                    + json.dumps(
                        {
                            "id": idea.id,
                            "title": idea.title,
                            "summary": idea.summary,
                            "tags": idea.tags,
                            "scores": {
                                "brand_fit": idea.brand_fit_score,
                                "novelty": idea.novelty_score,
                                "feasibility": idea.feasibility_score,
                            },
                        },
                        ensure_ascii=False,
                    )
                )
        if task.type == "shake_up_idea":
            recent = self.state_store.load_idea_history().get(task.related_idea_ids[0], [])
            base.append("Shake up the idea. Return JSON with keys: ideas (at least 2 divergent directions), follow_up_tasks, summary.")
            if recent:
                base.append("Recent summaries to avoid repeating:")
                for entry in recent[-3:]:
                    base.append(f" - {entry}")
            base.append("Ensure new directions differ clearly from the recent updates.")
        elif role == "planner":
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

    def _select_mode(self) -> str:
        policy = self.context.project_config.iteration_policy
        explore_ratio = float(policy.get("explore_ratio", 0.5))
        deepen_ratio = float(policy.get("deepening_ratio", 1 - explore_ratio))
        state = self._load_iteration_state()
        explore_count = state.get("explore", 0)
        deepen_count = state.get("deepen", 0)
        total = explore_count + deepen_count
        if total == 0:
            return "explore" if explore_ratio >= deepen_ratio else "deepen"
        explore_target = explore_ratio * total
        deepen_target = deepen_ratio * total
        if explore_count < explore_target:
            return "explore"
        if deepen_count < deepen_target:
            return "deepen"
        return "explore"

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

    def _shake_up_task(self, idea: IdeaRecord, history: list[str]) -> Task:
        meta = {
            "note": "Idea updates appear stalled; force different directions",
            "idea_id": idea.id,
            "recent_summaries": history[-3:],
        }
        return Task(
            id=f"shake-{idea.id}-{datetime.now(timezone.utc).strftime('%H%M%S')}",
            type="shake_up_idea",
            priority=int(idea.novelty_score * 100) if idea.novelty_score else 50,
            related_idea_ids=[idea.id],
            status="ready",
            meta=meta,
        )

    def _is_stalled(self, history: list[str], candidate: str, *, threshold: float, runs: int) -> bool:
        if runs < 2:
            runs = 2
        window = history[-(runs - 1) :] + [candidate]
        if len(window) < runs:
            return False
        similarities = [
            self._jaccard_similarity(window[i], window[i + 1]) for i in range(len(window) - 1)
        ]
        return all(score >= threshold for score in similarities)

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union)
