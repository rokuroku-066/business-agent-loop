from __future__ import annotations

import json
from typing import Iterable, TYPE_CHECKING

from ...models import IdeaRecord, Task
from ...runtime.harmony_client import HarmonyRequest

if TYPE_CHECKING:
    from ..loop import AgentContext


class PromptBuilder:
    ROLE_MAP = {
        "plan": "planner",
        "ideate": "ideator",
        "critic": "critic",
        "edit": "editor",
        "shake_up_idea": "ideator",
    }

    def __init__(self, context: "AgentContext") -> None:
        self.context = context

    def role_for_task(self, task_type: str) -> str:
        return self.ROLE_MAP.get(task_type, "planner")

    def build(
        self,
        task: Task,
        *,
        related_ideas: Iterable[IdeaRecord] = (),
        recent_summaries: list[str] | None = None,
    ) -> HarmonyRequest:
        role = self.role_for_task(task.type)
        system = self._system_prompt()
        developer = self._developer_prompt(role)
        user = self._task_instructions(task, role, related_ideas, recent_summaries)
        return HarmonyRequest(system=system, developer=developer, user=user)

    def _system_prompt(self) -> str:
        ip = self.context.ip_profile
        return (
            f"You are {ip.ip_name}, {ip.essence}. "
            f"Brand promise: {ip.brand_promise}. Avoid: {', '.join(ip.taboos)}."
        )

    def _developer_prompt(self, role: str) -> str:
        ip = self.context.ip_profile
        project = self.context.project_config
        constraints = ", ".join(f"{k}: {v}" for k, v in project.constraints.items())
        templates = " | ".join(project.idea_templates)
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
        return "\n".join(developer_lines)

    def _task_instructions(
        self,
        task: Task,
        role: str,
        related_ideas: Iterable[IdeaRecord],
        recent_summaries: list[str] | None,
    ) -> str:
        related = ", ".join(task.related_idea_ids) if task.related_idea_ids else "none"
        base = [f"You are acting as the {role} for this iteration."]
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
            base.append(
                "Shake up the idea. Return JSON with keys: ideas (at least 2 divergent directions), "
                "follow_up_tasks, summary."
            )
            if recent_summaries:
                base.append("Recent summaries to avoid repeating:")
                for entry in recent_summaries[-3:]:
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
