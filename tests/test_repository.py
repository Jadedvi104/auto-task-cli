"""Persistence, corruption protection, and safe export coverage."""

from __future__ import annotations

import errno
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from autotask import repository as repository_module
from autotask.errors import RepositoryError
from autotask.models import Task
from autotask.repository import TaskRepository, get_storage_path


@pytest.fixture
def task() -> Task:
    return Task(
        id=str(uuid4()),
        title="Backup ฐานข้อมูล",
        command="python backup.py --token=private-command-value",
        priority=3,
        done=False,
        created_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
    )


def test_storage_path_uses_home_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("AUTOTASK_DB", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert get_storage_path() == tmp_path / ".autotask" / "tasks.json"


def test_storage_path_expands_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOTASK_DB", "~/custom/tasks.json")
    assert get_storage_path() == Path.home() / "custom" / "tasks.json"


def test_missing_database_is_empty_without_creating_files(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "tasks.json"
    assert TaskRepository(path).load() == []
    assert not path.parent.exists()


def test_save_round_trip_with_nested_directory_and_generator(tmp_path: Path, task: Task) -> None:
    path = tmp_path / "nested" / "tasks.json"
    repository = TaskRepository(path)
    repository.save(item for item in [task])
    assert repository.load() == [task]
    assert json.loads(path.read_text(encoding="utf-8")) == [task.to_dict()]
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("contents", ["{broken", "[", '{"tasks": []}', '"string"', "null"])
def test_invalid_storage_is_preserved(tmp_path: Path, task: Task, contents: str) -> None:
    path = tmp_path / "tasks.json"
    path.write_text(contents, encoding="utf-8")
    repository = TaskRepository(path)
    with pytest.raises(RepositoryError):
        repository.load()
    with pytest.raises(RepositoryError):
        repository.save([task])
    assert path.read_text(encoding="utf-8") == contents


@pytest.mark.parametrize(
    "changed",
    [
        {"priority": True},
        {"done": "false"},
        {"title": " "},
        {"created_at": "2026-10-15T10:00:00"},
        {"unexpected": "private-command-value"},
    ],
)
def test_invalid_record_has_context_without_exposing_contents(
    tmp_path: Path, task: Task, changed: dict[str, object]
) -> None:
    path = tmp_path / "tasks.json"
    record = task.to_dict() | changed
    path.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(RepositoryError, match="record 1") as error:
        TaskRepository(path).load()
    assert "private-command-value" not in str(error.value)
    assert path.exists()


def test_duplicate_json_fields_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    path.write_text('[{"id": "first", "id": "second"}]', encoding="utf-8")
    with pytest.raises(RepositoryError, match="duplicate JSON fields"):
        TaskRepository(path).load()


def test_non_utf8_storage_is_preserved(tmp_path: Path, task: Task) -> None:
    path = tmp_path / "tasks.json"
    path.write_bytes(b"\xff\xfe\x80")
    with pytest.raises(RepositoryError, match="UTF-8"):
        TaskRepository(path).save([task])
    assert path.read_bytes() == b"\xff\xfe\x80"


def test_duplicate_ids_rejected_on_load(tmp_path: Path, task: Task) -> None:
    path = tmp_path / "tasks.json"
    contents = json.dumps([task.to_dict(), task.to_dict()])
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(RepositoryError, match="Duplicate task ID"):
        TaskRepository(path).load()
    assert path.read_text(encoding="utf-8") == contents


def test_duplicate_ids_rejected_before_write(tmp_path: Path, task: Task) -> None:
    path = tmp_path / "tasks.json"
    with pytest.raises(RepositoryError, match="Duplicate task ID"):
        TaskRepository(path).save([task, task])
    assert not path.exists()


def test_directory_cannot_be_used_as_database(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError, match="Check the path and file permissions"):
        TaskRepository(tmp_path).load()


def test_parent_file_reports_actionable_error(tmp_path: Path, task: Task) -> None:
    parent = tmp_path / "file"
    parent.write_text("existing", encoding="utf-8")
    with pytest.raises(RepositoryError, match="Check the path and file permissions"):
        TaskRepository(parent / "tasks.json").save([task])
    assert parent.read_text(encoding="utf-8") == "existing"


def test_replace_failure_preserves_database_and_cleans_temporary_file(
    tmp_path: Path, task: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "tasks.json"
    repository = TaskRepository(path)
    repository.save([task])
    original = path.read_bytes()

    def reject_replace(source: Path, destination: Path) -> None:
        assert Path(source).parent == destination.parent
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(repository_module.os, "replace", reject_replace)
    with pytest.raises(RepositoryError, match="Permission denied"):
        repository.save([])
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_fsync_failure_preserves_database_and_cleans_temporary_file(
    tmp_path: Path, task: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "tasks.json"
    repository = TaskRepository(path)
    repository.save([task])
    original = path.read_bytes()

    def reject_fsync(descriptor: int) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(repository_module.os, "fsync", reject_fsync)
    with pytest.raises(RepositoryError, match="Input/output error"):
        repository.save([])
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_export_round_trip_and_explicit_overwrite(tmp_path: Path, task: Task) -> None:
    repository = TaskRepository(tmp_path / "tasks.json")
    output = tmp_path / "exports" / "backup.json"
    assert repository.export([task], output) == output
    assert TaskRepository(output).load() == [task]
    original = output.read_bytes()
    with pytest.raises(RepositoryError, match="--force"):
        repository.export([], output)
    assert output.read_bytes() == original
    repository.export([], output, force=True)
    assert TaskRepository(output).load() == []
    assert list(output.parent.iterdir()) == [output]


@pytest.mark.parametrize("publish_strategy", ["rename", "link"])
def test_export_refuses_a_destination_created_during_write(
    tmp_path: Path, task: Task, monkeypatch: pytest.MonkeyPatch, publish_strategy: str
) -> None:
    output = tmp_path / "export.json"

    def create_competing_file(source: Path, destination: Path) -> None:
        destination.write_text("another writer", encoding="utf-8")
        raise FileExistsError(errno.EEXIST, "File exists")

    monkeypatch.setattr(repository_module, "_IS_WINDOWS", publish_strategy == "rename")
    monkeypatch.setattr(repository_module.os, publish_strategy, create_competing_file)
    with pytest.raises(RepositoryError, match="already exists"):
        TaskRepository(tmp_path / "tasks.json").export([task], output)
    assert output.read_text(encoding="utf-8") == "another writer"
    assert list(tmp_path.iterdir()) == [output]


def test_export_validates_duplicate_ids_before_creating_output(tmp_path: Path, task: Task) -> None:
    output = tmp_path / "exports" / "backup.json"
    with pytest.raises(RepositoryError, match="Duplicate task ID"):
        TaskRepository(tmp_path / "tasks.json").export([task, task], output)
    assert not output.parent.exists()


def test_invalid_text_cannot_replace_database(tmp_path: Path, task: Task) -> None:
    path = tmp_path / "tasks.json"
    repository = TaskRepository(path)
    repository.save([task])
    original = path.read_bytes()
    invalid_text = Task(
        id=str(uuid4()),
        title="Invalid \ud800 text",
        command=task.command,
        priority=task.priority,
        done=task.done,
        created_at=task.created_at,
    )
    with pytest.raises(RepositoryError, match="UTF-8") as error:
        repository.save([invalid_text])
    assert "private-command-value" not in str(error.value)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_repository_rejects_unvalidated_objects_before_write(tmp_path: Path) -> None:
    path = tmp_path / "tasks.json"
    with pytest.raises(RepositoryError, match="Task instance"):
        TaskRepository(path).save([{"title": "unvalidated"}])  # type: ignore[list-item]
    assert not path.exists()


@pytest.mark.parametrize("contents", ["[" + "9" * 5000 + "]", "[" * 5000 + "]" * 5000])
def test_json_parser_limits_report_error_and_preserve_database(
    tmp_path: Path, task: Task, contents: str
) -> None:
    path = tmp_path / "tasks.json"
    path.write_text(contents, encoding="utf-8")
    repository = TaskRepository(path)
    for operation in [repository.load, lambda: repository.save([task])]:
        with pytest.raises(RepositoryError, match="Repair it or restore a valid backup"):
            operation()
        assert path.read_text(encoding="utf-8") == contents
    assert list(tmp_path.iterdir()) == [path]
