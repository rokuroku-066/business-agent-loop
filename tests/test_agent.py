import json
from pathlib import Path

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.agent.policies.mode_selection import ModeSelector
from business_agent_loop.config import IPProfile, ProjectConfig
from business_agent_loop.models import IdeaRecord, Task


class FakeHarmonyClient:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requests = []

    def run(self, request: object) -> object:
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
        iteration_policy={"explore_ratio": 0.5, "stagnation_threshold": 0.2},
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


def test_prompts_require_json_for_critic_and_editor(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    critic_task = Task(
        id="critic-1",
        type="critic",
        priority=5,
        related_idea_ids=[],
        status="ready",
    )
    editor_task = Task(
        id="edit-1",
        type="edit",
        priority=5,
        related_idea_ids=["idea-1"],
        status="ready",
    )

    critic_prompt = agent.render_prompt(critic_task)
    editor_prompt = agent.render_prompt(editor_task)

    assert "JSONで返却" in critic_prompt.user
    assert "JSONで返却" in editor_prompt.user


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


def test_run_next_handles_plain_text_response(tmp_path: Path) -> None:
    client = FakeHarmonyClient("finished")
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
    assert data["task_summary"] == "finished"
    tasks = agent.state_store.load_tasks()
    assert any(task.id == "critic-1" and task.status == "done" for task in tasks)


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


def test_related_ideas_are_embedded_in_prompts(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    agent.state_store.ensure_layout()
    idea = IdeaRecord(
        id="idea-ctx",
        title="Context idea",
        summary="Reusable context block",
        target_audience="operators",
        value_proposition="helps testing",
        revenue_model="subscription",
        brand_fit_score=0.9,
        novelty_score=0.4,
        feasibility_score=0.8,
        status="idea",
        tags=["ops"],
    )
    agent.state_store.append_ideas([idea])
    task = Task(
        id="critic-ctx",
        type="critic",
        priority=10,
        related_idea_ids=[idea.id],
        status="ready",
    )

    prompt = agent.render_prompt(task)

    assert idea.summary in prompt.user
    assert idea.id in prompt.user


def test_stalled_idea_triggers_shake_up_task(tmp_path: Path) -> None:
    payload = {
        "ideas": [
            {
                "id": "idea-stall",
                "title": "Repeating",
                "summary": "same update",
                "target_audience": "operators",
                "value_proposition": "keeps repeating",
                "revenue_model": "subscription",
                "brand_fit_score": 0.7,
                "novelty_score": 0.5,
                "feasibility_score": 0.8,
                "status": "idea",
                "tags": ["ops"],
            }
        ],
        "follow_up_tasks": [],
        "summary": "looping",
    }
    client = FakeHarmonyClient(payload)
    agent = build_agent(tmp_path, model_client=client)
    agent.state_store.ensure_layout()
    agent.state_store.append_idea_history("idea-stall", "same update")
    agent.state_store.append_idea_history("idea-stall", "same update")
    agent.state_store.save_tasks(
        [
            Task(
                id="edit-1",
                type="edit",
                priority=5,
                related_idea_ids=["idea-stall"],
                status="ready",
            )
        ]
    )

    agent.run_next()

    tasks = agent.state_store.load_tasks()
    assert any(task.type == "shake_up_idea" for task in tasks)


def test_stalled_detection_requires_configured_run_count(tmp_path: Path) -> None:
    payload = {
        "ideas": [
            {
                "id": "idea-slow",
                "title": "Slow repeat",
                "summary": "nearly same",
                "target_audience": "operators",
                "value_proposition": "keeps repeating",
                "revenue_model": "subscription",
                "brand_fit_score": 0.7,
                "novelty_score": 0.5,
                "feasibility_score": 0.8,
                "status": "idea",
                "tags": ["ops"],
            }
        ],
        "follow_up_tasks": [],
        "summary": "looping",
    }
    client = FakeHarmonyClient(payload)
    agent = build_agent(tmp_path, model_client=client)
    agent.context.project_config.iteration_policy["stagnation_runs"] = 4
    agent.state_store.ensure_layout()
    agent.state_store.append_idea_history("idea-slow", "nearly same")
    agent.state_store.append_idea_history("idea-slow", "nearly same")
    agent.state_store.save_tasks(
        [
            Task(
                id="edit-2",
                type="edit",
                priority=5,
                related_idea_ids=["idea-slow"],
                status="ready",
            )
        ]
    )

    agent.run_next()

    tasks = agent.state_store.load_tasks()
    assert not any(task.type == "shake_up_idea" for task in tasks)


def test_mode_selection_balances_explore_and_deepen(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    agent.state_store.ensure_layout()
    agent.state_store.iteration_state_file.write_text(
        json.dumps({"explore": 5, "deepen": 0}), encoding="utf-8"
    )

    state = agent._load_iteration_state()
    selector = ModeSelector()
    assert selector.select_mode(state, agent.context.project_config.iteration_policy) == "deepen"
