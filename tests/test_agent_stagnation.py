from pathlib import Path

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig
from business_agent_loop.models import Task


class FakeHarmonyClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def run(self, request: object) -> object:  # pragma: no cover - trivial passthrough
        return self.payload


def build_agent(tmp_path: Path, payload: object) -> AgentLoop:
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
            "stagnation_threshold": 0.6,
            "stagnation_runs": 3,
        },
    )
    client = FakeHarmonyClient(payload)
    return AgentLoop(
        base_dir=tmp_path,
        context=AgentContext(ip_profile, project),
        model_client=client,
    )


def seed_ready_task(agent: AgentLoop) -> None:
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


def test_stagnation_triggers_shake_up_task(tmp_path: Path) -> None:
    idea_id = "idea-stall"
    history = [
        "Assistant automates report drafting for operators",
        "Assistant automates report drafting for busy operators",
    ]
    response = {
        "ideas": [
            {
                "id": idea_id,
                "title": "Report helper",
                "summary": "Assistant automates report drafting for operators",
                "target_audience": "operators",
                "value_proposition": "Saves time",
                "revenue_model": "subscription",
                "brand_fit_score": 0.8,
                "novelty_score": 0.73,
                "feasibility_score": 0.9,
                "status": "draft",
                "tags": ["ops"],
            }
        ],
        "follow_up_tasks": [],
        "summary": "incremental update",
    }
    agent = build_agent(tmp_path, response)
    agent.state_store.ensure_layout()
    for entry in history:
        agent.state_store.append_idea_history(idea_id, entry)
    seed_ready_task(agent)

    assert agent.stagnation_policy.is_stalled(
        history, response["ideas"][0]["summary"], threshold=0.6, runs=3
    )

    agent.run_next(mode="explore")

    tasks = agent.state_store.load_tasks()
    shake_tasks = [task for task in tasks if task.type == "shake_up_idea"]
    assert len(shake_tasks) == 1
    shake_task = shake_tasks[0]
    assert shake_task.meta is not None
    assert shake_task.meta.get("idea_id") == idea_id
    assert shake_task.meta.get("recent_summaries") == history[-3:]
    assert shake_task.priority == 73
    assert shake_task.related_idea_ids == [idea_id]


def test_diverse_history_skips_shake_up(tmp_path: Path) -> None:
    idea_id = "idea-fresh"
    diverse_history = [
        "Build a marketplace for local artisans",
        "Create an API for supply chain tracking",
    ]
    response = {
        "ideas": [
            {
                "id": idea_id,
                "title": "Energy dashboard",
                "summary": "Dashboard visualizes renewable energy usage trends",
                "target_audience": "operators",
                "value_proposition": "Visibility",
                "revenue_model": "subscription",
                "brand_fit_score": 0.7,
                "novelty_score": 0.6,
                "feasibility_score": 0.8,
                "status": "draft",
                "tags": ["energy"],
            }
        ],
        "follow_up_tasks": [],
        "summary": "new direction",
    }
    agent = build_agent(tmp_path, response)
    agent.state_store.ensure_layout()
    for entry in diverse_history:
        agent.state_store.append_idea_history(idea_id, entry)
    seed_ready_task(agent)

    assert not agent.stagnation_policy.is_stalled(
        diverse_history, response["ideas"][0]["summary"], threshold=0.6, runs=3
    )

    agent.run_next(mode="explore")

    tasks = agent.state_store.load_tasks()
    assert not any(task.type == "shake_up_idea" for task in tasks)
