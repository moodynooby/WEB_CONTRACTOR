"""Telegram Bot — Remote command interface for Web Contractor.

Provides bot commands to monitor and control pipeline execution remotely.

Commands:
    /start        — Show help message
    /status       — Show current pipeline stats
    /leads        — Show lead counts by status
    /run          — Run full pipeline (default limit: 20)
    /run <limit>  — Run pipeline with specific lead limit
    /audit <n>    — Audit N pending leads
    /discovery <n>— Run discovery with N max queries
    /cancel       — Cancel running pipeline
    /buckets      — Show bucket summary
    /help         — Show all commands

Usage:
    uv run python -m core.telegram_bot

Requires:
    TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment
    python-telegram-bot (installed via: uv add python-telegram-bot)
"""

import threading
from typing import Any

from core.logging import get_logger
from core.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = get_logger(__name__)

# Global state for pipeline cancellation
_pipeline_state: dict[str, Any] = {
    "running": False,
    "cancelled": False,
    "thread": None,
    "result": None,
    "error": None,
}


def _get_app():
    """Get WebContractorApp instance (avoids circular imports)."""
    from core.app_core import WebContractorApp

    app = WebContractorApp()
    app.initialize()
    return app


def _get_stats() -> str:
    """Format current stats as text message."""
    from core.repository import count_leads
    from core.db import get_email_campaign_stats

    total_leads = count_leads()

    try:
        from core.db import get_database

        db = get_database()
        if db is None:
            status_counts = {"pending_audit": 0, "qualified": 0, "unqualified": 0}
        else:
            pipeline = [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]
            status_counts = {}
            for doc in db.leads.aggregate(pipeline):
                status_counts[doc["_id"]] = doc["count"]
    except Exception:
        status_counts = {}

    pending = status_counts.get("pending_audit", 0)
    qualified = status_counts.get("qualified", 0)
    unqualified = status_counts.get("unqualified", 0)

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
        f"  Pending Audit: {pending}\n"
        f"  Qualified: {qualified}\n"
        f"  Unqualified: {unqualified}\n\n"
        f"📧 *Emails*\n"
        f"  Sent: {email_sent}\n"
        f"  Failed: {email_failed}\n\n"
        f"🏗️ *Pipeline*\n"
        f"  Status: {'Running' if _pipeline_state['running'] else 'Idle'}"
    )


def _run_pipeline_thread(limit: int) -> None:
    """Run pipeline in background thread."""
    global _pipeline_state
    try:
        app = _get_app()
        result = app.run_unified_pipeline(limit=limit)
        _pipeline_state["result"] = result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        _pipeline_state["error"] = str(e)
    finally:
        _pipeline_state["running"] = False
        _pipeline_state["thread"] = None


def _format_pipeline_result(limit: int) -> str:
    """Format pipeline execution result as text."""
    global _pipeline_state

    if _pipeline_state.get("error"):
        return f"❌ *Pipeline Failed*\n\nError: {_pipeline_state['error']}"

    result = _pipeline_state.get("result", {})
    if not result:
        return "⚠️ Pipeline completed but no results available"

    processed = result.get("processed", 0)
    qualified = result.get("qualified", 0)
    emails_generated = result.get("emails_generated", 0)

    qual_rate = f"{(qualified / processed * 100):.1f}%" if processed > 0 else "N/A"

    return (
        f"✅ *Pipeline Complete*\n\n"
        f"📋 *Results*\n"
        f"  Leads Processed: {processed}\n"
        f"  Qualified: {qualified} ({qual_rate})\n"
        f"  Emails Generated: {emails_generated}\n\n"
        f"📝 Limit: {limit}"
    )


