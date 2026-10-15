# AutoTask CLI — Project Brief

**Project:** AutoTask CLI Task Manager  
**Version:** 0.1.0 (MVP proposal)  
**Status:** Ready for team kickoff  
**Target delivery:** 1 week (25 engineering hours for the learning-project baseline; re-estimate for team capacity)  
**Primary language:** Python 3.13+  
**Audience:** Engineering team, reviewers, QA

## 1. Executive Summary

AutoTask is a local command-line application for defining and managing automation tasks. It provides a reliable interface for creating, inspecting, updating, completing, deleting, summarizing, and exporting task definitions. Tasks are persisted to a JSON file so they remain available between CLI invocations.

The MVP deliberately **does not execute task commands**. Process execution, scheduling, retries, and job history are proposed for later iterations. This boundary keeps the first release safe, testable, and easy to extend.

## 2. Goals and Success Criteria

**Goals**
- Provide a simple, predictable CLI for managing task definitions.
- Preserve task data reliably between program runs.
- Separate CLI presentation, domain logic, and storage for maintainability.
- Deliver an installable Python package with automated quality checks.

**MVP success means**
- All documented commands work, including error cases.
- Tasks persist through restarts and survive normal file writes without partial JSON replacement.
- A clean checkout can install, lint, and test successfully.
- The release passes the acceptance tests in §10.

## 3. Users and Core Use Cases

**Primary users:** developers, DevOps engineers, and operations staff organizing local automation task definitions.

**Example use cases:**
1. Register a named future automation task with a command string and priority.
2. View pending or completed tasks and filter by priority.
3. Change a task's title or priority and mark it complete.
4. Remove obsolete tasks and inspect aggregate progress.
5. Export saved task definitions for backup or review.

## 4. MVP Scope

### In Scope

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-01 | Add a task with title, command string, and priority (1–3; default 2). | Must |
| FR-02 | List tasks with ID, title, priority, and completion status. | Must |
| FR-03 | Filter listed tasks by priority. | Must |
| FR-04 | Update an existing task's title and/or priority without changing other fields. | Must |
| FR-05 | Mark a task as completed. | Must |
| FR-06 | Delete a task by ID. | Must |
| FR-07 | Persist task definitions to local JSON and load them between runs. | Must |
| FR-08 | Show task statistics: total, completed, pending, high-priority, completion rate. | Must |
| FR-09 | Export validated task definitions to a user-specified JSON file. | Must |
| FR-10 | Display CLI help and actionable errors; return nonzero exit codes on failures. | Must |
| FR-11 | Allow tests and automation to override the storage path via `AUTOTASK_DB`. | Should |

### Out of Scope (Future Releases)

- Executing or scheduling OS commands.
- Running parallel processes, retries, process timeouts, or execution history.
- Remote access, API servers, authentication, teams, and cloud sync.
- Multi-writer concurrency guarantees and distributed task execution.

**Safety boundary:** `command` is metadata only in v0.1.0 and must never be passed to a shell or subprocess.

## 5. Proposed CLI Contract

```bash
# Create tasks
autotask add "Backup database" "python backup.py" --priority 3
autotask add "Rotate logs" "python rotate.py" --priority 2

# Inspect tasks
autotask list
autotask list --priority 3

# Update tasks
autotask update <TASK_ID> --title "Nightly backup" --priority 3
autotask done <TASK_ID>
autotask delete <TASK_ID>

# Reporting and export
autotask stats
autotask export --output exported-tasks.json

# Discoverability
autotask --help
```

**CLI conventions**
- Task identifiers are stable UUID strings.
- Priority is `1` (low), `2` (normal), or `3` (high).
- `list` defaults to all tasks; optional `--priority` filters them.
- Unknown IDs, malformed arguments, and corrupt storage produce a readable error and nonzero exit status.
- `export` must not overwrite an existing file without explicit opt-in (e.g., `--force`).
- Default storage: `~/.autotask/tasks.json`; override with `AUTOTASK_DB`.
- Human-readable terminal output is required; machine-readable command output beyond JSON export is deferred.

