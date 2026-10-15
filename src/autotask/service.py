"""Application operations independent of CLI formatting and JSON storage."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from autotask.errors import TaskNotFoundError, ValidationError
from autotask.models import Task, TaskStats, normalize_task_id, validate_priority


class TaskStore(Protocol):
    """Storage operations needed by the service."""

    def load(self) -> list[Task]: ...

    def save(self, tasks: Iterable[Task]) -> None: ...

    def export(self, tasks: Iterable[Task], output: Path, force: bool = False) -> Path: ...


class TaskService:
    """Manage validated task definitions through a storage boundary."""

    def __init__(self, repository: TaskStore) -> None:
        self.repository = repository

    def add(self, title: str, command: str, priority: int = 2) -> Task:
        task = Task.create(title, command, priority)
        tasks = self.repository.load()
        self.repository.save([*tasks, task])
        return task

    def list(self, priority: int | None = None) -> list[Task]:
        if priority is not None:
            validate_priority(priority)
        tasks = self.repository.load()
        return [task for task in tasks if priority is None or task.priority == priority]

    def update(
        self,
        task_id: str,
        title: str | None = None,
        priority: int | None = None,
    ) -> Task:
        if title is None and priority is None:
            raise ValidationError("Provide a title or priority to update.")
        tasks, index = self._find(task_id)
        current = tasks[index]
        updated = replace(
            current,
            title=current.title if title is None else title,
            priority=current.priority if priority is None else priority,
        )
        tasks[index] = updated
        self.repository.save(tasks)
        return updated

    def complete(self, task_id: str) -> Task:
        tasks, index = self._find(task_id)
        if tasks[index].done:
            return tasks[index]
        completed = replace(tasks[index], done=True)
        tasks[index] = completed
        self.repository.save(tasks)
        return completed

    def delete(self, task_id: str) -> Task:
        tasks, index = self._find(task_id)
        deleted = tasks.pop(index)
        self.repository.save(tasks)
        return deleted

    def stats(self) -> TaskStats:
        tasks = self.repository.load()
        total = len(tasks)
        completed = sum(task.done for task in tasks)
        return TaskStats(
            total=total,
            completed=completed,
            pending=total - completed,
            high_priority=sum(task.priority == 3 for task in tasks),
            completion_rate=100.0 * completed / total if total else 0.0,
        )

    def export(self, output: Path, force: bool = False) -> Path:
        return self.repository.export(self.repository.load(), output, force=force)

    def _find(self, task_id: str) -> tuple[list[Task], int]:
        canonical_id = normalize_task_id(task_id)
        tasks = list(self.repository.load())
        for index, task in enumerate(tasks):
            if task.id == canonical_id:
                return tasks, index
        raise TaskNotFoundError(f"Task '{canonical_id}' was not found.")
