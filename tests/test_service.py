"""Business operations, aggregate reporting, and persistence boundaries."""

from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from autotask.errors import RepositoryError, TaskNotFoundError, ValidationError
from autotask.models import Task, TaskStats
from autotask.service import TaskService


class MemoryStore:
    """Expose the actual stored list to detect accidental in-place mutations."""

    def __init__(self, tasks: Iterable[Task] = ()) -> None:
        self.tasks = list(tasks)
        self.save_count = 0
        self.export_call: tuple[list[Task], Path, bool] | None = None
        self.fail_load = False
        self.fail_save = False
        self.fail_export = False

    def load(self) -> list[Task]:
        if self.fail_load:
            raise RepositoryError("Unable to read task storage.")
        return self.tasks

    def save(self, tasks: Iterable[Task]) -> None:
        self.save_count += 1
        if self.fail_save:
            raise RepositoryError("Unable to write task storage.")
        self.tasks = list(tasks)

    def export(self, tasks: Iterable[Task], output: Path, force: bool = False) -> Path:
        if self.fail_export:
            raise RepositoryError("Unable to export tasks.")
        self.export_call = (list(tasks), output, force)
        return output


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore(
        [
            Task.create("Low", "echo low", priority=1),
            Task.create("High", "echo high", priority=3),
            replace(Task.create("Completed", "echo complete", priority=3), done=True),
        ]
    )


def test_add_preserves_existing_tasks_and_persists_new_task(store: MemoryStore) -> None:
    previous = list(store.tasks)
    added = TaskService(store).add("  New task ", "echo new")
    assert added.title == "New task"
    assert added.priority == 2
    assert store.tasks == [*previous, added]
    assert store.save_count == 1


@pytest.mark.parametrize(
    ("title", "command", "priority"),
    [(" ", "echo test", 2), ("Title", " ", 2), ("Title", "echo test", True)],
)
def test_invalid_add_never_saves(
    store: MemoryStore, title: str, command: str, priority: int
) -> None:
    previous = list(store.tasks)
    with pytest.raises(ValidationError):
        TaskService(store).add(title, command, priority)
    assert store.tasks == previous
    assert store.save_count == 0


def test_list_returns_all_tasks_or_filters_by_priority(store: MemoryStore) -> None:
    service = TaskService(store)
    assert service.list() == store.tasks
    assert service.list(priority=3) == store.tasks[1:]
    assert service.list(priority=2) == []
    assert store.save_count == 0


@pytest.mark.parametrize("priority", [0, 4, True, 2.0, "3"])
def test_list_rejects_invalid_priority(store: MemoryStore, priority: object) -> None:
    with pytest.raises(ValidationError, match="Priority"):
        TaskService(store).list(priority=priority)
    assert store.save_count == 0


@pytest.mark.parametrize(
    ("changes", "title", "priority"),
    [
        ({"title": "  New title "}, "New title", 1),
        ({"priority": 3}, "Low", 3),
        ({"title": "New title", "priority": 2}, "New title", 2),
    ],
)
def test_update_changes_only_requested_fields(
    store: MemoryStore, changes: dict[str, object], title: str, priority: int
) -> None:
    original = store.tasks[0]
    others = store.tasks[1:]
    updated = TaskService(store).update(original.id, **changes)
    assert updated.title == title
    assert updated.priority == priority
    assert updated.id == original.id
    assert updated.command == original.command
    assert updated.created_at == original.created_at
    assert updated.done == original.done
    assert store.tasks == [updated, *others]
    assert store.save_count == 1


@pytest.mark.parametrize("changes", [{}, {"title": " "}, {"priority": False}])
def test_invalid_update_preserves_storage(store: MemoryStore, changes: dict[str, object]) -> None:
    previous = list(store.tasks)
    with pytest.raises(ValidationError):
        TaskService(store).update(store.tasks[0].id, **changes)
    assert store.tasks == previous
    assert store.save_count == 0


