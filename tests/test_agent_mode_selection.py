import json
from pathlib import Path

import pytest

from business_agent_loop.agent.loop import AgentContext, AgentLoop
from business_agent_loop.agent.policies.mode_selection import ModeSelector
from business_agent_loop.config import IPProfile, ProjectConfig, SearchConfig



def build_agent(tmp_path: Path, *, explore_ratio: float, deepening_ratio: float) -> AgentLoop:
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
            "explore_ratio": explore_ratio,
            "deepening_ratio": deepening_ratio,
        },
    )
    return AgentLoop(
        base_dir=tmp_path,
        context=AgentContext(ip_profile, project, SearchConfig()),
    )


def test_select_mode_honors_iteration_policy_ratios(tmp_path: Path) -> None:
    agent = build_agent(tmp_path, explore_ratio=0.7, deepening_ratio=0.3)
    agent.state_store.ensure_layout()
    selector = ModeSelector()

    scenarios = [
        ({"explore": 2, "deepen": 0}, "deepen"),
        ({"explore": 1, "deepen": 2}, "explore"),
        ({"explore": 3, "deepen": 1}, "deepen"),
    ]

    for iteration_state, expected_mode in scenarios:
        agent.state_store.iteration_state_file.write_text(
            json.dumps(iteration_state, ensure_ascii=False),
            encoding="utf-8",
        )
        state = agent._load_iteration_state()
        assert (
            selector.select_mode(state, agent.context.project_config.iteration_policy)
            == expected_mode
        )


def test_corrupted_iteration_state_defaults_to_explore(tmp_path: Path) -> None:
    agent = build_agent(tmp_path, explore_ratio=0.6, deepening_ratio=0.4)
    agent.state_store.ensure_layout()
    selector = ModeSelector()

    agent.state_store.iteration_state_file.write_text("{not: json", encoding="utf-8")

    assert agent._load_iteration_state() == {}
    assert selector.select_mode({}, agent.context.project_config.iteration_policy) == "explore"


def test_missing_deepening_ratio_is_error(tmp_path: Path) -> None:
    agent = build_agent(tmp_path, explore_ratio=0.6, deepening_ratio=0.4)
    selector = ModeSelector()
    with pytest.raises(ValueError):
        selector.select_mode({}, {"explore_ratio": 0.6})
