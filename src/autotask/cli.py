"""Human-readable command line interface for local task definitions."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from autotask.errors import AutoTaskError
from autotask.repository import TaskRepository, get_storage_path
from autotask.service import TaskService

app = typer.Typer(
    help=(
        "Manage local automation task definitions. "
        "Commands are stored as metadata and are never executed in v0.1.0."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _run[Result](operation: Callable[[TaskService], Result]) -> Result:
    """Create storage for this invocation and display actionable domain errors."""
    try:
        service = TaskService(TaskRepository(get_storage_path()))
        return operation(service)
    except AutoTaskError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None


@app.command("add")
def add_task(
    title: Annotated[str, typer.Argument(help="Nonempty title for the task.")],
    command: Annotated[
        str,
        typer.Argument(help="Command text to store as metadata; it will not run."),
    ],
    priority: Annotated[
        int,
        typer.Option(
            "--priority",
            "-p",
            min=1,
            max=3,
            help="Priority: 1 = low, 2 = normal, 3 = high.",
        ),
    ] = 2,
) -> None:
    """Create and save a task definition, returning its stable ID."""
    task = _run(lambda service: service.add(title, command, priority))
    typer.echo(f"Added task {task.id}: {task.title}")


@app.command("list")
def list_tasks(
    priority: Annotated[
        int | None,
        typer.Option(
            "--priority",
            "-p",
            min=1,
            max=3,
            help="Show only tasks with this priority (1-3).",
        ),
    ] = None,
) -> None:
    """Show all task IDs, titles, priorities, and completion states."""
    tasks = _run(lambda service: service.list(priority=priority))
    if not tasks:
        typer.echo(
            "No tasks found." if priority is None else f"No tasks found with priority {priority}."
        )
        return

    typer.echo("ID\tPriority\tStatus\tTitle")
    for task in tasks:
        status = "completed" if task.done else "pending"
        typer.echo(f"{task.id}\t{task.priority}\t{status}\t{task.title}")


@app.command("update")
def update_task(
    task_id: Annotated[str, typer.Argument(help="Stable ID of the task to update.")],
    title: Annotated[
        str | None,
        typer.Option("--title", help="Replace the task title with a nonempty value."),
    ] = None,
    priority: Annotated[
        int | None,
        typer.Option(
            "--priority",
            "-p",
            min=1,
            max=3,
            help="Replace the priority: 1 = low, 2 = normal, 3 = high.",
        ),
    ] = None,
) -> None:
    """Change a task's title and/or priority while preserving its other fields."""
    task = _run(lambda service: service.update(task_id, title=title, priority=priority))
    typer.echo(f"Updated task {task.id}: {task.title}")


@app.command("done")
def complete_task(
    task_id: Annotated[str, typer.Argument(help="Stable ID of the task to mark completed.")],
) -> None:
    """Mark an existing task completed and save its status."""
    task = _run(lambda service: service.complete(task_id))
    typer.echo(f"Completed task {task.id}: {task.title}")


@app.command("delete")
def delete_task(
    task_id: Annotated[str, typer.Argument(help="Stable ID of the task to delete.")],
) -> None:
    """Permanently remove an existing task definition by ID."""
    task = _run(lambda service: service.delete(task_id))
    typer.echo(f"Deleted task {task.id}: {task.title}")


@app.command("stats")
def show_statistics() -> None:
    """Show totals, completed and pending counts, and completion percentage."""
    stats = _run(lambda service: service.stats())
    typer.echo(f"Total: {stats.total}")
    typer.echo(f"Completed: {stats.completed}")
    typer.echo(f"Pending: {stats.pending}")
    typer.echo(f"High-priority: {stats.high_priority}")
    typer.echo(f"Completion rate: {stats.completion_rate:.1f}%")


@app.command("export")
def export_tasks(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Destination JSON file for task definitions."),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", help="Explicitly allow replacing an existing export."),
    ] = False,
) -> None:
    """Export validated task definitions; use --force to replace an existing file."""
    destination = _run(lambda service: service.export(output, force=force))
    typer.echo(f"Exported task definitions to {destination}")
