import json
from pathlib import Path

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
        "iteration_policy": {"token_limit": 10},
    }

    (config_dir / "ip_profile.json").write_text(json.dumps(ip_profile), encoding="utf-8")
    (config_dir / "project_config.json").write_text(
        json.dumps(project_config), encoding="utf-8"
    )

    ip, project = config.load_configs(config_dir)

    assert ip.ip_name == "Test IP"
    assert project.project_name == "Demo"
