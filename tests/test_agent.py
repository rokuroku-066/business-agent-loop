from pathlib import Path

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig


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
    return AgentLoop(base_dir=tmp_path, context=AgentContext(ip_profile, project))


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
