import json
from pathlib import Path

import pytest

from business_agent_loop import config


def test_load_configs(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    ip_profile = {
        "ip_name": "Test IP",
        "essence": "Core essence",
        "visual_motifs": ["m1"],
        "core_personality": ["calm"],
        "taboos": ["none"],
        "target_audience": "humans",
        "brand_promise": "clarity",
        "canon_examples": ["ex1"],
    }
    project_config = {
        "project_name": "Demo",
        "goal_type": "testing",
        "constraints": {"budget": "low"},
        "idea_templates": ["template"],
        "iteration_policy": {
            "token_limit": 10,
            "explore_ratio": 0.5,
            "deepening_ratio": 0.5,
            "stagnation_threshold": 0.6,
            "stagnation_runs": 2,
        },
    }
    search_config = {
        "backend": "duckduckgo",
        "region": "jp-jp",
        "safesearch": "strict",
        "max_results": 3,
        "timeout": 8,
    }

    (config_dir / "ip_profile.json").write_text(json.dumps(ip_profile), encoding="utf-8")
    (config_dir / "project_config.json").write_text(
        json.dumps(project_config), encoding="utf-8"
    )
    (config_dir / "search.json").write_text(json.dumps(search_config), encoding="utf-8")

    ip, project, search = config.load_configs(config_dir)

    assert ip.ip_name == "Test IP"
    assert project.project_name == "Demo"
    assert search.region == "jp-jp"
    assert search.max_results == 3


def test_validate_configs_checks_ratios(tmp_path: Path) -> None:
    ip_profile = config.IPProfile(
        ip_name="Test IP",
        essence="essence",
        visual_motifs=["m1"],
        core_personality=["calm"],
        taboos=["none"],
        target_audience="humans",
        brand_promise="clarity",
        canon_examples=["ex"],
    )
    project = config.ProjectConfig(
        project_name="Demo",
        goal_type="testing",
        constraints={"budget": "low"},
        idea_templates=["template"],
        iteration_policy={
            "explore_ratio": 0.7,
            "deepening_ratio": 0.2,
            "stagnation_threshold": 0.5,
            "stagnation_runs": 2,
        },
    )

    with pytest.raises(ValueError):
        config.validate_configs(ip_profile, project)
