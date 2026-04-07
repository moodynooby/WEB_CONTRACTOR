# Web Contractor - Agent Guidelines

## Development

### Commands

```bash
uv sync                   # install deps
uv run python main.py     # run app

# Before every commit:
uv run ruff check --fix . && uv run uncomment . && uv run mypy .
```

### Type Hints Philosophy

- **Pragmatic approach**: This is an app, not a library
- Use simple types: `list`, `dict`, `str | None` instead of `List[Dict]`, `Optional[str]`
- Mypy configured to ignore ORM/framework dynamic attributes
- Type hints help IDE autocomplete, not fight the type system

---

## Configuration

### Telegram Notifications (Optional)

Get pipeline execution notifications directly on your phone via Telegram:

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

4. **Notifications you'll receive:**
   - ✅ Pipeline started
   - ✅ Each stage completion (with metrics)
   - ✅ Pipeline fully completed (summary)
   - ❌ Stage failures (with error details)
   - ❌ Pipeline-level errors

> **Note:** Pipeline will run without notifications if Telegram is not configured.
