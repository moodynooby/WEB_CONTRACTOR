# Web Contractor - Ultra-Minimal TUI Edition

**Lead Generation & Outreach Automation with Terminal Interface**

## 🎯 Architecture Overview

**From**: Flask API (16+ endpoints, 4-stage pipeline, 1000+ lines, 19 dependencies)  
**To**: Textual TUI (2 core modules, ~410 lines, 5 dependencies)

### Core Modules (2)

1. **Discovery** (`discovery.py`): Query Generation (Stage 0) + Lead Scraping (Stage A)
2. **Outreach** (`outreach.py`): Lead Auditing (Stage B) + Email Generation (Stage C)

### Support Files (4)

- `main_tui.py`: Textual TUI interface with key bindings
- `lead_repository.py`: Simplified SQLite database operations
- `email_sender.py`: Direct SMTP email sending
- `pyproject.toml`: 5 essential dependencies

## 🚀 Quick Start

### Installation

```bash
# Install dependencies with uv
uv sync

# Or with pip
pip install textual requests beautifulsoup4 selenium webdriver-manager
```

### Configuration

Create `.env` file:

```bash
GMAIL_EMAIL=your-email@gmail.com
GMAIL_PASSWORD=your-app-password
```

### Run TUI

```bash
python main_tui.py
```

## ⌨️ Key Bindings

| Key | Action | Description |
|-----|--------|-------------|
| `d` | Discovery | Run query generation + lead scraping |
| `a` | Audit | Audit pending leads for technical issues |
| `g` | Generate | Generate personalized emails for qualified leads |
| `s` | Send | Send pending emails via SMTP |
| `r` | Refresh | Refresh statistics display |
| `q` | Quit | Exit application |

## 📊 TUI Features

- **Real-time Statistics**: Total leads, qualified leads, emails sent, pending emails
- **Activity Log**: Live feed of all operations with color-coded status
- **Button Controls**: Click or use keyboard shortcuts
- **Background Processing**: Non-blocking operations with worker threads
- **Visual Feedback**: Progress indicators and status updates

## 🔧 Module Details

### Discovery Module (`discovery.py`)

**Consolidates**: Stage 0 (Planning) + Stage A (Scraping)

```python
from discovery import Discovery

discovery = Discovery()
result = discovery.run(bucket_name="Interior Designers", max_queries=5)
# Returns: {"queries_executed": 5, "leads_found": 15, "leads_saved": 12}
```

**Features**:
- Generates targeted search queries from bucket configuration
- Scrapes Google Maps for business listings (Selenium)
- Scrapes Yellow Pages as fallback (requests + BeautifulSoup)
- Saves leads to SQLite database
- Built-in rate limiting

### Outreach Module (`outreach.py`)

**Consolidates**: Stage B (Auditing) + Stage C (Email Generation)

```python
from outreach import Outreach

outreach = Outreach()

# Audit leads
audit_result = outreach.audit_leads(limit=20)
# Returns: {"audited": 20, "qualified": 8}

# Generate emails
email_result = outreach.generate_emails(limit=10)
# Returns: {"generated": 10}
```

**Audit Checks**:
- Page title and meta description
- Mobile-friendly viewport
- Heading structure (H1)
- Image alt text
- Google Analytics
- SSL/HTTPS
- Load time performance

**Email Generation**:
- Ollama LLM integration (optional)
- Template-based fallback
- Personalized based on audit findings

### Email Sender (`email_sender.py`)

**Direct SMTP** (no Flask-Mail dependency)

```python
from email_sender import EmailSender

sender = EmailSender()
result = sender.send_pending_emails(limit=10)
# Returns: {"sent": 8, "failed": 2}
```

### Lead Repository (`lead_repository.py`)

**Simplified database operations**

```python
from lead_repository import LeadRepository

repo = LeadRepository()
repo.setup_database()

# Get stats
stats = repo.get_stats()
# Returns: {"total_leads": 150, "qualified_leads": 45, ...}

# Get pending audits
leads = repo.get_pending_audits(limit=50)

# Get qualified leads
qualified = repo.get_qualified_leads(limit=20)
```

