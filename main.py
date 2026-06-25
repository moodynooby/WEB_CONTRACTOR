"""Web Contractor — Application Launcher

Usage:
    python main.py              # Launch Streamlit web app (default)
    python main.py bot          # Start Telegram bot only
    python main.py status       # Check database connectivity
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"


def main():
    streamlit_app = SRC_DIR / "streamlit_app" / "Home.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(streamlit_app)]
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
