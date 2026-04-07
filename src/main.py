"""Web Contractor — Single Entry Point

Cross-platform service manager for Streamlit, Cloudflare Tunnel, and Telegram Bot.

Usage:
    python main.py                  # Launch Streamlit (default)
    python main.py run              # Same as above
    python main.py bot              # Start Telegram bot (background)
    python main.py status           # Show running services
    python main.py stop             # Stop all services
    python main.py setup            # Full setup: deps + auth + start all
    python main.py verify           # Health check
"""

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.resolve()
PID_FILE = PROJECT_ROOT / ".pids"
TUNNEL_URL_FILE = PROJECT_ROOT / ".tunnel_url"
AUTH_CONFIG = PROJECT_ROOT / "config" / "auth.yaml"
STREAMLIT_PORT = 8501

# ── Cross-platform helpers ─────────────────────────────────────────────

def is_windows() -> bool:
    return platform.system() == "Windows"


def uv_cmd() -> list[str]:
    """Return the command prefix for running via uv."""
    return [sys.executable, "-m", "uv"] if _has_uv_module() else ["uv"]


def _has_uv_module() -> bool:
    """Check if uv is available as a Python module."""
    try:
        import importlib.util
        return importlib.util.find_spec("uv") is not None
    except ModuleNotFoundError:
        return False


