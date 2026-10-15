# AutoTask CLI

AutoTask is a local command-line application for managing automation task definitions.
Version 0.1.0 stores command strings as metadata only. It never executes or schedules them.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from this directory:

```console
uv sync --locked
uv run autotask --help
```

The project requires Python 3.13 or newer. `.python-version` selects Python 3.13 for development;
uv can provision it. To use an existing supported interpreter, run
`uv sync --locked --python 3.14` and select the same interpreter for subsequent commands.

Install the CLI as an independent tool:

```console
uv tool install .
autotask --help
```

## Usage

```console
uv run autotask add "Backup database" "python backup.py" --priority 3
uv run autotask add "Rotate logs" "python rotate.py"
uv run autotask list
uv run autotask list --priority 3
uv run autotask update <TASK_ID> --title "Nightly backup" --priority 3
uv run autotask done <TASK_ID>
uv run autotask stats
uv run autotask export --output exported-tasks.json
uv run autotask export --output exported-tasks.json --force
uv run autotask delete <TASK_ID>
```

Replace `<TASK_ID>` with the full UUID printed by `add` or `list`. Angle brackets are placeholders,
not characters to enter. `python -m autotask` is also available in an installed environment.
Every command has `--help`.

| Command | Behavior |
| --- | --- |
| `add TITLE COMMAND [--priority 1\|2\|3]` | Save a pending task; default priority is 2. |
| `list [--priority 1\|2\|3]` | Show IDs, titles, priorities, and completion status. |
| `update TASK_ID [--title TEXT] [--priority 1\|2\|3]` | Change the supplied fields; at least one is required. |
| `done TASK_ID` | Mark a task complete; repeating it is safe. |
| `delete TASK_ID` | Remove a task. |
| `stats` | Show total, completed, pending, high-priority count, and completion percentage. |
| `export --output PATH [--force]` | Export validated JSON; use `--force` to replace an existing file. |

Priority 1 is low, 2 normal, and 3 high. High-priority statistics include completed tasks.
An empty database has a completion rate of 0%. Invalid arguments, unknown IDs, and storage failures
produce readable errors with a nonzero exit status.

## Data and reliability

The default database is `~/.autotask/tasks.json`. Override it with `AUTOTASK_DB`:

```powershell
# PowerShell
$env:AUTOTASK_DB = Join-Path $PWD "tasks.json"
uv run autotask list
```

```sh
# macOS / Linux
export AUTOTASK_DB="$PWD/tasks.json"
uv run autotask list
```

A missing database is treated as empty. AutoTask creates its parent directory when saving.
The database and exports are JSON arrays of records:

```json
[
  {
    "id": "4eb938db-ef25-483b-bc92-4bce774280b4",
    "title": "Backup database",
    "command": "python backup.py",
    "priority": 3,
    "done": false,
    "created_at": "2026-10-15T10:00:00+00:00"
  }
]
```

Titles and commands must be nonempty after trimming. IDs must be unique UUID strings, priority
must be an integer from 1 to 3 (booleans are rejected), `done` must be a boolean, and timestamps
must be timezone-aware UTC. Missing fields, unexpected fields, invalid records, duplicate IDs,
and malformed JSON cause explicit errors. AutoTask preserves a corrupt database for recovery.

Database writes create a temporary file in the destination directory, flush and sync its contents,
then replace the destination atomically. v0.1.0 supports one writer at a time: atomic replacement
does not prevent lost updates from simultaneous processes. Full power-loss durability depends
on the filesystem. On macOS and Linux, exports without `--force` require hard-link support
in the destination filesystem; unsupported destinations fail without overwriting existing files.
Task definitions, including command strings, are stored in plain text.

## Development and verification

The application has four layers: Typer command handlers, a task service, validated dataclass
models, and a JSON repository. Application code is under `src/autotask`; isolated tests are
under `tests`. The original requirements are in [the project brief](autotask_cli_project_brief.md).

```console
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv build
uv tool run --no-config --from ./dist/autotask_cli-0.1.0-py3-none-any.whl autotask --help
```

Tests include unit, storage failure, service, and CLI integration scenarios. Coverage includes
branches and enforces an 85% minimum. CI repeats linting, formatting, tests, distribution builds,
and installed entry-point verification on Windows, macOS, and Linux with Python 3.13 and 3.14.
Commit `uv.lock` with dependency changes; use `uv lock` to refresh it intentionally. See the [acceptance matrix](docs/acceptance.md) for the mapping to the brief.

## Troubleshooting

- **Corrupt database:** copy the file to a backup, repair the reported JSON/schema problem,
  then retry. AutoTask does not reset or discard damaged records automatically.
- **Unknown task ID:** run `autotask list` and copy the full ID.
- **Export already exists:** choose another destination or pass `--force` to replace it.
- **Permission or path error:** choose a writable location, check parent directories, and check
  that another application is not locking the file.
- **Command does not run:** this release manages definitions only. Execution, scheduling,
  retries, and history are deferred to future versions.

## Release status

This repository initializes the v0.1.0 MVP. Review and a successful hosted CI run are release
gates; tag `v0.1.0` after those gates pass. See [CHANGELOG.md](CHANGELOG.md) for release contents.
