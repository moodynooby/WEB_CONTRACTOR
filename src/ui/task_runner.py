"""Task Runner with QThread.

Background task execution for long-running pipeline operations.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime, timezone


class TaskRunner(QThread):
    """Run a callable in a background thread.

    Signals:
        started: Emitted when task starts (task_name).
        finished: Emitted when task completes successfully (task_name, result_dict, elapsed_seconds).
        failed: Emitted when task raises an exception (task_name, error_message).
    """

    started = pyqtSignal(str)
    finished = pyqtSignal(str, dict, float)
    failed = pyqtSignal(str, str)

    def __init__(self, task_name: str, task_func, display_name: str, **kwargs):
        """Initialize task runner.

        Args:
            task_name: Internal identifier for the task.
            task_func: Callable to execute in background.
            display_name: Human-readable name for logging/display.
            **kwargs: Additional arguments to pass to task_func.
        """
        super().__init__()
        self.task_name = task_name
        self.task_func = task_func
        self.display_name = display_name
        self.kwargs = kwargs

    def run(self) -> None:
        """Execute the task in background thread."""
        start_time = datetime.now(timezone.utc)
        self.started.emit(self.display_name)

        try:
            result = self.task_func(**self.kwargs)
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

            if result is None:
                result = {}
            elif not isinstance(result, dict):
                result = {"result": result}

            self.finished.emit(self.display_name, result, elapsed)

        except Exception as e:
            error_msg = str(e)
            self.failed.emit(self.display_name, error_msg)


class TaskManager:
    """Manage multiple background tasks.

    Prevents duplicate task execution and tracks running tasks.
    """

    def __init__(self):
        self._running_tasks: dict[str, TaskRunner] = {}

    def is_running(self, task_name: str) -> bool:
        """Check if a task is currently running.

        Args:
            task_name: Task identifier to check.

        Returns:
            True if task is running, False otherwise.
        """
        return (
            task_name in self._running_tasks
            and self._running_tasks[task_name].isRunning()
        )

    def start_task(self, task_name: str, runner: TaskRunner) -> None:
        """Register and start a task.

        Args:
            task_name: Task identifier.
            runner: TaskRunner instance to start.
        """
        runner.finished.connect(
            lambda *_: self._cleanup(task_name)
        )
        runner.failed.connect(
            lambda *_: self._cleanup(task_name)
        )
        self._running_tasks[task_name] = runner
        runner.start()

    def _cleanup(self, task_name: str) -> None:
        """Remove completed task from tracking dict.

        Args:
            task_name: Task identifier to remove.
        """
        self._running_tasks.pop(task_name, None)

    def stop_all(self) -> None:
        """Stop all running tasks."""
        for task_name, runner in list(self._running_tasks.items()):
            if runner.isRunning():
                runner.terminate()
                runner.wait()
        self._running_tasks.clear()
