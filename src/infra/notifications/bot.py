"""Telegram Bot — Remote command interface for Web Contractor.

Provides bot commands to monitor and control pipeline execution remotely.
Uses simple long-polling (no asyncio, no python-telegram-bot dependency).

Commands:
    /status       — Show current pipeline stats
    /leads        — Show lead counts by status
    /run [limit]  — Run full pipeline (default: 20)
    /audit <n>    — Audit N pending leads
    /discovery <n>— Run discovery with N max queries
    /cancel       — Cancel running pipeline
    /buckets      — Show bucket summary
    /help         — Show all commands

Usage:
    from infra.notifications.bot import start_bot_thread, stop_bot

    # Start (called by App.initialize())
    start_bot_thread(app_instance)

    # Stop (called by App.shutdown())
    stop_bot()
"""

import threading
import time
from typing import Any

from infra.logging import get_logger
from infra.notifications.telegram import TelegramNotifier
from infra.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = get_logger(__name__)

_notifier: TelegramNotifier | None = None
_bot_thread: threading.Thread | None = None
_stop_event = threading.Event()

_pipeline_running = False
_pipeline_thread: threading.Thread | None = None
_pipeline_result: dict | None = None
_pipeline_error: str | None = None
_app_ref: Any = None  




def _get_stats() -> str:
    """Format current stats as text message."""
    from database.connection import get_database, get_email_campaign_stats, DatabaseUnavailableError
    from database.repository import count_leads

    try:
        total_leads = count_leads()
    except DatabaseUnavailableError:
        return "⚠️ Database is not connected. Cannot fetch stats."

    try:
        db = get_database()
        if db is None:
            status_counts: dict = {}
        else:
            pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
            status_counts = {}
            for doc in db.leads.aggregate(pipeline):
                status_counts[doc["_id"]] = doc["count"]
    except Exception:
        status_counts = {}

    try:
        email_stats = get_email_campaign_stats()
        email_sent = email_stats.get("sent", 0)
        email_failed = email_stats.get("failed", 0)
    except Exception:
        email_sent = 0
        email_failed = 0

    return (
        f"📊 *Web Contractor Stats*\n\n"
        f"📋 *Leads*\n"
        f"  Total: {total_leads}\n"
        f"  Pending Audit: {status_counts.get('pending_audit', 0)}\n"
        f"  Qualified: {status_counts.get('qualified', 0)}\n"
        f"  Unqualified: {status_counts.get('unqualified', 0)}\n\n"
        f"📧 *Emails*\n"
        f"  Sent: {email_sent}\n"
        f"  Failed: {email_failed}\n\n"
        f"🏗️ *Pipeline*\n"
        f"  Status: {'Running' if _pipeline_running else 'Idle'}"
    )


def _run_pipeline_thread(limit: int) -> None:
    """Run pipeline in background thread."""
    global _pipeline_running, _pipeline_result, _pipeline_error, _pipeline_thread
    try:
        assert _app_ref is not None
        result = _app_ref.run_unified_pipeline(limit=limit)
        _pipeline_result = result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        _pipeline_error = str(e)
    finally:
        _pipeline_running = False
        _pipeline_thread = None


