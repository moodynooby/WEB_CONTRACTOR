# Web Contractor - Agent Guidelines

## Architecture

**Pipeline Stages**:

- **Stage 0 (Query Generation)**: Uses LLM to expand bucket categories and discover new market segments. Generates search patterns with geographic placeholders.

- **Stage A (Lead Scraping)**: Playwright-based scraper searches business directories, extracts contact info (email, phone, social), stores raw leads to `Lead` table with `pending_audit` status.

- **Stage B (Lead Auditing)**: Fetches lead websites, analyzes content with LLM for quality scoring, detects issues (broken links, missing SSL, etc.). Saves audit results.

- **Stage C (Email Generation)**: Generates personalized cold emails using lead context and LLM. Stores in `EmailCampaign` for review.

- **Stage D (Email Delivery)**: SMTP sender. Sends approved emails, tracks delivery.

**Core Modules** (`core/`):

- **db_peewee.py**: Peewee ORM for SQLite. Models: `Bucket`, `Lead`, `Audit`, `EmailCampaign`. Atomic transactions for batch ops.
- **discovery.py**: Implements Stage 0 + Stage A. Single-threaded with efficient Playwright resource reuse.
- **outreach.py**: Implements Stage B + Stage C. Single-threaded with LRU caching for LLM calls.
- **email.py**: Simplified SMTP sender with direct connections.
- **llm.py**: Ollama API wrapper with retry logic, JSON format support.

**UI Layer** (`ui/app.py`):
Single Textual TUI. Screens: discovery, audit review, email review, settings. Workers use `@work(exclusive=True)` for sequential execution.

**Data Flow**:
1. User triggers discovery → Stage 0 generates queries → Stage A scrapes → saves to `Lead`
2. User runs audit → Stage B scores leads → Stage C generates emails → saves to `EmailCampaign`
3. User reviews emails in TUI → approves/rejects
4. User sends emails → Stage D dispatches → marks sent

**Entry Point**: `main.py` loads env, initializes DB, launches TUI.

## Commands

```bash
# Setup
uv sync
source .venv/bin/activate

# Quality
uv run ruff check .          # lint
uv run ruff check --fix .    # auto-fix
uv run ruff format .         # format
uv run uncomment .   # Uneccesory comments remover
# Run
uv run python main.py
```

## Database (Peewee)

```python
from core.db_peewee import Lead, Bucket, db, save_lead

# Operations
lead = Lead.get_or_none(Lead.id == lead_id)
lead_id = save_lead({'business_name': 'Acme', 'bucket': 'Designers'})

# Transactions
with db.atomic():
    bucket = Bucket.create(name='New')
    Lead.create(business_name='Test', bucket=bucket)

# Batch
with db.atomic():
    for lead_data in leads:
        Lead.create(**lead_data)
```

## Error Handling

- Catch specific exceptions (`ValueError`, `KeyError`)
- Log with context
- Return sensible defaults
- Clean up resources in `finally` or use context managers

## Concurrency

- Single-threaded design for simplicity and reliability
- Workers use `@work(exclusive=True)` for sequential execution
- Playwright browser context is reused across operations
- No shared state issues - each operation runs to completion before next starts

## Textual TUI

- Define shortcuts in `BINDINGS` class attribute
- Use `app.pop_screen()` to dismiss modals
- Use `@work` decorator for background tasks
- Manage focus and selection state properly

## Security

- Never commit `.env` files
- Use environment variables for credentials
- Validate user input

## Resource Management

- **Playwright**: Browser context reused; closed on session exit via `managed_session()`
- **Database**: Peewee handles connections automatically with `thread_safe=True`
- **SMTP**: Direct connections with automatic cleanup via `with` statement

## Workflow

1. Run `uv run ruff check .` before changes
2. Make focused, minimal changes
3. Test locally: `uv run python main.py`
4. Run `uv run ruff check --fix .`
5. Run ` uv run uncomment .   `
6. Commit with descriptive messages

