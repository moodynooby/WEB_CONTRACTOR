"""Web Contractor — Desktop Application Launcher

Launches the Tkinter desktop application.
The Telegram bot lifecycle is managed by the App class.

Usage:
    python main.py              # Launch Tkinter GUI
    python main.py run          # Same as above
    python main.py bot          # Start Telegram bot only

For setup, use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before launching any interface.

    Returns:
        True if database is reachable, False otherwise.
    """
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)

    mongo_uri = os.getenv("MONGODB_URI")

    if not mongo_uri:
        print("[✗] MONGODB_URI not set in .env file")
        print("[→] Configure MongoDB connection:")
        print(
            "    1. Get a free MongoDB Atlas cluster at: https://www.mongodb.com/atlas"
        )
        print("    2. Add MONGODB_URI to your .env file")
        print(
            "    3. Format: mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority"
        )
        print("")
        print("[→] Or run the setup wizard: python scripts/setup.py")
        return False

    print("[→] Testing MongoDB connection...")

    try:
        from pymongo import MongoClient

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()

        print("[✓] MongoDB connection successful")
        return True

    except ImportError:
        print("[✗] pymongo not installed. Run: uv sync")
        return False
    except Exception as e:
        print(f"[✗] MongoDB connection failed: {e}")
        print("")
        print("[→] Troubleshooting:")
        print("    • Check your MONGODB_URI in .env file")
        print("    • Ensure your MongoDB+srv URI is correctly formatted")
        print("    • Verify your IP is whitelisted in MongoDB Atlas")
        print(
            "    • Get a free MongoDB Atlas cluster at: https://www.mongodb.com/atlas"
        )
        print("")
        print("[→] Or run the setup wizard: python scripts/setup.py")
        return False


def launch_gui():
    """Launch Tkinter desktop application."""
    from database.connection import init_db
    from gui import main as gui_main

    print("[→] Initializing database...")
    init_db()

    print("[→] Starting Web Contractor GUI...")
    print("[→] Telegram bot will start automatically if configured")
    print()

    gui_main()


def launch_bot():
    """Launch Telegram bot only (foreground mode)."""
    from database.connection import init_db, is_connected
    import time

    if not is_connected():
        print("[✗] Database not connected. Bot cannot start.")
        sys.exit(1)

    print("[→] Initializing database...")
    init_db()

    print("[→] Starting Telegram bot in foreground mode...")
    print("[→] The bot will handle pipeline execution when you use /run command")
    print("[→] Press Ctrl+C to stop")
    print()

    from app import WebContractorApp

    app = WebContractorApp()
    app.initialize()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[→] Stopping...")
        app.shutdown()


def main():
    """Main entry point."""
    command = sys.argv[1] if len(sys.argv) > 1 else "run"

    if command in ("run", "gui"):
        if not check_db_connection():
            print("[✗] Database connectivity check failed. Application cannot start.")
            sys.exit(1)

        launch_gui()
    elif command == "bot":
        launch_bot()
    elif command == "status":
        check_db_connection()
    else:
        print(f"[✗] Unknown command: {command}")
        print("[→] Usage: python main.py [run|gui|bot|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
