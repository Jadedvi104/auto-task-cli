"""Validated JSON storage for task definitions.

Database writes replace a synced temporary file in the destination directory.
This prevents partially written JSON, but does not coordinate multiple writers.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import UUID

from .errors import RepositoryError, ValidationError
from .models import Task

_IS_WINDOWS = os.name == "nt"


def get_storage_path() -> Path:
    """Resolve the optional database override without creating directories."""
    override = os.environ.get("AUTOTASK_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".autotask" / "tasks.json"


class TaskRepository:
    """Read and write one JSON task database."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser()

    def load(self) -> list[Task]:
        """Read all tasks, rejecting invalid data without changing the file."""
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                records = json.load(stream, object_pairs_hook=_unique_object)
        except FileNotFoundError:
            return []
        except json.JSONDecodeError as exc:
            raise RepositoryError(
                f"Storage file '{self.path}' contains invalid JSON at line {exc.lineno}, "
                f"column {exc.colno}. Repair it or restore a valid backup."
            ) from exc
        except UnicodeDecodeError as exc:
            raise RepositoryError(
                f"Storage file '{self.path}' is not valid UTF-8. "
                "Repair it or restore a valid backup."
            ) from exc
        except (ValueError, RecursionError) as exc:
            raise RepositoryError(
                f"Storage file '{self.path}' contains unsupported JSON values or "
                "excessive nesting. Repair it or restore a valid backup."
            ) from exc
        except ValidationError as exc:
            raise RepositoryError(
                f"Storage file '{self.path}' contains duplicate JSON fields. "
                "Repair it or restore a valid backup."
            ) from exc
        except OSError as exc:
            raise _filesystem_error("read storage file", self.path, exc) from exc

        if not isinstance(records, list):
            raise RepositoryError(
                f"Storage file '{self.path}' must contain a JSON array of tasks. "
                "Repair it or restore a valid backup."
            )

        tasks: list[Task] = []
        for position, record in enumerate(records, start=1):
            try:
                tasks.append(Task.from_dict(record))
            except ValidationError as exc:
                raise RepositoryError(
                    f"Task record {position} in '{self.path}' is invalid: {exc} "
                    "Repair it or restore a valid backup."
                ) from exc
        _reject_duplicate_ids(tasks)
        return tasks

    def save(self, tasks: Iterable[Task]) -> None:
        """Validate and atomically replace storage, preserving corrupt databases."""
        records = _validated_records(tasks)
        self.load()
        self._write(records, self.path, overwrite=True)

    def export(self, tasks: Iterable[Task], output: Path, force: bool = False) -> Path:
        """Export valid tasks, requiring explicit permission to replace a file."""
        destination = Path(output).expanduser()
        records = _validated_records(tasks)
        self._write(records, destination, overwrite=force)
        return destination

    @staticmethod
    def _write(records: list[dict[str, Any]], destination: Path, *, overwrite: bool) -> None:
        temporary: Path | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(records, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if overwrite:
                os.replace(temporary, destination)
            else:
                # Publish a complete file while atomically refusing a destination
                # that exists or was created during this write.
                if _IS_WINDOWS:
                    # Windows rename refuses an existing destination and also
                    # works on removable drives without hard-link support.
                    os.rename(temporary, destination)
                else:
                    os.link(temporary, destination)
        except FileExistsError as exc:
            if not overwrite and destination.exists():
                raise RepositoryError(
                    f"Export destination '{destination}' already exists. "
                    "Choose another path or use --force to overwrite it."
                ) from exc
            raise _filesystem_error("write file", destination, exc) from exc
        except UnicodeError as exc:
            raise RepositoryError(
                f"Could not write file '{destination}': task text must be valid UTF-8."
            ) from exc
        except OSError as exc:
            raise _filesystem_error("write file", destination, exc) from exc
        finally:
            if temporary is not None:
                # Preserve the original write error if temporary cleanup fails.
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)


def _validated_records(tasks: Iterable[Task]) -> list[dict[str, Any]]:
    validated: list[Task] = []
    for position, task in enumerate(tasks, start=1):
        if not isinstance(task, Task):
            raise RepositoryError(f"Task item {position} must be a Task instance.")
        try:
            validated.append(Task.from_dict(task.to_dict()))
        except ValidationError as exc:
            raise RepositoryError(f"Task item {position} is invalid: {exc}") from exc
    _reject_duplicate_ids(validated)
    return [task.to_dict() for task in validated]


def _reject_duplicate_ids(tasks: Iterable[Task]) -> None:
    seen: set[UUID] = set()
    for position, task in enumerate(tasks, start=1):
        identity = UUID(task.id)
        if identity in seen:
            raise RepositoryError(
                f"Duplicate task ID at record {position}. Each task must have a unique UUID."
            )
        seen.add(identity)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for name, value in pairs:
        if name in record:
            raise ValidationError("Duplicate JSON field.")
        record[name] = value
    return record


def _filesystem_error(action: str, path: Path, error: OSError) -> RepositoryError:
    reason = error.strerror or "filesystem operation failed"
    return RepositoryError(
        f"Could not {action} '{path}': {reason}. Check the path and file permissions."
    )
