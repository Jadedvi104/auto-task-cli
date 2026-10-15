"""Validated immutable models for inert automation task definitions."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from autotask.errors import ValidationError

_TASK_FIELDS = {"id", "title", "command", "priority", "done", "created_at"}


def normalize_task_id(value: object) -> str:
    """Validate a UUID string and return its canonical spelling."""
    if not isinstance(value, str):
        raise ValidationError("Task ID must be a valid UUID string.")
    try:
        return str(UUID(value))
    except ValueError as error:
        raise ValidationError("Task ID must be a valid UUID string.") from error


def validate_priority(value: object) -> int:
    """Accept only integer priority values from 1 through 3."""
    if isinstance(value, bool) or not isinstance(value, int) or value not in (1, 2, 3):
        raise ValidationError("Priority must be an integer from 1 to 3.")
    return value


def _trimmed_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a nonempty string.")
    return value.strip()


def _utc_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ValidationError("Creation time must be a timezone-aware UTC datetime.")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValidationError("Creation time must be a timezone-aware UTC datetime.")
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Task:
    """A task definition; its command is metadata and is never executed."""

    id: str
    title: str
    command: str
    priority: int
    done: bool
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_task_id(self.id))
        object.__setattr__(self, "title", _trimmed_text(self.title, "Title"))
        object.__setattr__(self, "command", _trimmed_text(self.command, "Command"))
        object.__setattr__(self, "priority", validate_priority(self.priority))
        if not isinstance(self.done, bool):
            raise ValidationError("Completion status must be a boolean.")
        object.__setattr__(self, "created_at", _utc_datetime(self.created_at))

    @classmethod
    def create(cls, title: str, command: str, priority: int = 2) -> "Task":
        """Create a pending task with a fresh UUID and a UTC creation time."""
        return cls(
            id=str(uuid4()),
            title=title,
            command=command,
            priority=priority,
            done=False,
            created_at=datetime.now(UTC),
        )

    @classmethod
    def from_dict(cls, record: object) -> "Task":
        """Load a complete serialized record without accepting unknown fields."""
        if not isinstance(record, dict):
            raise ValidationError("Each task record must be a JSON object.")
        if set(record) != _TASK_FIELDS:
            raise ValidationError(
                "Task records must contain exactly: id, title, command, priority, done, created_at."
            )
        timestamp = record["created_at"]
        if not isinstance(timestamp, str):
            raise ValidationError("Creation time must be an ISO 8601 UTC timestamp.")
        try:
            created_at = datetime.fromisoformat(timestamp)
        except ValueError as error:
            raise ValidationError("Creation time must be an ISO 8601 UTC timestamp.") from error
        return cls(
            id=record["id"],
            title=record["title"],
            command=record["command"],
            priority=record["priority"],
            done=record["done"],
            created_at=created_at,
        )

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible task data with a canonical UTC timestamp."""
        return {
            "id": self.id,
            "title": self.title,
            "command": self.command,
            "priority": self.priority,
            "done": self.done,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class TaskStats:
    """Aggregate task counts and the completion percentage."""

    total: int
    completed: int
    pending: int
    high_priority: int
    completion_rate: float
