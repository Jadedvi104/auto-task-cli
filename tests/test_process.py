"""Exercise the installed module across independent CLI processes."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_lifecycle_across_processes(tmp_path: Path) -> None:
    database = tmp_path / "database" / "tasks.json"
    sentinel = tmp_path / "command-must-never-run"
    environment = {**os.environ, "AUTOTASK_DB": str(database), "NO_COLOR": "1"}

    def run(*arguments: str) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "autotask", *arguments],
            capture_output=True,
            text=True,
            env=environment,
            timeout=20,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout

    run("add", "Process test", f'echo executed > "{sentinel}"', "--priority", "3")
    original = json.loads(database.read_text(encoding="utf-8"))[0]
    task_id = original["id"]
    assert task_id in run("list", "--priority", "3")
    run("update", task_id, "--title", "Updated process test", "--priority", "1")
    run("done", task_id)
    saved = json.loads(database.read_text(encoding="utf-8"))[0]
    assert saved == {**original, "title": "Updated process test", "priority": 1, "done": True}
    assert "100.0%" in run("stats")
    exported = tmp_path / "export.json"
    run("export", "--output", str(exported))
    assert json.loads(exported.read_text(encoding="utf-8")) == [saved]
    run("delete", task_id)
    assert json.loads(database.read_text(encoding="utf-8")) == []
    assert not sentinel.exists()
