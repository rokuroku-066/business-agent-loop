from __future__ import annotations

from typing import Dict


class ModeSelector:
    def select_mode(self, iteration_state: Dict[str, int], iteration_policy: Dict[str, object]) -> str:
        if "explore_ratio" not in iteration_policy or "deepening_ratio" not in iteration_policy:
            raise ValueError("iteration_policy must define both explore_ratio and deepening_ratio")
        explore_ratio = float(iteration_policy["explore_ratio"])
        deepen_ratio = float(iteration_policy["deepening_ratio"])
        explore_count = iteration_state.get("explore", 0)
        deepen_count = iteration_state.get("deepen", 0)
        total = explore_count + deepen_count
        if total == 0:
            return "explore" if explore_ratio >= deepen_ratio else "deepen"
        explore_target = explore_ratio * total
        deepen_target = deepen_ratio * total
        if explore_count < explore_target:
            return "explore"
        if deepen_count < deepen_target:
            return "deepen"
        return "explore"
