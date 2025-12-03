from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import IdeaRecord, IterationLog, Task


class StateStore:
    """Filesystem-backed storage for ideas, tasks, and iterations."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.ideas_dir = base_dir / "ideas"
        self.iterations_dir = base_dir / "iterations"
        self.snapshots_dir = base_dir / "snapshots"
        self.state_dir = base_dir / "state"
        self.tasks_file = self.state_dir / "tasks.json"
        self.iteration_state_file = self.state_dir / "iteration_state.json"

    def ensure_layout(self) -> None:
        for directory in [
            self.base_dir,
            self.ideas_dir,
            self.iterations_dir,
            self.snapshots_dir,
            self.state_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if not self.tasks_file.exists():
            self.tasks_file.write_text("[]", encoding="utf-8")
        if not self.iteration_state_file.exists():
            self.iteration_state_file.write_text("{}", encoding="utf-8")

    # Task management
    def load_tasks(self) -> list[Task]:
        if not self.tasks_file.exists():
            return []
        with self.tasks_file.open("r", encoding="utf-8") as file:
            raw_tasks = json.load(file)
        return [Task.from_dict(task) for task in raw_tasks]

    def save_tasks(self, tasks: Iterable[Task]) -> None:
        serialized = [task.to_dict() for task in tasks]
        with self.tasks_file.open("w", encoding="utf-8") as file:
            json.dump(serialized, file, ensure_ascii=False, indent=2)

    # Idea storage
    def append_ideas(self, ideas: Iterable[IdeaRecord]) -> None:
        idea_file = self.ideas_dir / "ideas.jsonl"
        with idea_file.open("a", encoding="utf-8") as file:
            for idea in ideas:
                file.write(json.dumps(idea.to_dict(), ensure_ascii=False) + "\n")

    # Iteration logs
    def record_iteration(self, iteration: IterationLog) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        iteration_path = self.iterations_dir / f"{timestamp}_iteration.json"
        with iteration_path.open("w", encoding="utf-8") as file:
            json.dump(iteration.to_dict(), file, ensure_ascii=False, indent=2)
        return iteration_path

    def latest_iteration(self) -> Path | None:
        if not self.iterations_dir.exists():
            return None
        candidates = sorted(self.iterations_dir.glob("*_iteration.json"))
        return candidates[-1] if candidates else None
