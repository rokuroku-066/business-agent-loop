from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

from . import IPProfile, ProjectConfig

REQUIRED_IP_FIELDS = (
    "ip_name",
    "essence",
    "visual_motifs",
    "core_personality",
    "taboos",
    "target_audience",
    "brand_promise",
    "canon_examples",
)

REQUIRED_PROJECT_FIELDS = (
    "project_name",
    "goal_type",
    "constraints",
    "idea_templates",
    "iteration_policy",
)


def _require_fields(payload: dict[str, Any], *, fields: tuple[str, ...], label: str) -> None:
    missing = [field for field in fields if field not in payload or payload[field] is None]
    if missing:
        raise ValueError(f"Missing required {label} fields: {', '.join(missing)}")


def _validate_iteration_policy(policy: dict[str, Any]) -> None:
    _require_fields(policy, fields=("explore_ratio", "deepening_ratio"), label="iteration_policy")

    explore_ratio = policy["explore_ratio"]
    deepen_ratio = policy["deepening_ratio"]
    try:
        explore_ratio_f = float(explore_ratio)
        deepen_ratio_f = float(deepen_ratio)
    except (TypeError, ValueError) as exc:
        raise ValueError("Iteration ratios must be numeric") from exc

    if explore_ratio_f < 0 or deepen_ratio_f < 0:
        raise ValueError("Iteration ratios must be non-negative")

    if not math.isclose(explore_ratio_f + deepen_ratio_f, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("explore_ratio and deepening_ratio must sum to 1.0")

    threshold = policy.get("stagnation_threshold")
    if threshold is None:
        raise ValueError("stagnation_threshold is required in iteration_policy")
    try:
        threshold_f = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("stagnation_threshold must be numeric") from exc
    if not 0.0 <= threshold_f <= 1.0:
        raise ValueError("stagnation_threshold must be between 0.0 and 1.0")

    runs = policy.get("stagnation_runs")
    if runs is None:
        raise ValueError("stagnation_runs is required in iteration_policy")
    try:
        runs_int = int(runs)
    except (TypeError, ValueError) as exc:
        raise ValueError("stagnation_runs must be an integer") from exc
    if runs_int < 1:
        raise ValueError("stagnation_runs must be at least 1")


def validate_configs(ip_profile: IPProfile, project_config: ProjectConfig) -> None:
    ip_payload = asdict(ip_profile)
    project_payload = asdict(project_config)

    _require_fields(ip_payload, fields=REQUIRED_IP_FIELDS, label="ip_profile")
    _require_fields(project_payload, fields=REQUIRED_PROJECT_FIELDS, label="project_config")

    iteration_policy = project_payload.get("iteration_policy", {})
    if not isinstance(iteration_policy, dict):
        raise ValueError("iteration_policy must be a mapping")
    _validate_iteration_policy(iteration_policy)