## 📦 Dependencies (5 Essential)

```toml
dependencies = [
    "textual>=0.47.0",        # Terminal UI framework
    "requests>=2.32.5",       # HTTP client
    "beautifulsoup4>=4.14.3", # HTML parsing
    "selenium>=4.40.0",       # Browser automation
    "webdriver-manager>=4.0.0" # Chrome driver management
]
```

**Removed**:
- Flask & Flask ecosystem (flask-mail, flask-limiter, flask-cors)
- Marshmallow validation
- APScheduler
- Loguru
- python-dotenv (optional, standard library alternative)

## 🗂️ Configuration Files

Both files are preserved from the original architecture:

- `config/buckets.json`: Lead bucket definitions, geographic targeting
- `config/email_templates.json`: Email templates by bucket and issue type

## 🔄 Workflow

```
1. Discovery [d]
   ├─ Generate search queries from buckets
   ├─ Scrape Google Maps (Selenium)
   ├─ Scrape Yellow Pages (requests)
   └─ Save leads → Database

2. Audit [a]
   ├─ Get pending leads
   ├─ Audit website (requests + BeautifulSoup)
   ├─ Score & identify issues
   └─ Mark as qualified/unqualified

3. Generate [g]
   ├─ Get qualified leads
   ├─ Generate emails (Ollama LLM or template)
   └─ Save to email_campaigns table

4. Send [s]
   ├─ Get pending emails
   ├─ Send via SMTP (smtplib)
   └─ Mark as sent/failed
```

## 📈 Code Reduction

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| Dependencies | 19 | 5 | -73% |
| Core Files | 11+ | 4 | -63% |
| Lines of Code | ~1000+ | ~410 | -59% |
| Modules | Flask API | Textual TUI | New paradigm |

## 🛠️ Optional: Ollama Integration

For AI-powered email generation:

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull model
ollama pull qwen3:8b

# Ollama will be auto-detected
# Falls back to templates if unavailable
```

## 🔒 Security

- Gmail App Password required (not regular password)
- SMTP credentials via environment variables
- No external API keys needed
- Local-first architecture

## 📝 Database Schema

**Simplified 3-table schema**:

```sql
-- Core leads table
CREATE TABLE leads (
    id INTEGER PRIMARY KEY,
    business_name TEXT NOT NULL,
    website TEXT UNIQUE,
    status TEXT DEFAULT 'pending_audit',
    bucket TEXT,
    ...
);

-- Audit results
CREATE TABLE audits (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER,
    score INTEGER,
    issues_json TEXT,
    qualified INTEGER,
    ...
);

-- Email campaigns
CREATE TABLE email_campaigns (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER,
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT 'pending',
    ...
);
```

## 🎨 TUI Screenshot

```
┌─ Web Contractor - Ultra-Minimal TUI ────────────────────────┐
│                                                              │
│ ┌─ Statistics ─────────────────────────────────────────────┐│
│ │  Total Leads    Qualified     Emails Sent    Pending     ││
│ │      150           45             32            8        ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Controls ───────────────────────────────────────────────┐│
│ │ [Discovery] [Audit] [Generate] [Send] [Refresh]          ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Activity Log ───────────────────────────────────────────┐│
│ │ ✓ Discovery complete: 15 leads found, 12 saved           ││
│ │ ℹ Starting Audit Pipeline...                             ││
│ │ ✓ Audit complete: 20 audited, 8 qualified                ││
│ │ ✓ Email generation complete: 10 emails created           ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ [d] Discovery [a] Audit [g] Generate [s] Send [q] Quit      │
└──────────────────────────────────────────────────────────────┘
```

## 🚦 Status

✅ **Production Ready**

- All core business logic preserved
- Simplified architecture
- Modern terminal interface
- Zero API overhead
- Faster development iteration

## 📄 License

MIT
