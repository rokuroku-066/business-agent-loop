from pathlib import Path

from business_agent_loop.models import IdeaRecord, IterationLog, Task
from business_agent_loop.storage import StateStore


def test_state_store_initializes(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()

    assert (tmp_path / "state" / "tasks.json").exists()
    assert (tmp_path / "ideas").exists()
    assert store.load_tasks() == []


def test_state_store_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()

    task = Task(id="1", type="plan", priority=10, related_idea_ids=[], status="ready")
    store.save_tasks([task])
    loaded = store.load_tasks()
    assert loaded[0].id == "1"

    idea = IdeaRecord(
        id="idea-1",
        title="Sample",
        summary="Summary",
        target_audience="ops",
        value_proposition="Value",
        revenue_model="Subscription",
        brand_fit_score=0.8,
        novelty_score=0.7,
        feasibility_score=0.9,
        status="draft",
        tags=["automation"],
    )
    store.append_ideas([idea])
    idea_file = tmp_path / "ideas" / "ideas.jsonl"
    assert idea_file.exists()
    content = idea_file.read_text(encoding="utf-8")
    assert "idea-1" in content

    iteration = IterationLog(iteration_id="iter-1", mode="explore", task_summary="note")
    path = store.record_iteration(iteration)
    assert path.exists()
    assert store.latest_iteration() == path


def test_state_store_tracks_idea_history(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    store.append_idea_history("idea-1", "first summary")
    store.append_idea_history("idea-1", "second summary")

    history = store.load_idea_history()
    assert history["idea-1"][-1] == "second summary"


def test_load_ideas_by_ids_filters(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    store.ensure_layout()
    idea_a = IdeaRecord(
        id="idea-a",
        title="First",
        summary="Summary A",
        target_audience="ops",
        value_proposition="Value",
        revenue_model="Subscription",
        brand_fit_score=0.8,
        novelty_score=0.7,
        feasibility_score=0.9,
        status="draft",
        tags=["automation"],
    )
    idea_b = IdeaRecord(
        id="idea-b",
        title="Second",
        summary="Summary B",
        target_audience="ops",
        value_proposition="Value",
        revenue_model="Subscription",
        brand_fit_score=0.8,
        novelty_score=0.7,
        feasibility_score=0.9,
        status="draft",
        tags=["automation"],
    )
    store.append_ideas([idea_a, idea_b])

    matches = store.load_ideas_by_ids(["idea-b"])

    assert len(matches) == 1
    assert matches[0].id == "idea-b"
