# Changelog

## 0.1.0

- Manage task definitions with add, list, update, done, and delete commands.
- Filter tasks by priority and report completion statistics.
- Persist validated task records using atomic JSON replacement.
- Export JSON with explicit opt-in for overwriting existing destinations.
- Support a custom database location through `AUTOTASK_DB`.

Command strings are stored as metadata. Execution, scheduling, retries, and job history are outside this release.