def _setup_bot(token: str) -> Any:
    """Set up the Telegram bot with command handlers.

    Args:
        token: Telegram bot token

    Returns:
        Application instance
    """
    try:
        from telegram import Update
        from telegram.ext import (
            Application,
            CommandHandler,
            ContextTypes,
            MessageHandler,
            filters,
        )
    except ImportError:
        logger.error(
            "python-telegram-bot not installed. "
            "Run: uv add python-telegram-bot"
        )
        return None

    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send welcome message with available commands."""
        if update.message is None:
            return
        await update.message.reply_text(
            "🏗️ *Web Contractor Bot*\n\n"
            "I can help you monitor and control your pipeline remotely.\n\n"
            "Use /help to see all available commands.",
            parse_mode="Markdown",
        )

    async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help message with all commands."""
        if update.message is None:
            return
        await update.message.reply_text(
            "🏗️ *Web Contractor Bot — Commands*\n\n"
            "/status — Show current stats\n"
            "/leads — Show lead counts by status\n"
            "/run [limit] — Run full pipeline (default: 20)\n"
            "/audit <n> — Audit N pending leads\n"
            "/discovery <n> — Run discovery with N queries\n"
            "/cancel — Cancel running pipeline\n"
            "/buckets — Show bucket summary\n"
            "/help — Show this message",
            parse_mode="Markdown",
        )

    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show current pipeline stats."""
        if update.message is None:
            return
        stats = _get_stats()
        await update.message.reply_text(stats, parse_mode="Markdown")

    async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show lead counts by status."""
        if update.message is None:
            return
        try:
            from core.db import get_database

            db = get_database()
            if db is None:
                await update.message.reply_text("⚠️ Database not connected")
                return

            pipeline = [
                {"$group": {"_id": "$status", "count": {"$sum": 1}}}
            ]
            status_counts = {}
            for doc in db.leads.aggregate(pipeline):
                status_counts[doc["_id"]] = doc["count"]

            total = sum(status_counts.values())
            lines = "\n".join(
                f"  {status}: {count}" for status, count in sorted(status_counts.items())
            )

            msg = f"📋 *Leads by Status*\n\n{lines}\n\n*Total*: {total}"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error fetching lead stats: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run full pipeline."""
        if update.message is None:
            return

        global _pipeline_state

        if _pipeline_state["running"]:
            await update.message.reply_text(
                "⚠️ Pipeline is already running. Use /cancel to stop."
            )
            return

        limit = 20
        if context.args:
            try:
                limit = int(context.args[0])
                if limit < 1 or limit > 100:
                    await update.message.reply_text(
                        "⚠️ Limit must be between 1 and 100"
                    )
                    return
            except ValueError:
                await update.message.reply_text("⚠️ Invalid limit. Use: /run <number>")
                return

        await update.message.reply_text(
            f"🚀 Starting pipeline with limit={limit}..."
        )

        _pipeline_state = {
            "running": True,
            "cancelled": False,
            "thread": None,
            "result": None,
            "error": None,
        }

        thread = threading.Thread(target=_run_pipeline_thread, args=(limit,), daemon=True)
        _pipeline_state["thread"] = thread
        thread.start()

        # Wait for completion and send result
        def _notify_when_done() -> None:
            thread.join()
            if _pipeline_state.get("cancelled"):
                msg = "⏹️ Pipeline was cancelled"
            else:
                msg = _format_pipeline_result(limit)
            # We can't access update.message here, so we use the notifier directly
            from core.telegram import TelegramNotifier
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                notifier.send_message(msg)

        notify_thread = threading.Thread(target=_notify_when_done, daemon=True)
        notify_thread.start()

    async def cmd_audit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run audit on pending leads."""
        if update.message is None:
            return

        global _pipeline_state

        if _pipeline_state["running"]:
            await update.message.reply_text(
                "⚠️ Pipeline is already running. Use /cancel to stop."
            )
            return

        if not context.args:
            await update.message.reply_text("⚠️ Usage: /audit <number_of_leads>")
            return

        try:
            limit = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Invalid number")
            return

        await update.message.reply_text(f"📋 Auditing {limit} leads...")

        try:
            app = _get_app()
            result = app.run_audit(limit=limit)
            audited = result.get("audited", 0)
            qualified = result.get("qualified", 0)
            rate = f"{(qualified / audited * 100):.1f}%" if audited > 0 else "N/A"

            msg = (
                f"✅ *Audit Complete*\n\n"
                f"Audited: {audited}\n"
                f"Qualified: {qualified} ({rate})"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Audit failed: {e}")
            await update.message.reply_text(f"❌ Audit failed: {e}")

    async def cmd_discovery(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run discovery with specified queries."""
        if update.message is None:
            return

        global _pipeline_state

        if _pipeline_state["running"]:
            await update.message.reply_text(
                "⚠️ Pipeline is already running. Use /cancel to stop."
            )
            return

        if not context.args:
            await update.message.reply_text("⚠️ Usage: /discovery <number_of_queries>")
            return

        try:
            max_queries = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ Invalid number")
            return

        await update.message.reply_text(f"🔍 Running discovery with {max_queries} queries...")

        try:
            app = _get_app()
            result = app.run_discovery(max_queries=max_queries)
            found = result.get("leads_found", 0)
            saved = result.get("leads_saved", 0)

            msg = (
                f"✅ *Discovery Complete*\n\n"
                f"Queries: {max_queries}\n"
                f"Leads Found: {found}\n"
                f"Leads Saved: {saved}"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            await update.message.reply_text(f"❌ Discovery failed: {e}")

    async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Cancel running pipeline."""
        if update.message is None:
            return

        global _pipeline_state

        if not _pipeline_state["running"]:
            await update.message.reply_text("⚠️ No pipeline is currently running")
            return

        _pipeline_state["cancelled"] = True
        await update.message.reply_text("⏹️ Pipeline cancellation requested...")

    async def cmd_buckets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show bucket summary."""
        if update.message is None:
            return
        try:
            from core.db import get_database

            db = get_database()
            if db is None:
                await update.message.reply_text("⚠️ Database not connected")
                return

            buckets = list(db.buckets.find({}, {"name": 1, "priority": 1, "daily_email_limit": 1}))

            if not buckets:
                await update.message.reply_text("📭 No buckets configured")
                return

            lines = "\n".join(
                f"  • {b.get('name', 'unknown')} (priority: {b.get('priority', 1)})"
                for b in sorted(buckets, key=lambda x: x.get("priority", 1))
            )

            msg = f"📦 *Buckets*\n\n{lines}"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error fetching buckets: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def unknown_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle unknown commands."""
        if update.message is None:
            return
        await update.message.reply_text(
            "❓ Unknown command. Use /help to see available commands."
        )

    # Build application
    app = Application.builder().token(token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("audit", cmd_audit))
    app.add_handler(CommandHandler("discovery", cmd_discovery))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("buckets", cmd_buckets))

    # Fallback for unknown commands
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    return app


def main() -> None:
    """Main entry point for Telegram bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Cannot start bot.")
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set. Bot will respond to all chats.")

    print("🤖 Starting Web Contractor Telegram Bot...")
    print(f"   Bot token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"   Chat ID: {TELEGRAM_CHAT_ID or 'any'}")
    print()
    print("Commands available:")
    print("  /status  — Show current stats")
    print("  /run     — Run full pipeline")
    print("  /audit   — Audit pending leads")
    print("  /cancel  — Cancel running pipeline")
    print("  /help    — Show all commands")
    print()

    bot_app = _setup_bot(TELEGRAM_BOT_TOKEN)
    if bot_app is None:
        print("Error: Failed to initialize bot. Is python-telegram-bot installed?")
        print("Install with: uv add python-telegram-bot")
        return

    print("✅ Bot is running! Send /start to begin.")
    bot_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