def run_uv(*args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run a command via uv, handling both module and CLI forms."""
    cmd = [*uv_cmd(), "run", *args]
    return subprocess.run(cmd, **kwargs)


def check_command(name: str) -> bool:
    """Check if a command is available on PATH."""
    try:
        subprocess.run(
            ["where", name] if is_windows() else ["which", name],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ── PID Management ─────────────────────────────────────────────────────

def read_pids() -> dict[str, int]:
    """Read PID file, return dict of {service_name: pid}."""
    pids = {}
    if PID_FILE.exists():
        for line in PID_FILE.read_text().strip().splitlines():
            if "=" in line:
                name, pid = line.split("=", 1)
                try:
                    pids[name.strip()] = int(pid.strip())
                except ValueError:
                    pass
    return pids


def write_pid(name: str, pid: int) -> None:
    """Append a service PID to the PID file."""
    pids = read_pids()
    pids[name] = pid
    PID_FILE.write_text("\n".join(f"{k}={v}" for k, v in pids.items()) + "\n")


def clear_pids() -> None:
    """Remove the PID file."""
    if PID_FILE.exists():
        PID_FILE.unlink()


def is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        if is_windows():
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, check=True,
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, subprocess.CalledProcessError):
        return False


def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, check=True,
            )
        else:
            os.kill(pid, 9)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


# ── Service Commands ───────────────────────────────────────────────────

def start_streamlit() -> int | None:
    """Start Streamlit server. Returns PID or None on failure."""
    print("[→] Starting Streamlit on port {}...".format(STREAMLIT_PORT))
    streamlit_app = PROJECT_ROOT / "streamlit_app.py"
    if not streamlit_app.exists():
        print(f"[✘] Streamlit app not found at {streamlit_app}")
        return None

    log_path = PROJECT_ROOT / ".streamlit.log"
    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(streamlit_app),
             "--server.port", str(STREAMLIT_PORT),
             "--server.headless", "true",
             "--server.enableCORS", "false",
             "--server.enableXsrfProtection", "true",
             "--browser.gatherUsageStats", "false"],
            stdout=log_f,
            stderr=log_f,
            cwd=str(PROJECT_ROOT),
        )

    write_pid("streamlit", proc.pid)
    print(f"[✔] Streamlit started (PID {proc.pid})")

    # Wait for Streamlit to be ready
    print("[→] Waiting for Streamlit...")
    for _ in range(30):
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"http://localhost:{STREAMLIT_PORT}", timeout=2)
            if resp.status == 200:
                print("[✔] Streamlit is ready")
                return proc.pid
        except Exception:
            pass
        time.sleep(1)
    print("[⚠] Streamlit may not be fully ready yet (timeout after 30s)")
    return proc.pid


def start_telegram_bot() -> int | None:
    """Start Telegram bot. Returns PID or None on failure."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        print("[⚠] TELEGRAM_BOT_TOKEN not set, skipping Telegram bot")
        return None

    print("[→] Starting Telegram bot...")
    log_path = PROJECT_ROOT / ".telegram_bot.log"
    with open(log_path, "w") as log_f:
        proc = subprocess.Popen(
            [sys.executable, "-m", "core.telegram_bot"],
            stdout=log_f,
            stderr=log_f,
            cwd=str(PROJECT_ROOT),
        )

    write_pid("telegram_bot", proc.pid)
    print(f"[✔] Telegram bot started (PID {proc.pid})")
    print(f"[→] Logs: {log_path}")
    return proc.pid


def stop_all() -> None:
    """Stop all running services."""
    pids = read_pids()
    if not pids:
        print("[⚠] No PID file found — services may not be running")
        # Fallback: try to kill by name
        _kill_by_name("streamlit")
        _kill_by_name("telegram_bot")
        return

    print("[→] Stopping services...")
    for name, pid in pids.items():
        if is_process_running(pid):
            print(f"[→] Stopping {name} (PID {pid})...")
            if kill_process(pid):
                print(f"[✔] Stopped {name}")
            else:
                print(f"[⚠] Failed to stop {name}")
        else:
            print(f"[⚠] {name} (PID {pid}) not running")

    clear_pids()
    # Clean up temp files
    for f in [TUNNEL_URL_FILE, PROJECT_ROOT / ".streamlit.log", PROJECT_ROOT / ".telegram_bot.log"]:
        if f.exists():
            f.unlink()
    print("[✔] Cleanup complete")


def _kill_by_name(pattern: str) -> None:
    """Try to kill processes matching a pattern (fallback when no PID file)."""
    try:
        if is_windows():
            subprocess.run(
                ["taskkill", "/F", "/IM", "python*.exe"],
                capture_output=True,
            )
        else:
            subprocess.run(["pkill", "-f", pattern], capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


def show_status() -> None:
    """Show status of all services."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   📊 Web Contractor — Service Status                    ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    pids = read_pids()

    # Streamlit
    streamlit_pid = pids.get("streamlit")
    if streamlit_pid and is_process_running(streamlit_pid):
        print(f"[✔] Streamlit is running (PID {streamlit_pid})")
        try:
            import urllib.request
            resp = urllib.request.urlopen(f"http://localhost:{STREAMLIT_PORT}", timeout=2)
            if resp.status == 200:
                print(f"[✔] Streamlit responding on port {STREAMLIT_PORT}")
        except Exception:
            print(f"[⚠] Streamlit on port {STREAMLIT_PORT} not responding")
    else:
        print("[✘] Streamlit is not running")

    # Telegram bot
    telegram_pid = pids.get("telegram_bot")
    if telegram_pid and is_process_running(telegram_pid):
        print(f"[✔] Telegram bot is running (PID {telegram_pid})")
    elif os.getenv("TELEGRAM_BOT_TOKEN"):
        print("[⚠] Telegram bot is not running (TELEGRAM_BOT_TOKEN is set)")
    else:
        print("[→] Telegram bot not configured (set TELEGRAM_BOT_TOKEN in .env)")

    # MongoDB
    print("[→] Checking MongoDB connectivity...", end=" ", flush=True)
    try:
        result = run_uv(
            "python", "-c",
            "from core.db import is_connected, init_db; init_db(); print('connected' if is_connected() else 'disconnected')",
            capture_output=True, text=True, timeout=10,
        )
        if "connected" in result.stdout:
            print("[✔] MongoDB is connected")
        else:
            print("[✘] MongoDB is not connected")
    except Exception:
        print("[✘] MongoDB check failed")

    # Auth config
    if AUTH_CONFIG.exists():
        print(f"[✔] Auth config exists at {AUTH_CONFIG}")
    else:
        print("[⚠] Auth config not found — run 'python main.py setup' to generate")


def install_deps() -> None:
    """Install Python dependencies via uv."""
    print("[→] Installing Python dependencies...")
    if not check_command("uv"):
        print("[✘] uv is not installed.")
        if is_windows():
            print("[→] Install: winget install --id=astral-sh.uv -e")
        else:
            print("[→] Install: curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)
    subprocess.run([*uv_cmd(), "sync"], cwd=str(PROJECT_ROOT), check=True)
    print("[✔] Python dependencies installed")


def generate_auth_config() -> None:
    """Generate Streamlit auth config if it doesn't exist."""
    if AUTH_CONFIG.exists():
        print(f"[⚠] Auth config already exists at {AUTH_CONFIG}, skipping")
        return

    print("[→] Generating Streamlit auth config...")
    username = os.getenv("STREAMLIT_USERNAME", "admin")
    password = os.getenv("STREAMLIT_PASSWORD", "changeme")

    # Simple YAML config
    AUTH_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    AUTH_CONFIG.write_text(
        f"credentials:\n"
        f"  usernames:\n"
        f"    {username}:\n"
        f"      password: {password}\n"
    )
    print(f"[✔] Auth config generated at {AUTH_CONFIG}")
    print(f"[⚠] Default credentials: username={username} password={password}")
    print(f"[⚠] Change these by editing {AUTH_CONFIG}")


def run_setup() -> None:
    """Full setup: deps + auth + start all services."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🏗️  Web Contractor — Full Setup                       ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # Stop any previous services
    stop_all()

    # Install deps
    install_deps()

    # Generate auth
    generate_auth_config()

    # Clear PID file for fresh start
    clear_pids()

    # Start services
    start_streamlit()
    start_telegram_bot()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║                   ✅ Setup Complete!                     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print(f"🌐 Streamlit: http://localhost:{STREAMLIT_PORT}")
    print(f"🔒 Username: {os.getenv('STREAMLIT_USERNAME', 'admin')}")
    print(f"🔑 Password: {os.getenv('STREAMLIT_PASSWORD', 'changeme')}")
    print()
    print("📝 To stop all services:  python main.py stop")
    print("📊 To check status:       python main.py status")
    print()


def run_verify() -> None:
    """Health check for all services."""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   🔍 Web Contractor — Health Check                      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    all_ok = True

    # Streamlit
    print("[→] Checking Streamlit on port {}...".format(STREAMLIT_PORT))
    try:
        import urllib.request
        resp = urllib.request.urlopen(f"http://localhost:{STREAMLIT_PORT}", timeout=5)
        if resp.status == 200:
            print("[✔] Streamlit is responding")
        else:
            print(f"[✘] Streamlit returned status {resp.status}")
            all_ok = False
    except Exception:
        print(f"[✘] Streamlit is not responding on port {STREAMLIT_PORT}")
        all_ok = False

    # Telegram bot
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        pids = read_pids()
        telegram_pid = pids.get("telegram_bot")
        if telegram_pid and is_process_running(telegram_pid):
            print("[✔] Telegram bot is running")
        else:
            print("[⚠] Telegram bot is not running (may not have been started)")

    # MongoDB
    print("[→] Checking MongoDB connectivity...", end=" ", flush=True)
    try:
        result = run_uv(
            "python", "-c",
            "from core.db import is_connected, init_db; init_db(); print('connected' if is_connected() else 'disconnected')",
            capture_output=True, text=True, timeout=10,
        )
        if "connected" in result.stdout:
            print("[✔] MongoDB is connected")
        else:
            print("[✘] MongoDB is not connected")
            all_ok = False
    except Exception:
        print("[✘] MongoDB check failed")
        all_ok = False

    # Auth config
    if AUTH_CONFIG.exists():
        print("[✔] Auth config exists")
    else:
        print("[⚠] Auth config not found — run 'python main.py setup'")

    # Dependencies
    print("[→] Checking Python dependencies...", end=" ", flush=True)
    try:
        run_uv(
            "python", "-c",
            "import streamlit; import pymongo; import plotly",
            capture_output=True, timeout=10,
        )
        print("[✔] Core dependencies available")
    except Exception:
        print("[✘] Some dependencies are missing — run: uv sync")
        all_ok = False

    print()
    if all_ok:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║              ✅ All checks passed!                       ║")
        print("╚══════════════════════════════════════════════════════════╝")
    else:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║              ❌ Some checks failed                       ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print()
        print("[→] Fix failed checks and re-run: python main.py verify")
    print()


# ── CLI ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Web Contractor — Service Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py              Launch Streamlit
  python main.py bot          Start Telegram bot
  python main.py status       Show service status
  python main.py stop         Stop all services
  python main.py setup        Full setup (deps + auth + start all)
  python main.py verify       Health check
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "bot", "status", "stop", "setup", "verify"],
        help="Command to run (default: run)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        start_streamlit()
        # Keep process alive so Ctrl+C kills Streamlit
        try:
            proc_status = subprocess.Popen(
                [sys.executable, "-c",
                 "import time; [time.sleep(1) for _ in iter(int, 1)]"]
            )
            proc_status.wait()
        except KeyboardInterrupt:
            print("\n[→] Shutting down...")
            stop_all()

    elif args.command == "bot":
        start_telegram_bot()
        print("[→] Bot running. Press Ctrl+C to stop.")
        try:
            while True:
                pid = read_pids().get("telegram_bot")
                if pid and is_process_running(pid):
                    time.sleep(1)
                else:
                    print("[⚠] Telegram bot stopped unexpectedly")
                    break
        except KeyboardInterrupt:
            print("\n[→] Stopping Telegram bot...")
            if pid:
                kill_process(pid)
            clear_pids()

    elif args.command == "status":
        show_status()

    elif args.command == "stop":
        stop_all()

    elif args.command == "setup":
        run_setup()

    elif args.command == "verify":
        run_verify()


if __name__ == "__main__":
    main()
