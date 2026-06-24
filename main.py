"""Web Contractor — Application Launcher

Usage:
    python main.py              # Launch Streamlit web app (default)
    python main.py web          # Same as above
    python main.py bot          # Start Telegram bot only
    python main.py status       # Check database connectivity

For setup, use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from infra.logging import get_logger

logger = get_logger(__name__)


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before launching any interface."""
    from infra.db_health import check_db_connection as _check

    return _check(PROJECT_ROOT)


def launch_web():
    """Launch Streamlit web application."""
    streamlit_app = SRC_DIR / "streamlit_app" / "Home.py"
    logger.info("Starting Web Contractor web UI...")
    logger.info(f"Streamlit app: {streamlit_app}")

    cmd = [sys.executable, "-m", "streamlit", "run", str(streamlit_app)]
    subprocess.run(cmd)


def launch_bot():
    """Launch Telegram bot only (foreground mode)."""
    import time

    from database.connection import init_db, is_connected

    if not is_connected():
        logger.error("Database not connected. Bot cannot start.")
        sys.exit(1)

    logger.info("Initializing database...")
    init_db()

    logger.info("Starting Telegram bot in foreground mode...")
    logger.info("Press Ctrl+C to stop")

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
    command = sys.argv[1] if len(sys.argv) > 1 else "web"

    if command in ("web", "run"):
        launch_web()
    elif command == "bot":
        launch_bot()
    elif command == "status":
        check_db_connection()
    else:
        logger.error("Unknown command: %s", command)
        logger.info("Usage: python main.py [web|bot|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
