"""Web Contractor — Service Manager

Cross-platform service manager for Streamlit and Telegram Bot.

Usage:
    python main.py              # Launch Streamlit (default)
    python main.py run          # Same as above
    python main.py bot          # Start Telegram bot (background)
    python main.py status       # Show running services
    python main.py stop         # Stop all services

For setup  , use the scripts:
    python scripts/setup.py         # Interactive setup wizard
"""

import argparse
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"
PID_FILE = PROJECT_ROOT / ".pids"
STREAMLIT_PORT = 8501


def is_windows() -> bool:
    return platform.system() == "Windows"


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


def start_streamlit() -> int | None:
    """Start Streamlit server. Returns PID or None on failure."""
    print("[→] Starting Streamlit on port {}...".format(STREAMLIT_PORT))
    streamlit_app = SRC_DIR / "gui.py"
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
            cwd=str(SRC_DIR),
        )

    write_pid("streamlit", proc.pid)
    print(f"[✔] Streamlit started (PID {proc.pid})")

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
    for f in [PROJECT_ROOT / ".streamlit.log", PROJECT_ROOT / ".telegram_bot.log"]:
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

    telegram_pid = pids.get("telegram_bot")
    if telegram_pid and is_process_running(telegram_pid):
        print(f"[✔] Telegram bot is running (PID {telegram_pid})")
    elif os.getenv("TELEGRAM_BOT_TOKEN"):
        print("[⚠] Telegram bot is not running (TELEGRAM_BOT_TOKEN is set)")
    else:
        print("[→] Telegram bot not configured (set TELEGRAM_BOT_TOKEN in .env)")

 


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

Scripts:
  python scripts/setup.py         Interactive setup wizard
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["run", "bot", "status", "stop"],
        help="Command to run (default: run)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        start_streamlit()
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
            pid = read_pids().get("telegram_bot")
            if pid:
                kill_process(pid)
            clear_pids()

    elif args.command == "status":
        show_status()

    elif args.command == "stop":
        stop_all()


if __name__ == "__main__":
    main()