## 6. Data Model

One record per task, serialized to a JSON array:

```json
{
  "id": "4eb938db-ef25-483b-bc92-4bce774280b4",
  "title": "Backup database",
  "command": "python backup.py",
  "priority": 3,
  "done": false,
  "created_at": "2026-10-15T10:00:00+00:00"
}
```

**Validation rules**
- `id`: unique UUID string; immutable after creation.
- `title`: nonempty string after trimming whitespace.
- `command`: nonempty string after trimming; **stored but never executed**.
- `priority`: integer 1–3; booleans must not be accepted as integers.
- `done`: boolean.
- `created_at`: timezone-aware ISO 8601 UTC timestamp.
- Unknown or malformed records should fail with an explicit error, not be silently discarded.

## 7. Technical Design

### Recommended Stack

- **Python 3.13+** — application runtime.
- **uv** — Python version and dependency management, builds.
- **Typer** — command-line interface.
- **dataclasses / pathlib / json** — model and persistence (standard library).
- **pytest** — unit and CLI/integration testing.
- **Ruff** — linting and formatting.
- **GitHub Actions** — continuous integration.

### Layering

```text
User / Terminal
      |
  Typer CLI
      |
 TaskService        (business rules)
      |
TaskRepository      (JSON load/save)
      |
~/.autotask/tasks.json
```

### Repository Layout

```text
autotask/
├── src/autotask/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── service.py
│   └── repository.py
├── tests/
│   ├── test_models.py
│   ├── test_repository.py
│   ├── test_service.py
│   └── test_cli.py
├── .github/workflows/ci.yml
├── pyproject.toml
├── uv.lock
└── README.md
```

### Storage and Error Handling

- Write JSON to a temporary file in the same directory, flush and `fsync` it, then replace the destination with `os.replace()`.
- Reject corrupted JSON and duplicate task IDs; do not overwrite a corrupt database automatically.
- Keep tests isolated using pytest's `tmp_path` fixture.
- Document that atomic replacement is **not** a solution for concurrent writers; v0.1.0 supports a single writer at a time. Full power-loss durability also depends on filesystem behavior.
- Avoid printing secrets or complete command contents in unnecessary diagnostic logs.

## 8. Nonfunctional Requirements

| Area | Target |
| --- | --- |
| Correctness | Valid operations yield deterministic task states; invalid operations do not partially mutate saved state. |
| Usability | Every command has `--help`; errors say what needs fixing. |
| Reliability | Writes use atomic replacement; corrupt JSON is reported without silent data loss. |
| Maintainability | CLI, services, models, and storage remain separate and type-annotated. |
| Portability | Support Windows, macOS, and Linux for local task-definition management. |
| Testability | At least 20 meaningful automated tests; target ≥85% coverage as a guide, not a substitute for failure-path testing. |
| Security | Never execute stored `command` strings in the MVP; validate input and explicit export overwrites. |

## 9. Delivery Plan (25 Hours)

| Day | Hours | Implementation focus | Output |
| --- | ---: | --- | --- |
| 1 | 4 | Python environment, collections, functions, project scaffolding | Installable development environment, starter exercises |
| 2 | 4 | Dataclasses, type hints, validation | `Task` model and model tests |
| 3 | 4 | JSON storage, safe writes, corrupted-file errors | Repository and persistence tests |
| 4 | 4 | Typer commands and service methods | Add/list/update/done/delete CLI |
| 5 | 4 | Test cases, fixtures, linting | Automated unit/integration/CLI tests |
| 6 | 3 | Packaging, CI, clean-install verification | Build artifacts, GitHub Actions checks |
| 7 | 2 | Stats/export, documentation, final validation | v0.1.0 demonstration and release notes |
| **Total** | **25** | | |

*The hours reflect an accelerated learning-project plan for an experienced programmer new to Python; the team should revisit estimates during kickoff.*

## 10. Acceptance Tests

