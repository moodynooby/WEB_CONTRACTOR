"""Pipeline service - decoupled pipeline execution operations.

Extracted from BackgroundTaskRunner and WebContractorApp GUI coupling.
Provides long-running pipeline operations with progress tracking
via shared progress dicts (UI-agnostic).
"""

import threading
from typing import Callable

from app import WebContractorApp
from infra.logging import get_logger

logger = get_logger(__name__)

PROGRESS_STATUS_IDLE = "idle"
PROGRESS_STATUS_RUNNING = "running"
PROGRESS_STATUS_DONE = "done"
PROGRESS_STATUS_ERROR = "error"


def make_progress_dict() -> dict:
    """Create a fresh progress dict for pipeline tracking."""
    return {
        "status": PROGRESS_STATUS_IDLE,
        "message": "",
        "current": 0,
        "total": 0,
        "result": None,
        "error": None,
    }


class PipelineService:
    """Pipeline execution operations, decoupled from any UI framework.

    Long-running tasks run in background threads and report progress
    via a shared dict that the UI polls.
    """

    _app: WebContractorApp | None = None
    _lock = threading.Lock()

    @classmethod
    def get_app(cls) -> WebContractorApp:
        if cls._app is None:
            with cls._lock:
                if cls._app is None:
                    app = WebContractorApp()
                    app.initialize()
                    cls._app = app
        return cls._app

    @classmethod
    def run_discovery(cls, progress: dict, max_queries: int | None = None) -> None:
        cls._run(progress, "discovery", cls.get_app().run_discovery, max_queries=max_queries)

    @classmethod
    def run_audit(cls, progress: dict, limit: int = 20) -> None:
        cls._run(progress, "audit", cls.get_app().run_audit, limit=limit)

    @classmethod
    def generate_emails(cls, progress: dict, limit: int = 20) -> None:
        cls._run(progress, "email", cls.get_app().generate_emails, limit=limit)

    @classmethod
    def run_full_pipeline(cls, progress: dict, limit: int = 20) -> None:
        cls._run(progress, "pipeline", cls.get_app().run_unified_pipeline, limit=limit)

    @classmethod
    def _run(cls, progress: dict, name: str, method: Callable, **kwargs) -> None:
        def wrapper():
            try:
                progress["status"] = PROGRESS_STATUS_RUNNING
                progress["message"] = f"Running {name}..."

                def on_progress(current: int, total: int, msg: str):
                    progress["current"] = current
                    progress["total"] = total
                    progress["message"] = msg

                result = method(progress_callback=on_progress, **kwargs)
                progress["status"] = PROGRESS_STATUS_DONE
                progress["message"] = f"{name.capitalize()} completed"
                progress["result"] = result
                logger.info(f"Pipeline '{name}' completed: {result}")
            except Exception as e:
                progress["status"] = PROGRESS_STATUS_ERROR
                progress["message"] = f"{name.capitalize()} failed: {e}"
                progress["error"] = str(e)
                logger.error(f"Pipeline '{name}' failed: {e}")

        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