def test_complete_preserves_other_fields_and_is_idempotent(store: MemoryStore) -> None:
    original = store.tasks[0]
    service = TaskService(store)
    completed = service.complete(original.id)
    assert completed == replace(original, done=True)
    assert store.tasks[0] == completed
    assert service.complete(original.id) == completed
    assert store.save_count == 1


def test_delete_preserves_other_tasks_and_returns_removed_record(store: MemoryStore) -> None:
    removed = store.tasks[1]
    expected = [store.tasks[0], store.tasks[2]]
    assert TaskService(store).delete(removed.id) == removed
    assert store.tasks == expected
    assert store.save_count == 1


@pytest.mark.parametrize("operation", ["update", "complete", "delete"])
def test_unknown_id_never_saves(store: MemoryStore, operation: str) -> None:
    service = TaskService(store)
    previous = list(store.tasks)
    kwargs = {"title": "New"} if operation == "update" else {}
    with pytest.raises(TaskNotFoundError, match="was not found"):
        getattr(service, operation)(str(uuid4()), **kwargs)
    assert store.tasks == previous
    assert store.save_count == 0


@pytest.mark.parametrize("operation", ["update", "complete", "delete"])
def test_malformed_id_is_reported_as_validation_error(store: MemoryStore, operation: str) -> None:
    kwargs = {"title": "New"} if operation == "update" else {}
    with pytest.raises(ValidationError, match="UUID"):
        getattr(TaskService(store), operation)("not-a-uuid", **kwargs)
    assert store.save_count == 0


def test_lookup_accepts_equivalent_uuid_spelling(store: MemoryStore) -> None:
    original = store.tasks[0]
    assert TaskService(store).complete(original.id.upper()).id == original.id


def test_stats_include_completed_high_priority_tasks(store: MemoryStore) -> None:
    stats = TaskService(store).stats()
    assert stats.total == 3
    assert stats.completed == 1
    assert stats.pending == 2
    assert stats.high_priority == 2
    assert stats.completion_rate == pytest.approx(100 / 3)
    assert store.save_count == 0


def test_empty_statistics_and_list() -> None:
    service = TaskService(MemoryStore())
    assert service.stats() == TaskStats(0, 0, 0, 0, 0.0)
    assert service.list() == []


@pytest.mark.parametrize("force", [False, True])
def test_export_delegates_validated_tasks_and_overwrite_choice(
    store: MemoryStore, tmp_path: Path, force: bool
) -> None:
    output = tmp_path / "export.json"
    assert TaskService(store).export(output, force=force) == output
    assert store.export_call == (store.tasks, output, force)
    assert store.save_count == 0


@pytest.mark.parametrize("operation", ["add", "update", "complete", "delete"])
def test_failed_save_cannot_mutate_previously_loaded_list(
    store: MemoryStore, operation: str
) -> None:
    previous = list(store.tasks)
    store.fail_save = True
    service = TaskService(store)
    args = ("New", "echo new") if operation == "add" else (store.tasks[0].id,)
    kwargs = {"title": "New"} if operation == "update" else {}
    with pytest.raises(RepositoryError, match="write"):
        getattr(service, operation)(*args, **kwargs)
    assert store.tasks == previous


@pytest.mark.parametrize(
    "operation", ["add", "list", "update", "complete", "delete", "stats", "export"]
)
def test_failed_load_propagates_without_writing(
    store: MemoryStore, tmp_path: Path, operation: str
) -> None:
    store.fail_load = True
    args = {
        "add": ("New", "echo new"),
        "list": (),
        "update": (store.tasks[0].id,),
        "complete": (store.tasks[0].id,),
        "delete": (store.tasks[0].id,),
        "stats": (),
        "export": (tmp_path / "export.json",),
    }[operation]
    kwargs = {"title": "New"} if operation == "update" else {}
    with pytest.raises(RepositoryError, match="read"):
        getattr(TaskService(store), operation)(*args, **kwargs)
    assert store.save_count == 0
    assert store.export_call is None


def test_export_error_propagates(store: MemoryStore, tmp_path: Path) -> None:
    store.fail_export = True
    with pytest.raises(RepositoryError, match="export"):
        TaskService(store).export(tmp_path / "export.json")
    assert store.save_count == 0
