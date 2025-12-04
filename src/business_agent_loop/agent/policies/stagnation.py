from __future__ import annotations

from datetime import datetime, timezone

from ...models import IdeaRecord, Task


class StagnationPolicy:
    def is_stalled(self, history: list[str], candidate: str, *, threshold: float, runs: int) -> bool:
        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("stagnation_threshold must be numeric") from exc
        if not 0.0 <= threshold_value <= 1.0:
            raise ValueError("stagnation_threshold must be between 0.0 and 1.0")
        try:
            runs_value = int(runs)
        except (TypeError, ValueError) as exc:
            raise ValueError("stagnation_runs must be an integer") from exc
        if runs_value < 1:
            raise ValueError("stagnation_runs must be at least 1")
        if runs_value < 2:
            runs_value = 2
        window = history[-(runs_value - 1) :] + [candidate]
        if len(window) < runs_value:
            return False
        similarities = [
            self._jaccard_similarity(window[i], window[i + 1]) for i in range(len(window) - 1)
        ]
        return all(score >= threshold_value for score in similarities)

    def create_shake_up_task(self, idea: IdeaRecord, history: list[str]) -> Task:
        meta = {
            "note": "Idea updates appear stalled; force different directions",
            "idea_id": idea.id,
            "recent_summaries": history[-3:],
        }
        return Task(
            id=f"shake-{idea.id}-{datetime.now(timezone.utc).strftime('%H%M%S')}",
            type="shake_up_idea",
            priority=int(idea.novelty_score * 100) if idea.novelty_score else 50,
            related_idea_ids=[idea.id],
            status="ready",
            meta=meta,
        )

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        tokens_a = set(text_a.lower().split())
        tokens_b = set(text_b.lower().split())
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = tokens_a.intersection(tokens_b)
        union = tokens_a.union(tokens_b)
        return len(intersection) / len(union)
