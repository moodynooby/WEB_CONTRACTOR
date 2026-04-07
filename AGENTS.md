# Web Contractor - Agent Guidelines


---

## Key Design Decisions

### 1. Decoupled Architecture

- **UI Layer** (`ui/`) handles only presentation and user input
- **Application Core** (`WebContractorApp`) manages service lifecycle
- **Core Services** contain business logic
- UI calls `app_core.run_*()` methods which handle threading internally

### 2. Threading Model

- Long-running operations run in background threads via `app.run_worker()`
- UI updates from threads use `app.call_from_thread()` for thread safety
- No `@work` decorators outside of `App` subclasses
- Unified pipeline is single-threaded for simplicity

### 3. Multi-Agent System

- **Specialized agents**: Each agent has a focused responsibility
- **Sequential execution**: Agents run in configured order
- **Early exit**: Skip remaining agents if thresholds not met
- **Configurable**: Agents, weights, and order defined in JSON
- **LLM-driven**: Dynamic issue detection based on business type

### 4. Resource Sharing

- Single browser instance shared across all audit operations
- HTTP session with connection pooling
- Fresh context per lead (lightweight), not fresh browser

### 5. Database Layer

- **`core/db.py`**: MongoDB connection using Motor (async driver)
- **`core/models.py`**: Dataclass-based models with `to_dict()`/`from_dict()` serialization
- **`core/repository.py`**: All database operations (repository pattern)
- Services import from `repository`, not directly from models
- `run_async()` bridges async MongoDB calls with Streamlit's sync context

### 6. Centralized Configuration

- `Config` class in `app_core.py` loads config files once
- All services share the same configuration instance
- No duplicate config loading across modules

### 7. Reusable UI Components

- `components.py`: Reusable widgets (panels, footers, filters)
- `screens/base.py`: Base classes for common screen patterns
- Reduces duplication across screen implementations

---

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
