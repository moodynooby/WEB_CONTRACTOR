"""Diagnostic Script for Web Contractor

Comprehensive health check and environment validation tool.
Run this script to troubleshoot issues before starting the application.

Usage:
    python scripts/diagnostic.py
    python scripts/diagnostic.py --verbose
    python scripts/diagnostic.py --json
"""

import json
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Project root is parent of scripts/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class DiagnosticResult:
    """Stores diagnostic check results."""

    def __init__(self, check_name: str):
        self.check_name = check_name
        self.status = "PASS"  # PASS, WARN, FAIL
        self.details: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def add_detail(self, detail: str):
        self.details.append(detail)

    def add_warning(self, warning: str):
        self.status = "WARN"
        self.warnings.append(warning)

    def add_error(self, error: str):
        self.status = "FAIL"
        self.errors.append(error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "status": self.status,
            "details": self.details,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def check_python_environment() -> DiagnosticResult:
    """Check Python version and virtual environment."""
    result = DiagnosticResult("Python Environment")

    python_version = sys.version_info
    result.add_detail(f"Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")

    if python_version.major == 3 and python_version.minor >= 11:
        result.add_detail("✓ Python version meets requirement (>=3.11)")
    else:
        result.add_error(f"✗ Python version too old. Need >=3.11, have {python_version.major}.{python_version.minor}")

    # Check if running in virtual environment
    in_venv = (
        hasattr(sys, "real_prefix")
        or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        or os.environ.get("VIRTUAL_ENV") is not None
    )

    if in_venv:
        venv_path = os.environ.get("VIRTUAL_ENV", sys.prefix)
        result.add_detail(f"✓ Running in virtual environment: {venv_path}")
    else:
        result.add_warning("Not running in a virtual environment. Consider using: uv venv")

    result.add_detail(f"Platform: {platform.system()} {platform.release()}")
    result.add_detail(f"Architecture: {platform.machine()}")

    return result


def check_dependencies() -> DiagnosticResult:
    """Check if all required dependencies are installed."""
    result = DiagnosticResult("Dependencies")

    required_deps = {
        "streamlit": "Web UI framework",
        "pymongo": "MongoDB driver",
        "playwright": "Web scraping",
        "groq": "AI API client",
        "requests": "HTTP library",
        "beautifulsoup4": "HTML parsing",
        "plotly": "Data visualization",
        "dotenv": "Environment variables",
        "email_validator": "Email validation",
        "telegram": "Telegram bot",
    }

    importable_names = {
        "streamlit": "streamlit",
        "pymongo": "pymongo",
        "playwright": "playwright",
        "groq": "groq",
        "requests": "requests",
        "beautifulsoup4": "bs4",
        "plotly": "plotly",
        "python-dotenv": "dotenv",
        "email-validator": "email_validator",
        "python-telegram-bot": "telegram",
    }

    missing = []
    for package, module_name in importable_names.items():
        try:
            __import__(module_name)
            version = __import__(module_name).__version__ if hasattr(__import__(module_name), "__version__") else "installed"
            result.add_detail(f"✓ {package} ({version})")
        except ImportError:
            missing.append(package)
            result.add_error(f"✗ {package} - NOT INSTALLED")

    if missing:
        result.add_error(f"Missing {len(missing)} dependencies. Run: uv sync")
    else:
        result.add_detail(f"✓ All {len(required_deps)} required dependencies installed")

    return result


def check_mongodb() -> DiagnosticResult:
    """Check MongoDB connectivity and database status."""
    result = DiagnosticResult("MongoDB")

    try:
        from pymongo import MongoClient
        from dotenv import load_dotenv

        load_dotenv()
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

        result.add_detail(f"Connection string: {mongo_uri[:30]}...")

        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")

        # Get server info
        server_info = client.server_info()
        result.add_detail(f"✓ Connected to MongoDB {server_info.get('version', 'unknown')}")

        # List databases
        databases = client.list_database_names()
        result.add_detail(f"Available databases: {', '.join(databases)}")

        # Check if web_contractor database exists
        if "web_contractor" in databases:
            db = client["web_contractor"]
            collections = db.list_collection_names()
            result.add_detail(f"✓ web_contractor database exists with {len(collections)} collections")

            for coll in collections:
                count = db[coll].count_documents({})
                result.add_detail(f"  - {coll}: {count} documents")
        else:
            result.add_warning("web_contractor database not found. It will be created on first run.")

        client.close()

    except ImportError:
        result.add_error("pymongo not installed. Run: uv sync")
    except Exception as e:
        result.add_error(f"Connection failed: {str(e)}")
        result.add_warning("Ensure MongoDB is running and MONGODB_URI is set in .env")

    return result


def check_environment_variables() -> DiagnosticResult:
    """Check required environment variables."""
    result = DiagnosticResult("Environment Variables")

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        result.add_detail(f"✓ .env file exists at: {env_file}")

        # Load and check variables
        from dotenv import load_dotenv

        load_dotenv(env_file)
    else:
        result.add_warning(".env file not found. Using defaults.")

    required_vars = {
        "MONGODB_URI": "MongoDB connection",
    }

    optional_vars = {
        "STREAMLIT_USERNAME": "Streamlit admin username",
        "STREAMLIT_PASSWORD": "Streamlit admin password",
        "TELEGRAM_BOT_TOKEN": "Telegram bot token (optional)",
        "TELEGRAM_CHAT_ID": "Telegram chat ID (optional)",
        "GROQ_API_KEY": "Groq API key for AI features",
    }

    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else "***"
            result.add_detail(f"✓ {var}: {masked}")
        else:
            result.add_error(f"✗ {var} not set ({description})")

    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            masked = value[:10] + "..." if len(value) > 10 else "***"
            result.add_detail(f"✓ {var}: {masked}")
        else:
            result.add_detail(f"  {var}: not set ({description}) - optional")

    return result


def check_file_structure() -> DiagnosticResult:
    """Check if required files and directories exist."""
    result = DiagnosticResult("File Structure")

    required_files = [
        "pyproject.toml",
        "main.py",
        "src/__init__.py",
        "src/gui.py",
        "src/database/connection.py",
        "src/discovery/engine.py",
        "src/audit/orchestrator.py",
        "src/outreach/sender.py",
        "src/outreach/generator.py",
    ]

    required_dirs = [
        "src/database",
        "src/discovery",
        "src/audit",
        "src/outreach",
        "src/pages",
        "src/models",
        "src/infra",
        "scripts",
    ]

    missing_files = []
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            result.add_detail(f"✓ {file_path}")
        else:
            missing_files.append(file_path)
            result.add_warning(f"✗ {file_path} not found")

    missing_dirs = []
    for dir_path in required_dirs:
        full_path = PROJECT_ROOT / dir_path
        if full_path.exists() and full_path.is_dir():
            result.add_detail(f"✓ {dir_path}/")
        else:
            missing_dirs.append(dir_path)
            result.add_warning(f"✗ {dir_path}/ not found")

    if not missing_files and not missing_dirs:
        result.add_detail("✓ All required files and directories present")
    else:
        result.add_warning(f"Missing {len(missing_files)} files, {len(missing_dirs)} directories")

    return result


def check_services() -> DiagnosticResult:
    """Check if services are running."""
    result = DiagnosticResult("Running Services")

    pid_file = PROJECT_ROOT / ".pids"
    if pid_file.exists():
        result.add_detail(f"PID file: {pid_file}")

        pids = {}
        for line in pid_file.read_text().strip().splitlines():
            if "=" in line:
                name, pid = line.split("=", 1)
                try:
                    pids[name.strip()] = int(pid.strip())
                except ValueError:
                    pass

        for service_name, pid in pids.items():
            # Check if process is running
            try:
                if platform.system() == "Windows":
                    proc_result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True,
                        text=True,
                    )
                    is_running = str(pid) in proc_result.stdout
                else:
                    os.kill(pid, 0)
                    is_running = True

                if is_running:
                    result.add_detail(f"✓ {service_name} (PID {pid})")
                else:
                    result.add_warning(f"✗ {service_name} (PID {pid}) - process not found")
            except (OSError, subprocess.CalledProcessError):
                result.add_warning(f"✗ {service_name} (PID {pid}) - not running")
    else:
        result.add_detail("No PID file found. Services may not be running.")

    # Check Streamlit port
    streamlit_port = 8501
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result_conn = sock.connect_ex(("localhost", streamlit_port))
        if result_conn == 0:
            result.add_detail(f"✓ Streamlit responding on port {streamlit_port}")
        else:
            result.add_detail(f"  Streamlit not responding on port {streamlit_port}")
    finally:
        sock.close()

    return result


