# Web Contractor - Agent Development Guidelines

This file contains build commands, code style guidelines, and development practices for agentic coding agents working on the Web Contractor lead management system.

## Build, Lint, and Test Commands

### Environment Setup
```bash
# Install dependencies using uv (recommended)
uv sync

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows
```

### Code Quality Commands
```bash
# Run linting and formatting checks
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code with ruff
uv run ruff format .

# Type checking
uv run mypy .

# Type check specific file
uv run mypy main.py
```

### Testing Commands
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest test_discovery.py

# Run specific test function
uv run pytest test_discovery.py::test_scrape_leads

# Run tests with coverage
uv run pytest --cov=.

# Run tests with verbose output
uv run pytest -v
```

### Application Commands
```bash
# Run the main TUI application
uv run python main.py


## Code Style Guidelines

### Import Organization
- **Standard library imports first**: `os`, `sys`, `json`, `time`, etc.
- **Third-party imports second**: `requests`, `bs4`, `selenium`, `textual`, etc.
- **Local imports third**: `lead_repository`, `discovery`, `outreach`, etc.
- **Use explicit imports**: Avoid `from module import *`
- **Group related imports**: Keep imports from the same package together

```python
# ✅ Good import style
import json
import time
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup
from selenium import webdriver

from lead_repository import LeadRepository
from discovery import Discovery
```

### Type Annotations
- **Always annotate function signatures**: Use `typing` for parameters and return types
- **Use Optional for nullable types**: `Optional[str]` instead of `str | None` for consistency
- **Annotate class attributes**: Add type hints for class-level variables
- **Use generic types**: `List[str]`, `Dict[str, int]` for collections

```python
# ✅ Good type annotations
def process_lead(self, lead_id: int, data: Dict[str, str]) -> Optional[bool]:
    """Process a lead with given data"""
    return True

class Discovery:
    def __init__(self, repo: Optional[LeadRepository] = None):
        self.repo: LeadRepository = repo or LeadRepository()
        self.buckets: List[Dict] = []
```

### Naming Conventions
- **Classes**: PascalCase (`LeadRepository`, `Discovery`, `ReviewScreen`)
- **Functions/Methods**: snake_case (`process_lead`, `get_connection`, `scrape_leads`)
- **Variables**: snake_case (`lead_data`, `email_template`, `audit_results`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_WORKERS`, `DEFAULT_TIMEOUT`, `SMTP_PORT`)
- **Private methods**: Prefix with underscore (`_get_driver`, `_load_settings`)

### Error Handling
- **Use specific exceptions**: Catch `ValueError`, `KeyError` instead of generic `Exception`
- **Always log errors**: Use the provided logger or print with context
- **Provide fallback values**: Return sensible defaults when operations fail
- **Clean up resources**: Use `finally` blocks or context managers for cleanup

```python
# ✅ Good error handling
def scrape_leads(self, query: str) -> List[Dict]:
    try:
        driver = self._get_driver()
        results = self._perform_search(driver, query)
        return results
    except WebDriverException as e:
        self.log(f"Selenium error during scraping: {e}", "error")
        return []
    except Exception as e:
        self.log(f"Unexpected error during scraping: {e}", "error")
        return []
    finally:
        self._quit_driver()
```

### Database Operations
- **Use context managers**: Always use `with repo:` for database transactions
- **Handle connection errors**: Wrap database operations in try-catch blocks
- **Use parameterized queries**: Prevent SQL injection with proper parameter binding
- **Close connections**: Use context managers or explicit connection closing

```python
# ✅ Good database pattern
def save_lead(self, lead_data: Dict[str, str]) -> Optional[int]:
    try:
        with self.repo as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO leads (business_name, email, website)
                VALUES (?, ?, ?)
            """, (lead_data['name'], lead_data['email'], lead_data['website']))
            return cursor.lastrowid
    except sqlite3.Error as e:
        self.log(f"Database error saving lead: {e}", "error")
        return None
```

### Threading and Concurrency
- **Use ThreadPoolExecutor**: For parallel processing of audits/generations
- **Limit concurrent operations**: Respect `max_workers` setting (default: 5)
- **Thread-safe UI updates**: Use `call_from_thread` for UI updates from workers
- **Avoid shared state**: Pass data explicitly between threads

### Configuration Management
- **Use environment variables**: For sensitive data (email credentials, API keys)
- **Load JSON configs**: Use proper error handling for configuration files
- **Provide defaults**: Always have fallback values for missing configuration
- **Validate config**: Check required fields and data types

### Code Structure
- **Single responsibility**: Each class/method should have one clear purpose
- **Keep methods small**: Prefer methods under 50 lines when possible
- **Use composition**: Prefer dependency injection over inheritance
- **Document public methods**: Add docstrings for public APIs

### Textual TUI Specific
- **Use proper bindings**: Define keyboard shortcuts in `BINDINGS` class attribute
- **Handle screen navigation**: Use `app.pop_screen()` for modal dismissal
- **Update UI safely**: Use `call_from_thread` for updates from background workers
- **Manage focus**: Handle cursor position and selection state properly

### Testing Guidelines
- **Write unit tests**: For core business logic and data processing
- **Mock external dependencies**: Use unittest.mock for web requests, database
- **Test error cases**: Verify proper error handling and fallback behavior
- **Use descriptive test names**: `test_scrape_leads_with_invalid_query`

### Security Considerations
- **Never commit secrets**: Keep `.env` files out of version control
- **Validate user input**: Sanitize data from web scraping and user input
- **Use parameterized queries**: Prevent SQL injection in database operations
- **Handle credentials securely**: Use environment variables for SMTP/API keys

## Common Issues to Watch For

### Missing Imports
- `time` module often used but not imported
- `urllib.parse` for URL operations
- Proper typing imports from `typing` module

### Resource Cleanup
- Selenium drivers: Always call `driver.quit()` in `finally` block
- Database connections: Use context managers or explicit closing
- SMTP connections: Use `with` statements for SMTP sessions

### Error Recovery
- Web scraping: Implement retry logic for transient failures
- Database operations: Handle connection timeouts and lock errors
- Email sending: Validate credentials and handle SMTP errors

### Performance
- Limit concurrent operations to avoid overwhelming target websites
- Use connection pooling for database operations when possible
- Implement proper timeout handling for network requests

## Development Workflow

1. **Before making changes**: Run `uv run ruff check .` and `uv run mypy .`
2. **Make changes**: Follow the code style guidelines above
3. **Test locally**: Run the application and verify functionality
4. **Run quality checks**: `uv run ruff check --fix .` and `uv run mypy .`
5. **Run tests**: `uv run pytest` if tests exist
6. **Commit changes**: Use descriptive commit messages

This project uses an ultra-minimal architecture with 4 core modules. Keep changes focused and maintain the simplicity of the design.