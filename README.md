# Web Contractor

## Configuration

All config is in Python. Edit directly in `src/infra/config_defaults.py`:

```python
# Example: Change LLM provider
CONFIG = {
    "llm": {
        "provider": "groq",  # change to "openrouter"
        "default_model": "llama-3.1-8b-instant",
        ...
    }
}
```

**Optional override:** Create `src/infra/config_override.json` for user-specific values. These merge with defaults (deep merge).

## Quick Start

```bash
uv sync                   # install deps
uv run python cli.py     # launch Streamlit
```

## Service Manager (Cross-Platform)

`cli.py` is the single entry point for all services — works on Linux, macOS, and Windows.

```bash
uv run python cli.py run       # Launch Streamlit (default)
uv run python cli.py bot       # Start Telegram bot (background)
uv run python cli.py status    # Show service status
uv run python cli.py stop      # Stop all services
uv run python cli.py setup     # Full setup: deps + auth + start all
uv run python cli.py verify    # Health check
```

## Telegram Integration

### Critical-Only Notifications

Get pipeline execution notifications directly on your phone via Telegram. Only **critical** events are sent:

- ✅ Pipeline started
- ✅ Pipeline completed (full summary with all stage metrics)
- ❌ Errors / stage failures (with traceback)

### Interactive Bot Commands

The Telegram bot also provides interactive commands for remote control:

| Command | Description |
| `/status` | Show current pipeline stats |
| `/run <limit>` | Run full pipeline remotely |
| `/audit <n>` | Audit N pending leads |
| `/discovery <n>` | Run discovery with N queries |
| `/cancel` | Cancel running pipeline |
| `/leads` | Show lead counts by status |
| `/buckets` | Show bucket summary |
| `/help` | Show all commands |

### Setup

1. **Create a Telegram Bot:**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` command
   - Follow the instructions to create your bot
   - Copy the **bot token** (looks like: `123456789:ABCdef...`)

2. **Get your Chat ID:**
   - Search for `@userinfobot` on Telegram
   - Send `/start` or any message
   - It will reply with your **Chat ID** (a number like `123456789`)

3. **Configure in `.env`:**

   ```bash
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

4. **Start the bot:**

   ```bash
   uv run python cli.py bot
   ```

> **Note:** Pipeline will run without notifications if Telegram is not configured. The bot is optional — you get critical notifications from the pipeline even without running the bot separately.
