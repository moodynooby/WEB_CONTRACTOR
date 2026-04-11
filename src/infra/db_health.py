"""Database health check utility — shared across CLI scripts and entry points."""

import os
from pathlib import Path

from dotenv import load_dotenv


def check_db_connection(project_root: Path | None = None) -> bool:
    """Verify MongoDB connectivity before proceeding.

    Args:
        project_root: Root directory containing .env file. Defaults to caller's parent.parent.

    Returns:
        True if database is reachable, False otherwise.
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent

    env_file = project_root / ".env"
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
