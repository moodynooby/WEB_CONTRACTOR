# Web Contractor

Lead generation and outreach automation system for web contractors.

## Features

- Automated lead scraping from Google Maps and websites
- Technical website auditing and analysis
- AI-powered personalized email generation
- Automated outreach campaigns
- Analytics and tracking

## Tech Stack

- **Backend**: Flask, Python 3.11+
- **Database**: SQLite
- **Scraping**: Selenium, BeautifulSoup4
- **Email**: Flask-Mail, Gmail SMTP
- **Scheduling**: APScheduler
- **AI**: Local Ollama integration
- **Analytics**: Google Sheets API

## Installation

```bash
# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your configuration
```

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Code formatting
uv run black .

# Type checking
uv run mypy .

# Security check
uv run bandit -r .
uv run safety check
```

## Usage

```bash
# Run the application
uv run python main.py
```

## Project Structure

- `agents/` - AI agents for email generation and quality control
- `core/` - Core business logic and database operations
- `scrapers/` - Web scraping modules
- `templates/` - HTML templates for the web interface

## License

MIT License
