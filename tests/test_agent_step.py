from __future__ import annotations

import json
from pathlib import Path

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig


class FakeHarmonyClient:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.requests = []

    def run(self, request: object) -> str:
        self.requests.append(request)
        return self.payload


def build_agent(tmp_path: Path) -> AgentLoop:
    ip_profile = IPProfile(
        ip_name="Demo",
        essence="Test",
        visual_motifs=["m"],
        core_personality=["calm"],
        taboos=["none"],
        target_audience="operators",
        brand_promise="reliability",
        canon_examples=["ex"],
    )
    project = ProjectConfig(
        project_name="Test Project",
        goal_type="demo",
        constraints={},
        idea_templates=["template"],
        iteration_policy={"explore_ratio": 0.5},
    )
    return AgentLoop(
        base_dir=tmp_path,
        context=AgentContext(ip_profile, project),
    )


def test_process_next_task_updates_task_and_records_iteration(tmp_path: Path) -> None:
    client = FakeHarmonyClient("note from llm")
    agent = build_agent(tmp_path)

    processed = agent.process_next_task(client, mode="explore")

    assert processed is True
    tasks = agent.state_store.load_tasks()
    assert len(tasks) == 1
    assert tasks[0].status == "done"
    assert tasks[0].meta["llm_note"] == "note from llm"

    iteration = agent.state_store.latest_iteration()
    assert iteration is not None
    data = json.loads(iteration.read_text(encoding="utf-8"))
    assert data["mode"] == "explore"