| Test | Scenario | Expected result |
| --- | --- | --- |
| AT-01 | Create a valid task | Stable unique ID returned; record persisted. |
| AT-02 | Empty or whitespace-only title | Validation error; no data written. |
| AT-03 | Priority outside 1–3 or boolean | Validation error and nonzero exit status. |
| AT-04 | List when database does not exist | Friendly empty result; no crash. |
| AT-05 | Filter priority 3 | Only high-priority tasks returned. |
| AT-06 | Update an existing task | Requested fields change; ID and creation time remain. |
| AT-07 | Mark an existing task done | Status persists after restart. |
| AT-08 | Delete an existing task | Task absent on subsequent listing. |
| AT-09 | Update/delete unknown ID | Readable error and nonzero status. |
| AT-10 | Exit and restart CLI | Previously stored data remains. |
| AT-11 | Load corrupt JSON | Error returned; file not silently reset. |
| AT-12 | Load duplicate IDs | Data rejected with explicit error. |
| AT-13 | Export task definitions | Valid JSON; existing destination preserved unless overwrite explicitly requested. |
| AT-14 | Get statistics | Counts and completion percentage correct, including empty dataset. |
| AT-15 | Fresh checkout on CI | Dependency install, lint, format check, test suite, and build all pass. |
| AT-16 | Inspect command handling | No implementation path executes saved command strings. |

## 11. Team Responsibilities and Artifacts

Suggested ownership (assign names at kickoff):

| Workstream | Suggested owner | Artifact |
| --- | --- | --- |
| Core model and service | Python engineer | Typed domain models and CRUD logic |
| CLI experience | Python engineer | Command handlers, help text, error paths |
| Storage and integrity | Python engineer | Repository, atomic writes, corruption tests |
| Quality and CI | Engineer / reviewer | pytest suite, Ruff configuration, CI pipeline |
| Release and docs | Maintainer | README, sample commands, versioned release notes |

**Review checkpoints:** (1) model and command contract, (2) CRUD and persistence functional demo, (3) acceptance test results and documentation review.

## 12. Risks and Decisions

| Risk or question | Mitigation / proposed decision |
| --- | --- |
| Concurrent CLI writes can lose updates | Restrict v0.1.0 to a single writer; evaluate SQLite or locking in a subsequent release. |
| Damaged JSON blocks all operations | Surface a clear error and preserve the original file for manual recovery. |
| Users assume registered tasks run automatically | State explicitly in help and README that execution is not supported in v0.1.0. |
| Arbitrary export path overwrites data | Require explicit overwrite flag and validate destination behavior. |
| Cross-platform shell differences | Store command strings as inert metadata; defer platform-specific execution design. |
| Scope expands into a job scheduler | Keep execution, scheduling, retries, and job history out of the MVP. |

**Kickoff decisions needed:** Confirm task field schema, default storage location, export overwrite behavior, and whether the team will require additional statuses beyond `done`/`pending` in later versions.

## 13. Definition of Done

The project is ready to release when:

- [ ] FR-01 through FR-10 are implemented and demonstrated.
- [ ] All AT-01 through AT-16 acceptance tests pass.
- [ ] `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .` pass.
- [ ] `uv build` produces distributable artifacts, and the installed CLI entry point works.
- [ ] CI passes from a clean checkout with committed lockfile.
- [ ] README includes setup, CLI examples, data-location details, limitations, and troubleshooting.
- [ ] At least one teammate reviews the implementation and the release is tagged `v0.1.0`.

## 14. Follow-on Roadmap

**v0.2.0 / Week 2:** Safe process execution (argument-based subprocess invocation), timeouts, exit status, execution history, structured logging, and cancellation behavior.

**Future:** Scheduling, worker queues, retries, persistent database transactions, multi-user access, notifications, and distributed automation orchestration.

---

**Suggested kickoff question:** Can every engineer describe what AutoTask v0.1.0 does *and does not* do, and can we demonstrate the complete acceptance-test matrix from a fresh checkout?
