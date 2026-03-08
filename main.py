"""Web Contractor - Entry Point"""

from dotenv import load_dotenv

load_dotenv()

from ui.app import WebContractorTUI  # noqa: E402


def main():
    """Run the TUI application."""
    app = WebContractorTUI()
    app.run()


if __name__ == "__main__":
    main()