def _send_message(text: str, parse_mode: str = "Markdown") -> None:
    """Send message to configured chat."""
    if _notifier is None:
        return
    try:
        _notifier.send_message(text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


def _format_pipeline_result(limit: int) -> str:
    """Format pipeline execution result as text."""
    global _pipeline_result, _pipeline_error

    if _pipeline_error:
        return f"❌ *Pipeline Failed*\n\nError: {_pipeline_error}"

    if not _pipeline_result:
        return "⚠️ Pipeline completed but no results available"

    processed = _pipeline_result.get("processed", 0)
    qualified = _pipeline_result.get("qualified", 0)
    emails_generated = _pipeline_result.get("emails_generated", 0)
    qual_rate = f"{(qualified / processed * 100):.1f}%" if processed > 0 else "N/A"

    return (
        f"✅ *Pipeline Complete*\n\n"
        f"📋 *Results*\n"
        f"  Leads Processed: {processed}\n"
        f"  Qualified: {qualified} ({qual_rate})\n"
        f"  Emails Generated: {emails_generated}\n\n"
        f"📝 Limit: {limit}"
    )


def _watch_pipeline_done(limit: int) -> None:
    """Wait for pipeline to finish and send notification."""
    if _pipeline_thread:
        _pipeline_thread.join()

    if _pipeline_result is None and _pipeline_error is None:
        _send_message("⏹️ Pipeline was cancelled")
    else:
        _send_message(_format_pipeline_result(limit))




def _handle_run(args: list[str]) -> str:
    """Handle /run command. Starts pipeline in background thread."""
    global _pipeline_running, _pipeline_result, _pipeline_error, _pipeline_thread

    if _pipeline_running:
        return "⚠️ Pipeline is already running. Use /cancel to stop."

    limit = 20
    if args:
        try:
            limit = int(args[0])
            if limit < 1 or limit > 100:
                return "⚠️ Limit must be between 1 and 100"
        except ValueError:
            return "⚠️ Invalid limit. Use: /run <number>"

    _pipeline_running = True
    _pipeline_result = None
    _pipeline_error = None

    thread = threading.Thread(target=_run_pipeline_thread, args=(limit,), daemon=True)
    _pipeline_thread = thread
    thread.start()

    threading.Thread(target=_watch_pipeline_done, args=(limit,), daemon=True).start()

    return f"🚀 Starting pipeline with limit={limit}..."


def _handle_audit(args: list[str]) -> str:
    """Handle /audit command."""
    if _pipeline_running:
        return "⚠️ Pipeline is already running. Use /cancel to stop."

    if not args:
        return "⚠️ Usage: /audit <number_of_leads>"

    try:
        limit = int(args[0])
    except ValueError:
        return "⚠️ Invalid number"

    try:
        assert _app_ref is not None
        result = _app_ref.run_audit(limit=limit)
        audited = result.get("audited", 0)
        qualified = result.get("qualified", 0)
        rate = f"{(qualified / audited * 100):.1f}%" if audited > 0 else "N/A"
        return f"✅ *Audit Complete*\n\nAudited: {audited}\nQualified: {qualified} ({rate})"
    except Exception as e:
        logger.error(f"Audit failed: {e}")
        return f"❌ Audit failed: {e}"


def _handle_discovery(args: list[str]) -> str:
    """Handle /discovery command."""
    if _pipeline_running:
        return "⚠️ Pipeline is already running. Use /cancel to stop."

    if not args:
        return "⚠️ Usage: /discovery <number_of_queries>"

    try:
        max_queries = int(args[0])
    except ValueError:
        return "⚠️ Invalid number"

    try:
        assert _app_ref is not None
        result = _app_ref.run_discovery(max_queries=max_queries)
        found = result.get("leads_found", 0)
        saved = result.get("leads_saved", 0)
        return f"✅ *Discovery Complete*\n\nQueries: {max_queries}\nLeads Found: {found}\nLeads Saved: {saved}"
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return f"❌ Discovery failed: {e}"


def _handle_cancel() -> str:
    """Handle /cancel command."""
    global _pipeline_running, _pipeline_result, _pipeline_error, _pipeline_thread

    if not _pipeline_running:
        return "⚠️ No pipeline is currently running"

    _pipeline_running = False
    _pipeline_result = None
    _pipeline_error = "Cancelled"
    return "⏹️ Pipeline cancellation requested..."


def _handle_leads() -> str:
    try:
        from database.connection import get_database

        db = get_database()
        if db is None:
            return "⚠️ Database not connected"

        pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        status_counts = {}
        for doc in db.leads.aggregate(pipeline):
            status_counts[doc["_id"]] = doc["count"]

        total = sum(status_counts.values())
        lines = "\n".join(
            f"  {status}: {count}" for status, count in sorted(status_counts.items())
        )
        return f"📋 *Leads by Status*\n\n{lines}\n\n*Total*: {total}"
    except Exception as e:
        logger.error(f"Error fetching lead stats: {e}")
        return f"❌ Error: {e}"


def _handle_buckets() -> str:
    try:
        from database.connection import get_database

        db = get_database()
        if db is None:
            return "⚠️ Database not connected"

        buckets = list(db.buckets.find({}, {"name": 1, "priority": 1, "daily_email_limit": 1}))
        if not buckets:
            return "📭 No buckets configured"

        lines = "\n".join(
            f"  • {b.get('name', 'unknown')} (priority: {b.get('priority', 1)})"
            for b in sorted(buckets, key=lambda x: x.get("priority", 1))
        )
        return f"📦 *Buckets*\n\n{lines}"
    except Exception as e:
        logger.error(f"Error fetching buckets: {e}")
        return f"❌ Error: {e}"


_COMMANDS: dict[str, Any] = {
    "/start": lambda _a: "🏗️ *Web Contractor Bot*\n\n"
        "I can help you monitor and control your pipeline remotely.\n\n"
        "Use /help to see all available commands.",
    "/help": lambda _a: (
        "🏗️ *Web Contractor Bot — Commands*\n\n"
        "/status — Show current stats\n"
        "/leads — Show lead counts by status\n"
        "/run [limit] — Run full pipeline (default: 20)\n"
        "/audit <n> — Audit N pending leads\n"
        "/discovery <n> — Run discovery with N queries\n"
        "/cancel — Cancel running pipeline\n"
        "/buckets — Show bucket summary\n"
        "/help — Show this message"
    ),
    "/status": lambda _a: _get_stats(),
    "/leads": lambda _a: _handle_leads(),
    "/run": _handle_run,
    "/audit": _handle_audit,
    "/discovery": _handle_discovery,
    "/cancel": lambda _a: _handle_cancel(),
    "/buckets": lambda _a: _handle_buckets(),
}


def _handle_command(text: str) -> str | None:
    """Parse a command and return response text. None for unknown commands."""
    if not text.startswith("/"):
        return None

    parts = text.strip().split()
    command = parts[0].lower()
    args = parts[1:]

    handler = _COMMANDS.get(command)
    if handler is not None:
        return handler(args)
    return None  




def _poll_loop() -> None:
    """Main long-polling loop. Runs in a daemon thread."""
    assert _notifier is not None

    bot_info = _notifier.get_me()
    if bot_info is None:
        logger.error("Failed to verify bot identity. Check TELEGRAM_BOT_TOKEN.")
        return

    _notifier.delete_webhook()

    offset: int | None = None

    while not _stop_event.is_set():
        try:
            updates = _notifier.get_updates(offset=offset, timeout=30)

            for update in updates:
                offset = update.get("update_id", 0) + 1

                message = update.get("message")
                if message is None:
                    continue

                chat = message.get("chat", {})
                chat_id = str(chat.get("id", ""))
                if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                text = message.get("text", "")
                if not text:
                    continue

                response = _handle_command(text)
                if response is not None:
                    _send_message(response)
                elif text.startswith("/"):
                    _send_message("❓ Unknown command. Use /help to see available commands.")

        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)




def start_bot_thread(app_instance: Any) -> None:
    """Start Telegram bot as a background thread."""
    global _notifier, _bot_thread, _app_ref

    if not TELEGRAM_BOT_TOKEN:
        return

    if _bot_thread and _bot_thread.is_alive():
        logger.warning("Bot already running")
        return

    _app_ref = app_instance
    _notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    _stop_event.clear()
    _bot_thread = threading.Thread(target=_poll_loop, daemon=True)
    _bot_thread.start()


def stop_bot() -> None:
    """Stop Telegram bot gracefully."""
    global _notifier, _bot_thread

    _stop_event.set()

    if _bot_thread and _bot_thread.is_alive():
        _bot_thread.join(timeout=10)
        _bot_thread = None

    _notifier = None
