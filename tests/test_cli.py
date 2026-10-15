"""Exercise the public CLI through independent invocations and isolated storage."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from autotask.cli import app

runner = CliRunner()


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "storage" / "tasks.json"
    monkeypatch.setenv("AUTOTASK_DB", str(path))
    return path


def _load(database: Path) -> list[dict]:
    return json.loads(database.read_text(encoding="utf-8"))


def _add(database: Path, title: str = "Backup database", priority: int = 2) -> dict:
    result = runner.invoke(app, ["add", title, "python backup.py", "--priority", str(priority)])
    assert result.exit_code == 0, result.output
    return _load(database)[-1]


def test_add_persists_record_and_prints_stable_id(database: Path) -> None:
    result = runner.invoke(app, ["add", "Backup database", "python backup.py"])

    assert result.exit_code == 0, result.output
    [task] = _load(database)
    assert str(UUID(task["id"])) == task["id"]
    assert task["id"] in result.output
    assert task["title"] == "Backup database"
    assert task["command"] == "python backup.py"
    assert task["priority"] == 2
    assert task["done"] is False


def test_independent_invocations_use_persisted_state(database: Path) -> None:
    first = _add(database, "First")
    second = _add(database, "Second")

    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0, result.output
    assert first["id"] != second["id"]
    assert first["id"] in result.output
    assert second["id"] in result.output
    assert "pending" in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        ["add", "", "echo hello"],
        ["add", "   ", "echo hello"],
        ["add", "Title", ""],
        ["add", "Title", "   "],
    ],
)
def test_add_rejects_blank_fields_without_creating_database(
    database: Path, arguments: list[str]
) -> None:
    result = runner.invoke(app, arguments)

    assert result.exit_code != 0
    assert "error" in result.output.lower()
    assert not database.exists()


@pytest.mark.parametrize("priority", ["0", "4", "-1", "true", "False", "2.5"])
def test_add_rejects_invalid_priority(database: Path, priority: str) -> None:
    result = runner.invoke(app, ["add", "Title", "echo hello", "--priority", priority])

    assert result.exit_code != 0
    assert "priority" in result.output.lower()
    assert not database.exists()


def test_list_missing_database_is_friendly_and_does_not_create_it(database: Path) -> None:
    result = runner.invoke(app, ["list"])

    assert result.exit_code == 0, result.output
    assert "No tasks" in result.output
    assert not database.exists()


def test_list_filters_priority_and_never_prints_commands(database: Path) -> None:
    high = _add(database, "Critical backup", priority=3)
    _add(database, "Routine cleanup", priority=1)

    result = runner.invoke(app, ["list", "--priority", "3"])

    assert result.exit_code == 0, result.output
    assert high["id"] in result.output
    assert "Critical backup" in result.output
    assert "Routine cleanup" not in result.output
    assert "python backup.py" not in result.output


def test_list_empty_filter_is_friendly(database: Path) -> None:
    _add(database, priority=1)

    result = runner.invoke(app, ["list", "--priority", "3"])

    assert result.exit_code == 0, result.output
    assert "No tasks" in result.output
    assert "priority 3" in result.output


def test_update_changes_requested_fields_and_preserves_metadata(database: Path) -> None:
    original = _add(database)

    result = runner.invoke(
        app,
        ["update", original["id"], "--title", "Nightly backup", "--priority", "3"],
    )

    assert result.exit_code == 0, result.output
    [updated] = _load(database)
    assert updated == {**original, "title": "Nightly backup", "priority": 3}


@pytest.mark.parametrize(
    ("options", "changes"),
    [
        (["--title", "Renamed"], {"title": "Renamed"}),
        (["--priority", "1"], {"priority": 1}),
    ],
)
def test_update_supports_each_field_independently(
    database: Path, options: list[str], changes: dict
) -> None:
    original = _add(database)

    result = runner.invoke(app, ["update", original["id"], *options])

    assert result.exit_code == 0, result.output
    assert _load(database) == [{**original, **changes}]


@pytest.mark.parametrize("options", [["--title", "  "], ["--priority", "4"]])
def test_invalid_update_preserves_database(database: Path, options: list[str]) -> None:
    original = _add(database)
    before = database.read_bytes()

    result = runner.invoke(app, ["update", original["id"], *options])

    assert result.exit_code != 0
    assert database.read_bytes() == before


def test_done_persists_status_between_invocations(database: Path) -> None:
    task = _add(database)

    completed = runner.invoke(app, ["done", task["id"]])
    listing = runner.invoke(app, ["list"])

    assert completed.exit_code == 0, completed.output
    assert listing.exit_code == 0, listing.output
    assert _load(database)[0]["done"] is True
    assert "completed" in listing.output


def test_delete_removes_task_from_persistent_storage(database: Path) -> None:
    task = _add(database)

    deleted = runner.invoke(app, ["delete", task["id"]])
    listing = runner.invoke(app, ["list"])

    assert deleted.exit_code == 0, deleted.output
    assert listing.exit_code == 0, listing.output
    assert _load(database) == []
    assert task["id"] not in listing.output


@pytest.mark.parametrize("command", ["update", "done", "delete"])
def test_unknown_id_returns_readable_error_and_preserves_storage(
    database: Path, command: str
) -> None:
    _add(database)
    before = database.read_bytes()
    arguments = [command, str(uuid4())]
    if command == "update":
        arguments += ["--title", "Unknown"]

    result = runner.invoke(app, arguments)

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "not found" in result.output.lower() or "unknown" in result.output.lower()
    assert database.read_bytes() == before


def test_corrupt_storage_returns_error_without_resetting_file(database: Path) -> None:
    database.parent.mkdir(parents=True)
    database.write_text("{broken JSON", encoding="utf-8")
    before = database.read_bytes()

    result = runner.invoke(app, ["list"])

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert database.read_bytes() == before


def test_duplicate_ids_return_explicit_error_without_data_loss(database: Path) -> None:
    task = _add(database)
    database.write_text(json.dumps([task, task]), encoding="utf-8")
    before = database.read_bytes()

    result = runner.invoke(app, ["list"])

    assert result.exit_code != 0
    assert "duplicate" in result.output.lower()
    assert database.read_bytes() == before


def test_stats_counts_completed_and_all_high_priority_tasks(database: Path) -> None:
    completed_task = _add(database, "First", priority=3)
    _add(database, "Second", priority=3)
    _add(database, "Third", priority=1)
    assert runner.invoke(app, ["done", completed_task["id"]]).exit_code == 0

    result = runner.invoke(app, ["stats"])

    assert result.exit_code == 0, result.output
    assert "Total: 3" in result.output
    assert "Completed: 1" in result.output
    assert "Pending: 2" in result.output
    assert "High-priority: 2" in result.output
    assert "Completion rate: 33.3%" in result.output


def test_stats_empty_database_has_zero_completion_rate(database: Path) -> None:
    result = runner.invoke(app, ["stats"])

    assert result.exit_code == 0, result.output
    assert "Total: 0" in result.output
    assert "Completed: 0" in result.output
    assert "Pending: 0" in result.output
    assert "High-priority: 0" in result.output
    assert "Completion rate: 0.0%" in result.output


def test_export_writes_valid_json_without_mutating_storage(database: Path, tmp_path: Path) -> None:
    task = _add(database)
    before = database.read_bytes()
    destination = tmp_path / "export.json"

    result = runner.invoke(app, ["export", "--output", str(destination)])

    assert result.exit_code == 0, result.output
    assert json.loads(destination.read_text(encoding="utf-8")) == [task]
    assert database.read_bytes() == before
    assert "python backup.py" not in result.output


def test_export_existing_file_requires_force(database: Path, tmp_path: Path) -> None:
    task = _add(database)
    destination = tmp_path / "export.json"
    destination.write_text("keep this file", encoding="utf-8")

    refused = runner.invoke(app, ["export", "--output", str(destination)])

    assert refused.exit_code != 0
    assert "--force" in refused.output
    assert destination.read_text(encoding="utf-8") == "keep this file"

    overwritten = runner.invoke(app, ["export", "--output", str(destination), "--force"])

    assert overwritten.exit_code == 0, overwritten.output
    assert json.loads(destination.read_text(encoding="utf-8")) == [task]


def test_export_requires_output_path(database: Path) -> None:
    result = runner.invoke(app, ["export"])

    assert result.exit_code != 0
    assert "--output" in result.output


def test_command_text_is_stored_as_inert_metadata(database: Path, tmp_path: Path) -> None:
    sentinel = tmp_path / "must-not-exist.txt"
    command = f'python -c "from pathlib import Path; Path({str(sentinel)!r}).touch()"'

    result = runner.invoke(app, ["add", "Inert command", command])
    listing = runner.invoke(app, ["list"])

    assert result.exit_code == 0, result.output
    assert listing.exit_code == 0, listing.output
    assert _load(database)[0]["command"] == command
    assert command not in result.output
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "command", [None, "add", "list", "update", "done", "delete", "stats", "export"]
)
def test_every_command_has_help(database: Path, command: str | None) -> None:
    arguments = ["--help"] if command is None else [command, "--help"]

    result = runner.invoke(app, arguments)

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output
    assert not database.exists()


def test_main_help_describes_execution_boundary(database: Path) -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    assert "never executed" in result.output