def check_playwright() -> DiagnosticResult:
    """Check Playwright installation and browser binaries."""
    result = DiagnosticResult("Playwright")

    try:
        import playwright

        version = getattr(playwright, '__version__', 'installed')
        result.add_detail(f"✓ Playwright installed (version {version})")

        # Check if browsers are installed
        try:
            result_code = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result_code.returncode == 0:
                result.add_detail("✓ Playwright browsers installed")
            else:
                result.add_warning("Playwright browsers not installed. Run: playwright install")
        except Exception:
            result.add_warning("Could not verify Playwright browsers. Run: playwright install")

    except ImportError:
        result.add_error("✗ Playwright not installed. Run: uv sync")

    return result


def run_diagnostics(verbose: bool = False, json_output: bool = False) -> int:
    """Run all diagnostic checks and report results."""
    print("\n" + "=" * 70)
    print("  🔍 Web Contractor - Diagnostic Report")
    print("=" * 70)
    print(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Project: {PROJECT_ROOT}")
    print("=" * 70 + "\n")

    checks = [
        check_python_environment,
        check_dependencies,
        check_environment_variables,
        check_mongodb,
        check_file_structure,
        check_playwright,
        check_services,
    ]

    results = []
    for check_func in checks:
        result = check_func()
        results.append(result)

        if json_output:
            continue

        # Print result
        status_icon = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[result.status]
        print(f"\n{status_icon} {result.check_name}")
        print("-" * 60)

        for detail in result.details:
            print(f"   {detail}")

        if verbose or result.status == "WARN":
            for warning in result.warnings:
                print(f"   ⚠️  {warning}")

        if verbose or result.status == "FAIL":
            for error in result.errors:
                print(f"   ❌ {error}")

    # Summary
    pass_count = sum(1 for r in results if r.status == "PASS")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    print("\n" + "=" * 70)
    print("  📊 Summary")
    print("=" * 70)
    print(f"  ✅ Passed: {pass_count}/{len(results)}")
    print(f"  ⚠️  Warnings: {warn_count}/{len(results)}")
    print(f"  ❌ Failed: {fail_count}/{len(results)}")
    print("=" * 70)

    if fail_count > 0:
        print("\n  ⚠️  Some checks failed. Review the errors above.")
        print("  💡 Run with --verbose for more details")
        print("  💡 Common fixes:")
        print("     - Missing dependencies: uv sync")
        print("     - MongoDB not running: Check your MongoDB service")
        print("     - Playwright browsers: playwright install")
        print("     - Environment variables: Copy .env.example to .env")
    elif warn_count > 0:
        print("\n  ⚠️  Some warnings found. Application may still work.")
        print("  💡 Run with --verbose to see details")
    else:
        print("\n  ✅ All checks passed! Ready to run Web Contractor.")
        print("  💡 Start with: python main.py setup")

    print()

    if json_output:
        print(json.dumps([r.to_dict() for r in results], indent=2))

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Web Contractor Diagnostic Tool")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--json", "-j", action="store_true", help="Output results as JSON")

    args = parser.parse_args()
    exit_code = run_diagnostics(verbose=args.verbose, json_output=args.json)
    sys.exit(exit_code)
