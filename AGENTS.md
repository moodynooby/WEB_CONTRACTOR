# Lead Management Database Schema

## Overview
This document contains the complete schema and details of the redesigned lead management database with all performance optimizations and enhancements.

## Database Tables

### 1. leads
Core table storing lead information with proper foreign key relationships.

```sql
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT NOT NULL,
    category TEXT,
    location TEXT,
    phone TEXT,
    email TEXT,
    website TEXT UNIQUE,
    source TEXT,
    status TEXT DEFAULT 'pending_audit',
    quality_score REAL DEFAULT 0.5,
    bucket_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_email_sent_at TIMESTAMP,
    FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE SET NULL
);
```

**Fields:**
- `id` - Primary key
- `business_name` - Company/lead name (required)
- `category` - Business category
- `location` - Geographic location
- `phone` - Phone number
- `email` - Email address
- `website` - Website URL (unique)
- `source` - Lead source
- `status` - Current status (pending_audit, qualified, unqualified)
- `quality_score` - Lead quality rating (0.0-1.0)
- `bucket_id` - Foreign key to buckets table
- `created_at` - Creation timestamp
- `last_email_sent_at` - Last email sent timestamp

**Indexes:**
- `idx_leads_status` - For status-based queries
- `idx_leads_bucket` - For bucket segmentation
- `idx_leads_created_at` - For date-range filtering

---

### 2. audits
Stores website audit results with cascading delete.

```sql
CREATE TABLE audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    url TEXT,
    score INTEGER,
    issues_json TEXT,
    qualified INTEGER DEFAULT 0,
    audit_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
);
```

**Fields:**
- `id` - Primary key
- `lead_id` - Foreign key to leads (cascading delete)
- `url` - Audited URL
- `score` - Audit score (0-100)
- `issues_json` - JSON array of issues (legacy)
- `qualified` - Whether lead qualified (0/1)
- `audit_date` - Audit timestamp

**Indexes:**
- `idx_audits_qualified` - For qualified lead queries
- `idx_audits_lead_id` - For JOIN performance

---

### 3. email_campaigns
Enhanced email tracking with engagement metrics and retry logic.

```sql
CREATE TABLE email_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    subject TEXT,
    body TEXT,
    status TEXT DEFAULT 'pending',
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    clicked_at TIMESTAMP,
    replied_at TIMESTAMP,
    bounce_reason TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,
    max_retries INTEGER DEFAULT 3,
    FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE
);
```

**Fields:**
- `id` - Primary key
- `lead_id` - Foreign key to leads (cascading delete)
- `subject` - Email subject line
- `body` - Email body content
- `status` - Campaign status (pending, sent, failed, permanently_failed)
- `sent_at` - When email was sent
- `opened_at` - When email was opened
- `clicked_at` - When links were clicked
- `replied_at` - When prospect replied
- `bounce_reason` - Delivery failure reason
- `retry_count` - Number of retry attempts
- `next_retry_at` - When to retry next
- `max_retries` - Maximum retry attempts

**Indexes:**
- `idx_email_campaigns_status` - For status queries
- `idx_email_campaigns_lead_status` - Composite for duplicate prevention

---

### 4. buckets
Lead segmentation and configuration with rate limiting.

```sql
CREATE TABLE buckets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    categories TEXT,
    search_patterns TEXT,
    geographic_segments TEXT,
    intent_profile TEXT,
    conversion_probability REAL,
    monthly_target INTEGER,
    daily_email_count INTEGER DEFAULT 0,
    last_reset_date DATE DEFAULT CURRENT_DATE,
    daily_email_limit INTEGER DEFAULT 500
);
```

**Fields:**
- `id` - Primary key
- `name` - Bucket name (unique)
- `categories` - JSON array of target categories
- `search_patterns` - JSON array of search patterns
- `geographic_segments` - JSON array of geographic targets
- `intent_profile` - Intent characteristics
- `conversion_probability` - Expected conversion rate
- `monthly_target` - Monthly lead target
- `daily_email_count` - Emails sent today
- `last_reset_date` - Last counter reset date
- `daily_email_limit` - Daily email limit (default 500)

---

### 5. audit_issues
Normalized audit issues for better analysis.

```sql
CREATE TABLE audit_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id INTEGER NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT CHECK(severity IN ('critical', 'warning', 'info')),
    description TEXT,
    FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE CASCADE
);
```

**Fields:**
- `id` - Primary key
- `audit_id` - Foreign key to audits (cascading delete)
- `issue_type` - Standardized issue category
- `severity` - Issue severity (critical/warning/info)
- `description` - Human-readable description

**Indexes:**
- `idx_audit_issues_audit_id` - For audit lookups
- `idx_audit_issues_type` - For issue type queries

---

### 6. email_templates
Email templates with bucket foreign key relationship.

```sql
CREATE TABLE email_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket_id INTEGER,
    issue_type TEXT,
    template_id TEXT,
    subject_pattern TEXT,
    body_template TEXT,
    tone TEXT,
    word_count_range TEXT,
    conversion_focus TEXT,
    FOREIGN KEY(bucket_id) REFERENCES buckets(id) ON DELETE CASCADE,
    UNIQUE(bucket_id, issue_type)
);
```

**Fields:**
- `id` - Primary key
- `bucket_id` - Foreign key to buckets (cascading delete)
- `issue_type` - Target issue type
- `template_id` - Template identifier
- `subject_pattern` - Subject line pattern
- `body_template` - Email body template
- `tone` - Email tone (professional, casual, etc.)
- `word_count_range` - JSON array [min, max] words
- `conversion_focus` - Primary conversion goal

