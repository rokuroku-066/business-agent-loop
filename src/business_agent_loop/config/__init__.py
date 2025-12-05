from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

__all__ = [
    "IPProfile",
    "ProjectConfig",
    "SearchConfig",
    "load_ip_profile",
    "load_project_config",
    "load_search_config",
    "load_configs",
    "validate_configs",
]


@dataclass
class IPProfile:
    ip_name: str
    essence: str
    visual_motifs: list[str]
    core_personality: list[str]
    taboos: list[str]
    target_audience: str
    brand_promise: str
    canon_examples: list[str]


@dataclass
class ProjectConfig:
    project_name: str
    goal_type: str
    constraints: Dict[str, str]
    idea_templates: list[str]
    iteration_policy: Dict[str, Any]


@dataclass
class SearchConfig:
    backend: str = "duckduckgo"
    region: str = "wt-wt"
    safesearch: str = "moderate"
    max_results: int = 5
    timeout: int = 10
    proxy: str | None = None


def load_ip_profile(path: Path) -> IPProfile:
    with path.open("r", encoding="utf-8") as file:
        content = json.load(file)
    return IPProfile(**content)


def load_project_config(path: Path) -> ProjectConfig:
    with path.open("r", encoding="utf-8") as file:
        content = json.load(file)
    return ProjectConfig(**content)


def load_search_config(path: Path) -> SearchConfig:
    if not path.exists():
        return SearchConfig()
    with path.open("r", encoding="utf-8") as file:
        content = json.load(file)
    return SearchConfig(**content)


def load_configs(config_dir: Path) -> tuple[IPProfile, ProjectConfig, SearchConfig]:
    ip_profile_path = config_dir / "ip_profile.json"
    project_config_path = config_dir / "project_config.json"
    search_config_path = config_dir / "search.json"
    if not ip_profile_path.exists():
        raise FileNotFoundError(f"Missing IP profile at {ip_profile_path}")
    if not project_config_path.exists():
        raise FileNotFoundError(f"Missing project config at {project_config_path}")
    return (
        load_ip_profile(ip_profile_path),
        load_project_config(project_config_path),
        load_search_config(search_config_path),
    )


from .validation import validate_configs

