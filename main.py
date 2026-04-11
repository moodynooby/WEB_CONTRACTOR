"""Web Contractor — Desktop Application Launcher

Launches the PyQt6 desktop application.
The Telegram bot lifecycle is managed by the App class.

Usage:
    python main.py              # Launch PyQt6 GUI
    python main.py run          # Same as above
    python main.py bot          # Start Telegram bot only

For setup, use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import sys
from pathlib import Path

from infra.logging import get_logger

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

logger = get_logger(__name__)


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before launching any interface."""
    from infra.db_health import check_db_connection as _check

    return _check(PROJECT_ROOT)


def launch_gui():
    """Launch PyQt6 desktop application."""
    from database.connection import init_db
    from gui import main as gui_main

    logger.info("Initializing database...")
    init_db()

    logger.info("Starting Web Contractor GUI...")
    logger.info("Telegram bot will start automatically if configured")
    logger.info("")

    gui_main()


def launch_bot():
    """Launch Telegram bot only (foreground mode)."""
    from database.connection import init_db, is_connected
    import time

    if not is_connected():
        logger.error("Database not connected. Bot cannot start.")
        sys.exit(1)

    logger.info("Initializing database...")
    init_db()

    logger.info("Starting Telegram bot in foreground mode...")
    logger.info("The bot will handle pipeline execution when you use /run command")
    logger.info("Press Ctrl+C to stop")
    logger.info("")

    from app import WebContractorApp

    app = WebContractorApp()
    app.initialize()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        app.shutdown()


def main():
    """Main entry point."""
    command = sys.argv[1] if len(sys.argv) > 1 else "run"

    if command in ("run", "gui"):
        if not check_db_connection():
            logger.error("Database connectivity check failed. Application cannot start.")
            sys.exit(1)

        launch_gui()
    elif command == "bot":
        launch_bot()
    elif command == "status":
        check_db_connection()
    else:
        logger.error("Unknown command: %s", command)
        logger.info("Usage: python main.py [run|gui|bot|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
