"""Setup Script for Web Contractor

One-time setup script to initialize the project environment.
This prepares everything needed to run the application.

Usage:
    python scripts/setup.py              # Interactive setup
    python scripts/setup.py --non-interactive  # Use defaults from .env or defaults
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

# Project root is parent of scripts/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


class SetupWizard:
    """Interactive setup wizard."""

    def __init__(self, non_interactive: bool = False):
        self.non_interactive = non_interactive
        self.env_file = PROJECT_ROOT / ".env"
        self.env_vars = {}

    def print_header(self, title: str):
        """Print formatted header."""
        print("\n" + "=" * 70)
        print(f"  🏗️  Web Contractor - {title}")
        print("=" * 70 + "\n")

    def print_step(self, step_num: int, total: int, description: str):
        """Print step indicator."""
        print(f"\n[{step_num}/{total}] {description}")
        print("-" * 60)

    def prompt(self, question: str, default: str = "") -> str:
        """Prompt user for input."""
        if default:
            prompt_text = f"{question} [{default}]: "
        else:
            prompt_text = f"{question}: "

        if self.non_interactive:
            print(f"  (non-interactive) Using default: {default or '(empty)'}")
            return default

        try:
            answer = input(prompt_text).strip()
            return answer if answer else default
        except (EOFError, KeyboardInterrupt):
            print("\n\n⚠️  Setup cancelled.")
            sys.exit(1)

    def check_uv(self) -> bool:
        """Check if uv is installed."""
        try:
            subprocess.run(
                ["uv", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def install_uv(self):
        """Install uv package manager."""
        print("  Installing uv...")
        if platform.system() == "Windows":
            subprocess.run(
                ["winget", "install", "--id=astral-sh.uv", "-e"],
                check=True,
            )
        else:
            subprocess.run(
                ["curl", "-LsSf", "https://astral.sh/uv/install.sh", "|", "sh"],
                shell=True,
                check=True,
            )

    def step_dependencies(self):
        """Step 1: Install dependencies."""
        self.print_step(1, 5, "Installing Dependencies")

        if not self.check_uv():
            print("  ⚠️  uv not found")
            install_uv = self.prompt("Install uv?", "y")
            if install_uv.lower() in ["y", "yes"]:
                self.install_uv()
            else:
                print("  ❌ uv is required. Please install it manually.")
                print("     https://docs.astral.sh/uv/")
                sys.exit(1)

        print("  Installing Python dependencies...")
        try:
            subprocess.run(
                [sys.executable, "-m", "uv", "sync"],
                cwd=str(PROJECT_ROOT),
                check=True,
            )
            print("  ✓ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"  ❌ Failed to install dependencies: {e}")
            sys.exit(1)

    def step_env(self):
        """Step 2: Configure environment variables."""
        self.print_step(2, 5, "Environment Configuration")

        env_example = PROJECT_ROOT / ".env.example"
        if env_example.exists():
            print("  Found .env.example file")

            if self.env_file.exists():
                overwrite = self.prompt(".env already exists. Overwrite?", "n")
                if overwrite.lower() not in ["y", "yes"]:
                    print("  Using existing .env file")
                    # Load existing vars
                    with open(self.env_file) as f:
                        for line in f:
                            if "=" in line and not line.startswith("#"):
                                key, value = line.strip().split("=", 1)
                                self.env_vars[key] = value
                    return

            # Create new .env from example
            print("  Creating .env from .env.example...")
            self.env_file.write_text(env_example.read_text())

        # Prompt for values
        print("\n  Configure environment variables (press Enter for defaults):")

        mongodb_uri = self.prompt("  MongoDB URI", "mongodb://localhost:27017")
        if mongodb_uri:
            self.env_vars["MONGODB_URI"] = mongodb_uri

        username = self.prompt("  Streamlit username", "admin")
        if username:
            self.env_vars["STREAMLIT_USERNAME"] = username

        password = self.prompt("  Streamlit password", "changeme")
        if password:
            self.env_vars["STREAMLIT_PASSWORD"] = password

        groq_key = self.prompt("  Groq API key (optional)", "")
        if groq_key:
            self.env_vars["GROQ_API_KEY"] = groq_key

        telegram_token = self.prompt("  Telegram bot token (optional)", "")
        if telegram_token:
            self.env_vars["TELEGRAM_BOT_TOKEN"] = telegram_token

        telegram_chat_id = self.prompt("  Telegram chat ID (optional)", "")
        if telegram_chat_id:
            self.env_vars["TELEGRAM_CHAT_ID"] = telegram_chat_id

        # Write .env file
        env_content = "# Web Contractor Environment Configuration\n\n"
        for key, value in self.env_vars.items():
            env_content += f"{key}={value}\n"

        self.env_file.write_text(env_content)
        print(f"\n  ✓ Environment saved to {self.env_file}")

    def step_database(self):
        """Step 3: Check database connectivity."""
        self.print_step(3, 5, "Database Connectivity Check")

        print("  Testing MongoDB connection...")
        try:
            # Load env vars
            for key, value in self.env_vars.items():
                os.environ[key] = value

            from dotenv import load_dotenv
            load_dotenv(self.env_file)

            from pymongo import MongoClient

            mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")

            print("  ✓ Connected to MongoDB successfully")

            # Initialize database
            print("  Initializing database...")
            sys.path.insert(0, str(PROJECT_ROOT / "src"))
            from database.connection import init_db
            init_db()
            print("  ✓ Database initialized")

            client.close()

        except ImportError:
            print("  ⚠️  pymongo not installed. Run: uv sync")
        except Exception as e:
            print(f"  ⚠️  Database connection failed: {e}")
            print("  💡 Ensure MongoDB is running and URI is correct")
            print("  💡 You can fix this later and re-run setup")

    def step_playwright(self):
        """Step 4: Install Playwright browsers."""
        self.print_step(4, 5, "Playwright Browser Setup")

        print("  Installing Playwright browsers (required for web scraping)...")
        install = self.prompt("Install browsers now?", "y")

        if install.lower() in ["y", "yes", ""]:
            try:
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install"],
                    check=True,
                )
                print("  ✓ Playwright browsers installed")
            except subprocess.CalledProcessError as e:
                print(f"  ⚠️  Playwright installation failed: {e}")
                print("  💡 You can install manually later: playwright install")
        else:
            print("  ⚠️  Skipping Playwright browsers")
            print("  💡 Install later with: playwright install")

    def step_services(self):
        """Step 5: Start services."""
        self.print_step(5, 5, "Starting Services")

        start_streamlit = self.prompt("Start Streamlit now?", "y")
        if start_streamlit.lower() in ["y", "yes", ""]:
            print("\n  Starting Streamlit...")
            try:
                # Use the main.py entry point
                subprocess.Popen(
                    [sys.executable, str(PROJECT_ROOT / "main.py"), "run"],
                    cwd=str(PROJECT_ROOT),
                )
                print("  ✓ Streamlit started")
            except Exception as e:
                print(f"  ⚠️  Failed to start Streamlit: {e}")
                print("  💡 Start manually: python main.py run")

        if os.getenv("TELEGRAM_BOT_TOKEN") or self.env_vars.get("TELEGRAM_BOT_TOKEN"):
            start_bot = self.prompt("Start Telegram bot?", "y")
            if start_bot.lower() in ["y", "yes", ""]:
                try:
                    subprocess.Popen(
                        [sys.executable, str(PROJECT_ROOT / "main.py"), "bot"],
                        cwd=str(PROJECT_ROOT),
                    )
                    print("  ✓ Telegram bot started")
                except Exception as e:
                    print(f"  ⚠️  Failed to start bot: {e}")
                    print("  💡 Start manually: python main.py bot")

    def run(self):
        """Run complete setup."""
        self.print_header("Setup Wizard")

        print("This wizard will:")
        print("  1. Install Python dependencies")
        print("  2. Configure environment variables")
        print("  3. Test database connectivity")
        print("  4. Install Playwright browsers")
        print("  5. Start services")
        print()

        if not self.non_interactive:
            input("Press Enter to continue...")

        try:
            self.step_dependencies()
            self.step_env()
            self.step_database()
            self.step_playwright()
            self.step_services()

            self.print_header("Setup Complete!")

            print("  ✓ All setup steps completed\n")
            print("  Quick Start:")
            print("    • Streamlit UI:  python main.py run")
            print("    • Telegram bot:  python main.py bot")
            print("    • Status check:  python main.py status")
            print("    • Diagnostics:   python scripts/diagnostic.py")
            print("    • Stop all:      python main.py stop")
            print()

            username = self.env_vars.get("STREAMLIT_USERNAME", "admin")
            password = self.env_vars.get("STREAMLIT_PASSWORD", "changeme")
            print(f"  🔐 Default login: {username} / {password}")
            print("  💡 Change credentials in .env file")
            print()
            print("=" * 70 + "\n")

        except KeyboardInterrupt:
            print("\n\n⚠️  Setup interrupted.")
            sys.exit(1)
        except Exception as e:
            print(f"\n\n❌ Setup failed: {e}")
            print("💡 Check the error above and try again")
            print("💡 Run diagnostics: python scripts/diagnostic.py")
            sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Web Contractor Setup Wizard")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run setup without prompts (use defaults or .env)",
    )

    args = parser.parse_args()
    wizard = SetupWizard(non_interactive=args.non_interactive)
    wizard.run()
