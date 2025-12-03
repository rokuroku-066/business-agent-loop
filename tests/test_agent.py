from pathlib import Path

import json

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig
from business_agent_loop.models import Task


class FakeHarmonyClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []

    def run(self, request: object) -> dict:
        self.requests.append(request)
        return self.payload


def build_agent(tmp_path: Path, model_client: object | None = None) -> AgentLoop:
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
        model_client=model_client,
    )


def test_agent_initializes_and_records(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    agent.initialize()

    status = agent.status()
    assert status["task_count"] == 1
    assert status["ready_tasks"] == 1

    task = agent.next_task()
    path = agent.record_iteration(task=task, mode="explore")
    assert path.exists()
    updated_status = agent.status()
    assert "iteration" in updated_status["latest_iteration"]


def test_prompt_construction_for_planner(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    task = Task(
        id="plan-1",
        type="plan",
        priority=10,
        related_idea_ids=[],
        status="ready",
        meta={"note": "seed"},
    )
    request = agent.render_prompt(task)
    assert "Demo" in request.system
    assert "planner" in request.developer
    assert "seed" in request.user


def test_run_next_updates_tasks_and_persists_ideas(tmp_path: Path) -> None:
    payload = {
        "ideas": [
            {
                "id": "idea-1",
                "title": "Automation helper",
                "summary": "Assist operators",
                "target_audience": "operators",
                "value_proposition": "Saves time",
                "revenue_model": "subscription",
                "brand_fit_score": 0.8,
                "novelty_score": 0.6,
                "feasibility_score": 0.9,
                "status": "draft",
                "tags": ["ops"],
            }
        ],
        "follow_up_tasks": [
            {
                "id": "ideate-1",
                "type": "ideate",
                "priority": 5,
                "related_idea_ids": ["idea-1"],
            }
        ],
        "summary": "initial exploration",
    }
    client = FakeHarmonyClient(payload)
    agent = build_agent(tmp_path, model_client=client)
    agent.state_store.ensure_layout()
    agent.state_store.save_tasks(
        [
            Task(
                id="plan-1",
                type="plan",
                priority=10,
                related_idea_ids=[],
                status="ready",
                meta={"note": "seed"},
            )
        ]
    )

    path = agent.run_next()
    assert path is not None and path.exists()
    tasks = agent.state_store.load_tasks()
    assert any(task.id == "plan-1" and task.status == "done" for task in tasks)
    assert any(task.id == "ideate-1" and task.status == "ready" for task in tasks)

    idea_file = tmp_path / "ideas" / "ideas.jsonl"
    content = idea_file.read_text(encoding="utf-8")
    assert "idea-1" in content


def test_iteration_logging_includes_prompt_and_response(tmp_path: Path) -> None:
    payload = {"summary": "completed"}
    client = FakeHarmonyClient(payload)
    agent = build_agent(tmp_path, model_client=client)
    agent.state_store.ensure_layout()
    agent.state_store.save_tasks(
        [
            Task(
                id="critic-1",
                type="critic",
                priority=1,
                related_idea_ids=[],
                status="ready",
            )
        ]
    )

    path = agent.run_next()
    assert path is not None and path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["details"]["response"]["summary"] == "completed"
    assert "prompt" in data["details"]
