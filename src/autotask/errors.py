"""User-facing errors shared by the application's layers."""


class AutoTaskError(Exception):
    """Base class for an expected application error."""


class ValidationError(AutoTaskError):
    """Task input or stored task data is invalid."""


class RepositoryError(AutoTaskError):
    """Task data could not be safely read or written."""


class TaskNotFoundError(AutoTaskError):
    """No task has the requested identifier."""
