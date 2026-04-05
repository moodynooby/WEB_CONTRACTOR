# Web Contractor - Agent Guidelines

Naming convention PEP 8 (find docs at agent_contexts/agents_validator.md)

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

### 5. Database Layer Split
- **`db_models.py`**: Pure Peewee ORM model definitions
- **`db_repository.py`**: All database operations (repository pattern)
- Services import from `db_repository`, not directly from models

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




docs:
	uv run mkdocs serve

lint:
	uv run ruff check --fix . && uv run uncomment . && uv run mypy .
