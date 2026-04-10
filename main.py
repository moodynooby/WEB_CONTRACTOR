"""Web Contractor — Service Manager

Launches the Streamlit application.
The Telegram bot lifecycle is managed by the App class.

Usage:
    python main.py              # Launch Streamlit
    python main.py run          # Same as above

For setup, use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
STREAMLIT_PORT = 8501


def check_db_connection() -> bool:
    """Verify MongoDB connectivity before launching any interface.
    
    Returns:
        True if database is reachable, False otherwise.
    """
    # Load environment variables from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    
    mongo_uri = os.getenv("MONGODB_URI")
    
    if not mongo_uri:
        print("[✗] MONGODB_URI not set in .env file")
        print("[→] Configure MongoDB connection:")
        print("    1. Get a free MongoDB Atlas cluster at: https://www.mongodb.com/atlas")
        print("    2. Add MONGODB_URI to your .env file")
        print("    3. Format: mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority")
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
        print("    • Get a free MongoDB Atlas cluster at: https://www.mongodb.com/atlas")
        print("")
        print("[→] Or run the setup wizard: python scripts/setup.py")
        return False


def main():
    """Launch Streamlit application."""
    # Pre-flight database check
    if not check_db_connection():
        print("[✗] Database connectivity check failed. Application cannot start.")
        sys.exit(1)
    
    streamlit_app = SRC_DIR / "gui.py"
    if not streamlit_app.exists():
        print(f"[✘] Streamlit app not found at {streamlit_app}")
        sys.exit(1)

    print(f"[→] Starting Streamlit on port {STREAMLIT_PORT}...")
    print("[→] Telegram bot will start automatically if configured")
    print()

    proc = subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(streamlit_app),
            "--server.port", str(STREAMLIT_PORT),
            "--server.headless", "true",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=str(SRC_DIR),
    )

    if proc.returncode != 0:
        print(f"[✘] Streamlit exited with code {proc.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    main()
