# Web Contractor - Agent Guidelines

Naming convention PEP 8 (find docs at agent_contexts/agents_validator.md)
### Layered Architecture

```
┌─────────────────────────────────────────────────────────┐
│  UI Layer (ui/)                                         │
│  ├── app.py              - Main TUI application         │
│  ├── dashboard.py        - Dashboard composition        │
│  ├── controllers.py      - Navigation & commands        │
│  ├── components.py       - Reusable UI widgets          │
│  └── screens/            - Individual screens           │
│      ├── base.py         - Base screen classes          │
│      ├── database.py     - Database browser             │
│      ├── review.py       - Email review                 │
│      └── market.py       - Market expansion             │
└───────────────────┬─────────────────────────────────────┘
                    │ uses
┌───────────────────▼─────────────────────────────────────┐
│  Application Core (core/app_core.py)                    │
│  ├── WebContractorApp    - Unified service layer        │
│  └── Config              - Centralized configuration    │
└───────────────────┬─────────────────────────────────────┘
                    │ uses
┌───────────────────▼─────────────────────────────────────┘
│  Core Services                                          │
│  ├── discovery.py        - Query gen + lead scraping    │
│  ├── outreach.py         - Auditing + email generation  │
│  ├── email.py            - SMTP email sender            │
│  ├── llm.py              - Ollama LLM wrapper           │
│  ├── db_models.py        - Peewee ORM models            │
│  └── db_repository.py    - Database operations          │
└─────────────────────────────────────────────────────────┘
```

### Pipeline (Sequential Stages)

| Stage | Name | Module | Input → Output |
|-------|------|--------|----------------|
| 0 | Query Generation | `discovery.py` | Bucket categories → search queries w/ geo placeholders |
| A | Lead Scraping | `discovery.py` | Search queries → `Lead` rows (`pending_audit`) |
| B | Lead Auditing | `outreach.py` | Lead URLs → quality scores + issue flags |
| C | Email Generation | `outreach.py` | Lead + audit context → `EmailCampaign` drafts |
| D | Email Delivery | `email.py` | Approved campaigns → sent emails |

**Data Flow**:
1. User triggers discovery → Stage 0 generates queries → Stage A scrapes → saves to `Lead`
2. User runs audit → Stage B scores leads → Stage C generates emails → saves to `EmailCampaign`
3. User reviews emails in TUI → approves/rejects/edits
4. User sends emails → Stage D dispatches → marks sent

**Entry point**: `main.py` → loads `.env` → init DB → launch TUI.

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

### 3. Database Layer Split
- **`db_models.py`**: Pure Peewee ORM model definitions
- **`db_repository.py`**: All database operations (repository pattern)
- Services import from `db_repository`, not directly from models

### 4. Centralized Configuration
- `Config` class in `app_core.py` loads config files once
- All services share the same configuration instance
- No duplicate config loading across modules

### 5. Reusable UI Components
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

### File Structure
```
WEB_CONTRACTOR/
├── main.py               # Entry point
├── pyproject.toml        # Dependencies
├── config/               # JSON config files
│   ├── app_settings.json
│   ├── audit_settings.json
│   └── email_prompts.json
├── core/
│   ├── app_core.py       # Unified application layer
│   ├── db_models.py      # Peewee ORM models
│   ├── db_repository.py  # Database operations
│   ├── discovery.py      # Query generation + scraping
│   ├── outreach.py       # Auditing + email generation
│   ├── email.py          # SMTP sender
│   └── llm.py            # Ollama wrapper
└── ui/
    ├── app.py            # Main TUI application
    ├── dashboard.py      # Dashboard manager
    ├── controllers.py    # Navigation controller
    ├── components.py     # Reusable widgets
    └── screens/
        ├── base.py       # Base screen classes
        ├── database.py   # Database browser screen
        ├── review.py     # Email review screen
        ├── logs.py       # Logs & performance screens
        └── market.py     # Market expansion screen
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Language** | Python 3.12+ |
| **Package Manager** | `uv` (not pip, not poetry) |
| **Database** | SQLite via `peewee` ORM |
| **Scraping** | `playwright` (sync API only) |
| **LLM** | Ollama (local) via `llm.py` wrapper |
| **TUI** | `textual` |
| **Email** | `smtplib` (stdlib) |
| **Linting** | `ruff` |
| **Type Checking** | `mypy` (pragmatic config) |
| **Dead Comment Removal** | `uncomment` |

---

## Common Patterns

### Running Background Operations
```python
# In UI action handler
def action_run_something(self) -> None:
    self.run_worker(self.app_core.run_something, exclusive=True, thread=True)
```

### Thread-Safe UI Updates
```python
# In background thread
self.app.call_from_thread(self.app.notify, "Operation complete")
self.app.call_from_thread(self.app.dashboard.update_status, "Idle")
```

### Database Operations
```python
# Import from repository, not models
from core.db_repository import get_all_buckets, save_lead

# Use in services
buckets = get_all_buckets()
save_lead(lead_data)
```

### Screen Navigation
```python
# Push a screen
self.push_screen(DatabaseScreen())

# Dismiss current screen
self.dismiss()
```
