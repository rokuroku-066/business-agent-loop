from __future__ import annotations

import json
from pathlib import Path

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
        iteration_policy={
            "explore_ratio": 0.5,
            "deepening_ratio": 0.5,
            "stagnation_threshold": 0.6,
            "stagnation_runs": 2,
        },
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


def test_run_next_initializes_layout_and_bootstraps_tasks(tmp_path: Path) -> None:
    response_payload = {
        "ideas": [
            {
                "id": "idea-1",
                "title": "Test idea",
                "summary": "Initial summary",
                "target_audience": "operators",
                "value_proposition": "value",
                "revenue_model": "subscription",
                "brand_fit_score": 0.8,
                "novelty_score": 0.7,
                "feasibility_score": 0.6,
                "status": "draft",
                "tags": ["demo"],
            }
        ],
        "follow_up_tasks": [],
        "summary": "Ran exploration",
    }
    client = FakeHarmonyClient(response_payload)
    agent = build_agent(tmp_path)
    agent.model_client = client

    iteration_path = agent.run_next(mode="explore")

    assert iteration_path is not None
    assert iteration_path.exists()

    tasks = agent.state_store.load_tasks()
    assert tasks and tasks[0].status == "done"

    history = agent.state_store.load_idea_history()
    assert history.get("idea-1") == ["Initial summary"]

    ideas_log = (tmp_path / "ideas" / "ideas.jsonl").read_text(encoding="utf-8")
    assert "Test idea" in ideas_log
