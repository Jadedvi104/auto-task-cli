"""Validation and serialization checks for task definitions."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from autotask.errors import ValidationError
from autotask.models import Task


@pytest.fixture
def task() -> Task:
    return Task.create("Backup database", "python backup.py", priority=3)


def test_create_assigns_unique_uuid_pending_status_and_current_utc_time() -> None:
    before = datetime.now(UTC)
    first = Task.create("First", "echo first")
    second = Task.create("Second", "echo second")
    after = datetime.now(UTC)

    assert UUID(first.id).version == 4
    assert first.id != second.id
    assert first.priority == 2
    assert first.done is False
    assert first.created_at.tzinfo is UTC
    assert before <= first.created_at <= after


def test_normalizes_text_without_changing_command_contents() -> None:
    task = Task.create("  Nightly backup \n", "  echo 'hello'; exit 9  ")
    assert task.title == "Nightly backup"
    assert task.command == "echo 'hello'; exit 9"


def test_serialization_round_trip_preserves_every_field(task: Task) -> None:
    record = task.to_dict()
    assert set(record) == {"id", "title", "command", "priority", "done", "created_at"}
    assert record["created_at"].endswith("+00:00")
    assert Task.from_dict(record) == task


def test_accepts_zulu_timestamp_and_normalizes_uuid(task: Task) -> None:
    record = task.to_dict()
    record["id"] = task.id.upper().replace("-", "")
    record["created_at"] = "2026-10-15T10:00:00Z"
    loaded = Task.from_dict(record)
    assert loaded.id == task.id
    assert loaded.created_at == datetime(2026, 10, 15, 10, tzinfo=UTC)
    assert loaded.to_dict()["created_at"] == "2026-10-15T10:00:00+00:00"


def test_task_is_immutable(task: Task) -> None:
    with pytest.raises(FrozenInstanceError):
        task.id = str(UUID(int=0))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "not-a-uuid"),
        ("id", None),
        ("id", 123),
        ("title", ""),
        ("title", " \t\n"),
        ("title", None),
        ("title", 42),
        ("command", " \t"),
        ("command", None),
        ("command", ["echo", "test"]),
        ("priority", True),
        ("priority", False),
        ("priority", 0),
        ("priority", 4),
        ("priority", 2.0),
        ("priority", "2"),
        ("priority", None),
        ("done", 0),
        ("done", 1),
        ("done", "false"),
        ("done", None),
        ("created_at", datetime(2026, 10, 15)),
        ("created_at", datetime(2026, 10, 15, tzinfo=timezone(timedelta(hours=7)))),
        ("created_at", "2026-10-15T10:00:00+00:00"),
        ("created_at", None),
    ],
)
def test_direct_construction_cannot_bypass_validation(
    task: Task, field: str, value: object
) -> None:
    with pytest.raises(ValidationError):
        replace(task, **{field: value})


@pytest.mark.parametrize("record", [None, [], "text", 3, True])
def test_rejects_non_object_records(record: object) -> None:
    with pytest.raises(ValidationError, match="JSON object"):
        Task.from_dict(record)


@pytest.mark.parametrize("field", ["id", "title", "command", "priority", "done", "created_at"])
def test_rejects_missing_fields(task: Task, field: str) -> None:
    record = task.to_dict()
    del record[field]
    with pytest.raises(ValidationError, match="exactly"):
        Task.from_dict(record)


def test_rejects_unknown_fields(task: Task) -> None:
    record = task.to_dict()
    record["status"] = "pending"
    with pytest.raises(ValidationError, match="exactly"):
        Task.from_dict(record)


@pytest.mark.parametrize(
    "timestamp",
    [None, 123, {}, "", "not-a-date", "2026-02-30T00:00:00Z", "2026-10-15T10:00:00"],
)
def test_rejects_malformed_or_naive_serialized_timestamps(task: Task, timestamp: object) -> None:
    record = task.to_dict()
    record["created_at"] = timestamp
    with pytest.raises(ValidationError, match="Creation time"):
        Task.from_dict(record)


def test_rejects_non_utc_serialized_timestamp(task: Task) -> None:
    record = task.to_dict()
    record["created_at"] = "2026-10-15T17:00:00+07:00"
    with pytest.raises(ValidationError, match="UTC"):
        Task.from_dict(record)


@pytest.mark.parametrize("priority", [1, 2, 3])
def test_accepts_each_supported_priority(priority: int) -> None:
    assert Task.create("Title", "echo test", priority).priority == priority
