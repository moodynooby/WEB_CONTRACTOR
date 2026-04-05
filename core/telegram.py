"""Telegram Notification Service

Sends notifications to Telegram for pipeline events and errors.
"""

import requests
from typing import Optional
from core.logging import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    """Handles sending messages to Telegram via Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        """Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token (from BotFather)
            chat_id: Target chat ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.enabled = True

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to Telegram.

        Args:
            text: Message text (supports Markdown formatting)
            parse_mode: Message parsing mode (default: Markdown)

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Telegram notifier disabled, skipping message")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Telegram message sent successfully")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            self.enabled = False  
            return False

    def notify_pipeline_started(self) -> bool:
        """Send notification that pipeline has started."""
        text = "🏗️ *Web Contractor Pipeline*\n\n🚀 Pipeline execution started..."
        return self.send_message(text)

    def notify_pipeline_completed(self, stats: dict) -> bool:
        """Send notification that pipeline has completed with summary stats.

        Args:
            stats: Dictionary containing pipeline execution statistics
        """
        discovery = stats.get("discovery", {})
        audit = stats.get("audit", {})
        email_gen = stats.get("email_generation", {})
        email_send = stats.get("email_send", {})
        duration = stats.get("total_duration", "N/A")

        text = f"""🏗️ *Web Contractor Pipeline*

✅ *Pipeline Completed Successfully!*

📊 *Stage Results:*

🔍 *Discovery*
• Leads Found: {discovery.get('leads_found', 0)}
• Leads Saved: {discovery.get('leads_saved', 0)}

📋 *Audit*
• Leads Audited: {audit.get('audited', 0)}
• Leads Qualified: {audit.get('qualified', 0)}

📧 *Email Generation*
• Emails Generated: {email_gen.get('generated', 0)}

📤 *Emails Sent*
• Emails Sent: {email_send.get('sent', 0)}

⏱️ *Total Duration*: {duration}"""

        return self.send_message(text)

    def notify_stage_completed(self, stage_name: str, stats: dict) -> bool:
        """Send notification that a pipeline stage has completed.

        Args:
            stage_name: Name of the completed stage
            stats: Stage execution statistics
        """
        stage_emojis = {
            "Discovery": "🔍",
            "Audit": "📋",
            "Email Generation": "📧",
            "Email Send": "📤",
        }
        emoji = stage_emojis.get(stage_name, "⚙️")

        stats_lines = "\n".join([f"• {k}: {v}" for k, v in stats.items()])

        text = f"""🏗️ *Web Contractor Pipeline*

{emoji} *Stage: {stage_name}*
✅ Completed

{stats_lines}"""

        return self.send_message(text)

    def notify_error(
        self,
        stage_name: str,
        error_message: str,
        traceback: Optional[str] = None,
    ) -> bool:
        """Send error notification with optional traceback.

        Args:
            stage_name: Stage where error occurred
            error_message: Human-readable error message
            traceback: Optional full traceback (will be truncated)
        """
        tb_text = ""
        if traceback:
            tb_text = traceback[:500]
            if len(traceback) > 500:
                tb_text += "\n\n...(truncated)"

        text = f"""🏗️ *Web Contractor Pipeline*

🚨 *Pipeline Error*

❌ *Stage*: {stage_name}
📝 *Error*: {error_message}

🔍 *Traceback*:
```
{tb_text}
```

🔧 Please check logs for full details."""

        return self.send_message(text)

    def notify_stage_failed(self, stage_name: str, error_message: str) -> bool:
        """Send notification that a stage has failed.

        Args:
            stage_name: Name of the failed stage
            error_message: Error description
        """
        stage_emojis = {
            "Discovery": "🔍",
            "Audit": "📋",
            "Email Generation": "📧",
            "Email Send": "📤",
        }
        emoji = stage_emojis.get(stage_name, "⚙️")

        text = f"""🏗️ *Web Contractor Pipeline*

{emoji} *Stage: {stage_name}*
❌ Failed

📝 *Error*: {error_message}

⚠️ Pipeline will continue with remaining stages."""

        return self.send_message(text)
