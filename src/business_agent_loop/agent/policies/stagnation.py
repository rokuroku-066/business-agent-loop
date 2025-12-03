from __future__ import annotations

from datetime import datetime, timezone

from ...models import IdeaRecord, Task


class StagnationPolicy:
    def is_stalled(self, history: list[str], candidate: str, *, threshold: float, runs: int) -> bool:
        if runs < 2:
            runs = 2
        window = history[-(runs - 1) :] + [candidate]
        if len(window) < runs:
            return False
        similarities = [
            self._jaccard_similarity(window[i], window[i + 1]) for i in range(len(window) - 1)
        ]
        return all(score >= threshold for score in similarities)

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
