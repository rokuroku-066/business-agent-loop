from __future__ import annotations

import json
from pathlib import Path

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig, SearchConfig
from business_agent_loop.models import Task
from business_agent_loop.runtime.ddg_search import SearchResult


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
        context=AgentContext(ip_profile, project, SearchConfig()),
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


def test_run_next_handles_research_task(tmp_path: Path) -> None:
    response_payload = {
        "ideas": [],
        "follow_up_tasks": [
            {
                "id": "follow-1",
                "type": "plan",
                "priority": 5,
                "related_idea_ids": [],
            }
        ],
        "summary": "research complete",
    }
    client = FakeHarmonyClient(response_payload)
    agent = build_agent(tmp_path)
    agent.model_client = client

    class StubSearchClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str) -> list[SearchResult]:
            self.queries.append(query)
            return [
                SearchResult(
                    title="Alpha",
                    href="https://example.com",
                    snippet="First result",
                )
            ]

    agent.search_client = StubSearchClient()  # type: ignore[assignment]
    agent.state_store.ensure_layout()
    agent.state_store.save_tasks(
        [
            Task(
                id="research-1",
                type="research",
                priority=3,
                related_idea_ids=[],
                status="ready",
                meta={"query": "latest market"},
            )
        ]
    )

    iteration_path = agent.run_next()

    assert iteration_path is not None and iteration_path.exists()
    tasks = agent.state_store.load_tasks()
    research_task = next(task for task in tasks if task.id == "research-1")
    assert research_task.status == "done"
    assert research_task.meta is not None
    assert research_task.meta.get("search_hits")[0]["href"] == "https://example.com"
    assert any(task.id == "follow-1" for task in tasks)
    assert agent.search_client.queries == ["latest market"]
    assert client.requests and client.requests[0].context is not None
    assert client.requests[0].context.get("search_hits")
