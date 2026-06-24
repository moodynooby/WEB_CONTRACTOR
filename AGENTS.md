# Web Contractor - Agent Guidelines

## Development

### Commands

```bash
uv sync                   # install deps

# Web UI (Streamlit):
uv run streamlit run src/streamlit_app/Home.py

# Telegram bot:
uv run python main.py bot       # Start Telegram bot
uv run python main.py status    # Show service status


# Scripts:
uv run python scripts/setup.py        # Interactive setup wizard
```

### Before every commit:

```bash
uv run ruff check --fix .
uv run ty check
```

### Type Hints Philosophy

- **Pragmatic approach**: This is an app, not a library
- Use simple types: `list`, `dict`, `str | None` instead of `List[Dict]`, `Optional[str]`
- Mypy configured to ignore ORM/framework dynamic attributes
- Type hints help IDE autocomplete, not fight the type system
