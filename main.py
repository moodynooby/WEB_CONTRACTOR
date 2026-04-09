"""Web Contractor — Service Manager

Launches the Streamlit application.
The Telegram bot lifecycle is managed by the App class.

Usage:
    python main.py              # Launch Streamlit
    python main.py run          # Same as above

For setup, use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
STREAMLIT_PORT = 8501


def main():
    """Launch Streamlit application."""
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
