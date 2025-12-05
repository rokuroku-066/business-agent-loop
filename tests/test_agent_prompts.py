import json
from pathlib import Path

import json

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.config import IPProfile, ProjectConfig, SearchConfig
from business_agent_loop.models import IdeaRecord, Task
from business_agent_loop.runtime.ddg_search import SearchResult


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
            "stagnation_threshold": 0.2,
            "stagnation_runs": 2,
        },
    )
    return AgentLoop(
        base_dir=tmp_path, context=AgentContext(ip_profile, project, SearchConfig())
    )


def test_prompts_include_related_idea_details(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    agent.state_store.ensure_layout()
    idea = IdeaRecord(
        id="idea-1",
        title="Sample idea",
        summary="A concise idea summary",
        target_audience="builders",
        value_proposition="Saves effort",
        revenue_model="subscription",
        brand_fit_score=0.7,
        novelty_score=0.6,
        feasibility_score=0.8,
        status="draft",
        tags=["ops", "automation"],
    )
    agent.state_store.append_ideas([idea])

    task = Task(
        id="critic-idea",
        type="critic",
        priority=5,
        related_idea_ids=[idea.id],
        status="ready",
        meta={"note": "review"},
    )

    prompt = agent.render_prompt(task)

    assert "## 関連アイデア" in prompt.user
    assert f'"id": "{idea.id}"' in prompt.user
    assert json.dumps(idea.title) in prompt.user
    assert "関連アイデア: idea-1" in prompt.user


def test_shake_up_prompt_lists_recent_summaries(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)
    agent.state_store.ensure_layout()
    idea = IdeaRecord(
        id="idea-2",
        title="Another idea",
        summary="Original concept",
        target_audience="operators",
        value_proposition="Adds insights",
        revenue_model="usage",
        brand_fit_score=0.6,
        novelty_score=0.4,
        feasibility_score=0.9,
        status="draft",
        tags=["analysis"],
    )
    agent.state_store.append_ideas([idea])

    history = ["First", "Second", "Third", "Fourth"]
    for summary in history:
        agent.state_store.append_idea_history(idea.id, summary)

    task = Task(
        id="shake-1",
        type="shake_up_idea",
        priority=1,
        related_idea_ids=[idea.id],
        status="ready",
    )

    prompt = agent.render_prompt(task)

    assert "アイデアを揺さぶってください。JSONで返却" in prompt.user
    assert "重複を避けるための最近のサマリー:" in prompt.user
    assert "Second" in prompt.user
    assert "Third" in prompt.user
    assert "Fourth" in prompt.user
    assert "First" not in prompt.user
    assert "新しい方向性が最近の更新と明確に異なるようにしてください。" in prompt.user

def test_research_prompt_includes_evidence(tmp_path: Path) -> None:
    agent = build_agent(tmp_path)

    class FakeSearchClient:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def search(self, query: str) -> list[SearchResult]:
            self.queries.append(query)
            return [
                SearchResult(
                    title="Result A", href="https://example.com", snippet="Summary A"
                )
            ]

    agent.search_client = FakeSearchClient()  # type: ignore[assignment]
    task = Task(
        id="research-1",
        type="research",
        priority=5,
        related_idea_ids=[],
        status="ready",
        meta={"query": "sample topic"},
    )

    prompt = agent.render_prompt(task)

    assert "外部リサーチ結果" in prompt.user
    assert "Result A" in prompt.user
    assert prompt.context is not None
    assert prompt.context.get("search_hits")
    assert agent.search_client.queries == ["sample topic"]
    assert task.meta is not None and "search_hits" in task.meta
