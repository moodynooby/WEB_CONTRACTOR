# Web Contractor - Agent Guidelines

## Development

### Commands

```bash
uv sync                   # install deps
uv run python main.py     # launch PyQt6 GUI

# Service manager (cross-platform):
uv run python main.py run       # Launch PyQt6 GUI
uv run python main.py bot       # Start Telegram bot
uv run python main.py status    # Show service status
uv run python main.py stop      # Stop all services
uv run --active mkdocs build  # serve docs
uv run --active mkdocs gh-deploy
# Scripts:
uv run python scripts/setup.py        # Interactive setup wizard

# Before every commit:
uv run ruff check --fix .
uv run ty check
```

### Type Hints Philosophy

- **Pragmatic approach**: This is an app, not a library
- Use simple types: `list`, `dict`, `str | None` instead of `List[Dict]`, `Optional[str]`
- Mypy configured to ignore ORM/framework dynamic attributes
- Type hints help IDE autocomplete, not fight the type system

---

## Configuration

### Telegram Notifications (Optional)

Get **critical-only** pipeline execution notifications directly on your phone via Telegram:

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
   uv run python main.py bot
   ```

5. **Notifications you'll receive (critical only):**
   - ✅ Pipeline started
   - ✅ Pipeline completed (full summary)
   - ❌ Errors / stage failures

6. **Interactive bot commands:**
   - `/status` — Show current pipeline stats
   - `/run <limit>` — Run full pipeline remotely
   - `/audit <n>` — Audit N pending leads
   - `/cancel` — Cancel running pipeline
   - `/help` — Show all commands

> **Note:** Pipeline will run without notifications if Telegram is not configured. The bot is optional — critical notifications are sent from the pipeline itself even without the interactive bot.
