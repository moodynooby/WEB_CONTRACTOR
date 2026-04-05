"""Web Contractor - Entry Point

Launches the Streamlit web interface.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Launch the Streamlit web interface."""
    streamlit_app = Path(__file__).parent / "streamlit_app.py"
    
    if not streamlit_app.exists():
        print(f"Error: Streamlit app not found at {streamlit_app}")
        sys.exit(1)
    
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(streamlit_app)])


if __name__ == "__main__":
    main()
