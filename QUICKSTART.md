# Quick Start Guide - Web Contractor TUI

Get started with Web Contractor in under 5 minutes.

## Prerequisites

- Python 3.11+
- Chrome/Chromium browser
- Gmail account with App Password

## Installation

### Step 1: Install Dependencies

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install textual requests beautifulsoup4 selenium webdriver-manager
```

### Step 2: Configure Environment

Create `.env` file:

```bash
GMAIL_EMAIL=your-email@gmail.com
GMAIL_PASSWORD=your-16-char-app-password
```

**Get Gmail App Password**: https://myaccount.google.com/apppasswords

### Step 3: Initialize Database

```bash
source .venv/bin/activate  # Activate virtual environment
python cli.py init
```

## Usage

### Option 1: Textual TUI (Recommended)

Launch the interactive terminal interface:

```bash
python main_tui.py
```

**Key Bindings**:
- `d` - Run Discovery (query generation + lead scraping)
- `a` - Run Audit (website auditing)
- `g` - Generate Emails (personalized email creation)
- `s` - Send Emails (SMTP delivery)
- `r` - Refresh Statistics
- `q` - Quit

### Option 2: CLI Commands

Use command-line interface for automation:

```bash
# Run discovery pipeline
python cli.py discovery --queries 5

# Audit pending leads
python cli.py audit --limit 20

# Generate emails for qualified leads
python cli.py generate --limit 10

# Send pending emails
python cli.py send --limit 5

# View statistics
python cli.py stats
```

## First Run Workflow

### 1. Run Discovery

```bash
python cli.py discovery --queries 5
```

This will:
- Generate 5 search queries from your bucket configuration
- Scrape Google Maps for business leads
- Fall back to Yellow Pages if needed
- Save leads to database

**Expected Output**:
```
============================================================
DISCOVERY: Query Generation + Lead Scraping
============================================================
Generated 5 search queries

[1/5] Interior Designers Mumbai
  ✓ Acme Interiors
  ✓ Design Studio XYZ
  ...

Discovery Complete: 15 found, 12 saved
```

### 2. Audit Leads

```bash
python cli.py audit --limit 20
```

This will:
- Fetch pending leads from database
- Audit each website for technical issues
- Score and qualify leads
- Update database with results

**Expected Output**:
```
============================================================
OUTREACH: Lead Auditing
============================================================
Auditing 20 leads...

[1/20] Acme Interiors
  ✓ Qualified (Score: 55, Issues: 4)

[2/20] Design Studio XYZ
  ✗ Not qualified (Score: 85)

Auditing Complete: 20 audited, 8 qualified
```

### 3. Generate Emails

```bash
python cli.py generate --limit 10
```

This will:
- Get qualified leads without emails
- Generate personalized emails using Ollama LLM (if available) or templates
- Save emails to database

**Expected Output**:
```
============================================================
OUTREACH: Email Generation
============================================================
Generating emails for 10 qualified leads...

[1/10] Acme Interiors
  ✓ Email generated

Email Generation Complete: 10 emails created
```

### 4. Send Emails

```bash
python cli.py send --limit 5
```

This will:
- Get pending emails from database
- Send via Gmail SMTP
- Mark as sent/failed

**Expected Output**:
```
============================================================
EMAIL SENDER: Sending Pending Emails
============================================================
Sending 5 emails...

[1/5] Acme Interiors
  ✓ Sent to info@acmeinteriors.com

Email Sending Complete: 5 sent, 0 failed
```

### 5. Check Stats

```bash
python cli.py stats
```

**Expected Output**:
```
========================================
Web Contractor Statistics
========================================
Total Leads:      52
Qualified Leads:  12
Emails Sent:      5
Emails Pending:   7
========================================
```

## Configuration

### Bucket Configuration

Edit `config/buckets.json` to customize:

- **Geographic targeting**: Cities, regions
- **Business categories**: Industries to target
- **Search patterns**: Query templates
- **Monthly targets**: Lead goals

### Email Templates

Edit `config/email_templates.json` to customize:

- **Subject patterns**
- **Body templates**
- **Tone and style**
- **Call-to-action**

## Automation

### Cron Setup

```bash
# Edit crontab
crontab -e

# Daily discovery at 2 AM
0 2 * * * cd /path/to/project && /path/to/.venv/bin/python cli.py discovery --queries 20

# Hourly audit
0 * * * * cd /path/to/project && /path/to/.venv/bin/python cli.py audit --limit 30

# Send emails every 2 hours
0 */2 * * * cd /path/to/project && /path/to/.venv/bin/python cli.py send --limit 10
```

### Screen/Tmux

```bash
# Start in background
screen -S web-contractor
python main_tui.py

# Detach: Ctrl+A, D

# Reattach
screen -r web-contractor
```

## Troubleshooting

### Chrome driver issues

```bash
# Test Selenium setup
python -c "from selenium import webdriver; driver = webdriver.Chrome(); driver.quit()"
```

### Ollama not available

Ollama is optional. If not installed, the system will use template-based email generation.

To install Ollama:

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull model
ollama pull qwen3:8b

# Verify
curl http://localhost:11434/api/tags
```

### Database locked

```bash
# Close all connections
pkill -f "python cli.py"
pkill -f "python main_tui.py"

# Reset database
rm leads.db
python cli.py init
```

### Gmail SMTP authentication failed

1. Use App Password, not regular password
2. Enable 2-factor authentication
3. Generate App Password: https://myaccount.google.com/apppasswords
4. Use the 16-character code in `.env`

## Next Steps

1. **Customize buckets**: Edit `config/buckets.json` for your target markets
2. **Customize templates**: Edit `config/email_templates.json` for your messaging
3. **Scale discovery**: Increase `--queries` parameter
4. **Monitor results**: Use `python cli.py stats` regularly
5. **Automate**: Set up cron jobs for hands-free operation

## Support

- **Documentation**: See `README_TUI.md` for detailed docs
- **Migration Guide**: See `MIGRATION_GUIDE.md` if upgrading from Flask
- **Architecture**: See `ARCHITECTURE_COMPARISON.md` for design details

## Tips

- **Start small**: Run with `--queries 5` or `--limit 10` initially
- **Review emails**: Check generated emails before sending at scale
- **Monitor performance**: Use TUI for real-time feedback
- **Backup database**: `cp leads.db leads.db.backup` before major operations
- **Use CLI for automation**: TUI for interactive, CLI for scripts

Happy lead hunting! 🎯