---

### 7. app_config
System configuration and settings.

```sql
CREATE TABLE app_config (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**Fields:**
- `key` - Configuration key (primary)
- `value` - Configuration value (JSON)

## Database Indexes

### Performance Indexes
```sql
-- Lead table indexes
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_bucket ON leads(bucket_id);
CREATE INDEX idx_leads_created_at ON leads(created_at);

-- Audit table indexes
CREATE INDEX idx_audits_qualified ON audits(qualified);
CREATE INDEX idx_audits_lead_id ON audits(lead_id);

-- Email campaign indexes
CREATE INDEX idx_email_campaigns_status ON email_campaigns(status);
CREATE INDEX idx_email_campaigns_lead_status ON email_campaigns(lead_id, status);

-- Audit issues indexes
CREATE INDEX idx_audit_issues_audit_id ON audit_issues(audit_id);
CREATE INDEX idx_audit_issues_type ON audit_issues(issue_type);
```

## Foreign Key Relationships

### Relationship Diagram
```
buckets (1) -----> (N) leads
leads (1) -----> (N) audits
leads (1) -----> (N) email_campaigns
audits (1) -----> (N) audit_issues
buckets (1) -----> (N) email_templates
```

### Cascade Rules
- `leads.bucket_id` → `buckets.id` (ON DELETE SET NULL)
- `audits.lead_id` → `leads.id` (ON DELETE CASCADE)
- `email_campaigns.lead_id` → `leads.id` (ON DELETE CASCADE)
- `audit_issues.audit_id` → `audits.id` (ON DELETE CASCADE)
- `email_templates.bucket_id` → `buckets.id` (ON DELETE CASCADE)

## Key Methods and Functions

### Lead Management
- `save_lead()` - Save lead with bucket foreign key resolution
- `get_pending_audits()` - Get leads needing audit
- `get_qualified_leads()` - Optimized qualified leads query

### Email Operations
- `save_email()` - Save email campaign
- `get_pending_emails()` - Get emails with rate limiting
- `mark_email_sent()` - Track delivery with retry logic
- `track_email_opened()` - Track email opens
- `track_email_clicked()` - Track link clicks
- `track_email_replied()` - Track replies
- `get_retry_emails()` - Get emails ready for retry

### Bucket Management
- `save_bucket()` - Save/update bucket configuration
- `get_all_buckets()` - Retrieve all buckets
- `get_bucket_id_by_name()` - Resolve bucket name to ID

### Audit Operations
- `save_audit()` - Save audit with normalized issues
- `get_issues_by_type()` - Query issues by type

### System Operations
- `get_stats()` - Enhanced statistics with engagement metrics
- `consolidate_database()` - Cleanup and optimization

## Data Types and Constraints

### String Fields
- `TEXT` - Variable length strings
- `UNIQUE` constraints on website and bucket names

### Numeric Fields
- `INTEGER` - Whole numbers (IDs, counts, scores)
- `REAL` - Decimal numbers (quality scores, probabilities)

### Date/Time Fields
- `TIMESTAMP` - Date and time with automatic defaults
- `DATE` - Date only for daily counters

### Constraints
- `NOT NULL` - Required fields
- `DEFAULT` - Automatic default values
- `CHECK` - Validated values (severity levels)
- `UNIQUE` - Prevent duplicates
- `FOREIGN KEY` - Referential integrity

## Performance Optimizations

### Query Improvements
1. **LEFT JOIN instead of NOT EXISTS** in `get_qualified_leads()`
2. **Composite indexes** for common query patterns
3. **Covering indexes** to reduce table lookups
4. **Proper foreign key indexes** for JOIN performance

### Memory Efficiency
1. **Context managers** for connection management
2. **Normalized data structures** to reduce JSON parsing
3. **Efficient data types** for storage optimization

## Migration Information

### Previous Schema Issues Fixed
- ✅ String-based bucket relationships → Proper foreign keys
- ✅ No cascading deletes → Full cascade support
- ✅ Missing indexes → Comprehensive indexing
- ✅ No email engagement → Full tracking support
- ✅ No retry logic → Exponential backoff system
- ✅ No rate limiting → Daily limits per bucket
- ✅ Manual connection management → Context managers
- ✅ JSON blob issues → Normalized audit_issues table

### Data Migration
- Automatic backup creation before migration
- Data transformation handled seamlessly
- Verification steps ensure integrity
- Backward compatibility maintained where possible

## Usage Examples

### Basic Operations
```python
# Save lead with bucket
lead_id = repo.save_lead({
    "business_name": "Example Corp",
    "website": "https://example.com",
    "bucket": "technology"  # Automatically resolved to bucket_id
})

# Track email engagement
repo.track_email_opened(campaign_id)
repo.track_email_clicked(campaign_id)

# Get engagement statistics
stats = repo.get_stats()
# Returns: total_leads, qualified_leads, emails_sent, 
#          emails_pending, emails_opened, emails_clicked, emails_replied
```

### Advanced Queries
```python
# Find leads with specific issues
mobile_issues = repo.get_issues_by_type("no_viewport")

# Get emails ready for retry
retry_emails = repo.get_retry_emails(limit=10)

# Get bucket performance
buckets = repo.get_all_buckets()
# Includes daily_email_count, conversion_probability, etc.
```

This database schema provides a robust foundation for lead management with enterprise-grade features including data integrity, performance optimization, and comprehensive tracking capabilities.
