# Acceptance verification

The automated suite maps to the original brief as follows. Tests use temporary databases and
never depend on the user's default task data.

| ID | Automated evidence |
| --- | --- |
| AT-01 | CLI add persists a stable UUID; model creates unique IDs and UTC creation times. |
| AT-02 | Model and CLI reject empty or whitespace-only titles without writing data. |
| AT-03 | Model rejects boolean and out-of-range priorities; CLI rejects invalid priority arguments. |
| AT-04 | Repository and CLI treat missing storage as empty without creating it. |
| AT-05 | Service and CLI list filters return only the requested priority. |
| AT-06 | Service and CLI updates preserve IDs, creation times, command text, and completion status. |
| AT-07 | Completion persists and is idempotent across invocations. |
| AT-08 | Deletion persists and preserves other records. |
| AT-09 | Unknown and malformed IDs produce readable failures without saving changes. |
| AT-10 | `test_cli_lifecycle_across_processes` exercises independent Python processes and persisted state. |
| AT-11 | Invalid JSON, schema errors, invalid UTF-8, and duplicate JSON fields are reported and preserved. |
| AT-12 | Duplicate UUIDs are rejected on load, save, and export. |
| AT-13 | Exports validate records, preserve existing files unless forced, and resist destination-creation races. |
| AT-14 | Service and CLI statistics cover empty and mixed datasets, including completed high-priority tasks. |
| AT-15 | CI installs the lockfile, lints, checks formatting, tests, builds, and checks the installed CLI across three operating systems and two Python versions. Hosted CI must run after the repository is pushed. |
| AT-16 | CLI and process integration tests store shell-like command strings and assert that they remain inert; application code has no process-execution path. |

## Release gates

Run the commands in the README from a clean checkout. Before tagging `v0.1.0`, obtain a
maintainer review and a successful hosted CI run. Local Windows checks do not substitute for
the configured Linux and macOS jobs.
