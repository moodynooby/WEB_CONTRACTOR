# Web Contractor Pipeline

A comprehensive lead generation and outreach system for web service businesses, organized into modular stages with quality control and AI-powered messaging.

## 🏗️ Architecture Overview

The pipeline is organized into 5 main stages plus quality control:

```
Stage 0: Lead Discovery & Bucket Definition
    ↓
Stage A: Intelligent Scraper with Anti-Blocking
    ↓
Stage B: "Needs Update" Auditor Engine
    ↓
Stage C: AI-Powered Messaging
    ↓
Quality Control Agent (monitors all stages)
```

## 📁 File Structure

### Core Pipeline Files
- `pipeline_orchestrator.py` - Main coordinator for all stages
- `stage0_orchestrator.py` - Lead discovery and bucket management
- `stage_a_scraper.py` - Intelligent scraping with anti-blocking
- `stage_b_auditor.py` - Website technical auditing
- `stage_c_messaging.py` - AI-powered email generation
- `quality_control_agent.py` - Quality monitoring and validation

### Individual Scrapers
- `google_maps_scraper.py` - Google Maps business scraper
- `scraper.py` - Yellow Pages and directory scraper
- `linkedin_scraper.py` - LinkedIn company scraper
- `facebook_scraper.py` - Facebook business scraper

### Supporting Files
- `lead_buckets.py` - Lead bucket definitions and targeting
- `db.py` - Database operations and initialization
- `email_generator.py` - Email generation utilities
- `email_sender.py` - Email sending via Gmail SMTP
- `rate_limiter.py` - Rate limiting for scraping
- `main.py` - Flask web interface and API

### Configuration
- `pyproject.toml` - Python dependencies
- `.python-version` - Python version specification
- `templates/index.html` - Web interface

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Ollama (for AI email generation)
- Gmail account (for email sending)
- ChromeDriver (for LinkedIn scraping)

### Installation

```bash
# Install dependencies with uv
uv sync

# Start Ollama for AI email generation
ollama serve
ollama pull llama3.2

# Set up environment variables
cp .env.example .env
# Edit .env with your settings
```

### Environment Variables
```env
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
GMAIL_EMAIL=your@gmail.com
GMAIL_PASSWORD=your_app_password
```

### Running the Pipeline

```python
# Run the complete pipeline
from pipeline_orchestrator import PipelineOrchestrator

pipeline = PipelineOrchestrator()
results = pipeline.run_full_pipeline(manual_mode=True)
```

### Web Interface

```bash
# Start the web interface
python main.py
# Visit http://localhost:5000
```

## 📋 Stages Detailed

### Stage 0: Lead Discovery & Bucket Definition
**Purpose**: Define target segments and coordinate initial lead discovery

**Features**:
- Geographic and industry-based lead buckets
- Conversion probability scoring
- Monthly target tracking
- Multi-source scraping coordination

**Key Files**: `stage0_orchestrator.py`, `lead_buckets.py`

### Stage A: Intelligent Scraper with Anti-Blocking
**Purpose**: Scrape leads from multiple sources with advanced protection

**Features**:
- User agent rotation
- Proxy rotation (free proxy integration)
- Domain-specific rate limiting
- Blocked domain detection
- Intelligent delay systems

**Sources**:
- Google Maps
- Yellow Pages (yellow.co.in)
- LinkedIn
- Facebook

**Key File**: `stage_a_scraper.py`

### Stage B: "Needs Update" Auditor Engine
**Purpose**: Analyze websites for technical issues and qualification

**Features**:
- SSL certificate checking
- Mobile responsiveness testing
- Performance analysis
- SEO audit
- Contact information validation
- Quality scoring (0.0-1.0)
- Qualification logic

**Issues Detected**:
- Missing SSL certificates
- Slow loading times
- Mobile unfriendliness
- Missing meta descriptions
- Outdated technology
- Broken links
- No contact information
- Poor navigation
- Missing social proof
- Accessibility issues

**Key File**: `stage_b_auditor.py`

### Stage C: AI-Powered Messaging
**Purpose**: Generate personalized outreach emails using local AI

**Features**:
- Local Ollama LLM integration
- Bucket-specific email templates
- Personalization scoring
- Tone detection (professional, friendly, urgent, casual)
- Word count optimization (110-130 words)
- Call-to-action extraction

**Email Templates by Bucket**:
- Interior Designers & Architects
- Local Service Providers
- Small B2B Agencies
- Niche Professional Services

**Key File**: `stage_c_messaging.py`

### Quality Control Agent
**Purpose**: Monitor pipeline health and data quality

**Features**:
- Data validation across all stages
- Pipeline performance monitoring
- Automated alert system
- Auto-fix capabilities
- Quality metrics dashboard

**Alert Levels**: Info, Warning, Error, Critical

**Key File**: `quality_control_agent.py`

## 🗄️ Database Schema

### Core Tables
- **leads** - Business information with quality scores
- **lead_buckets** - Bucket definitions and targets
- **audits** - Website audit results and issues
- **email_campaigns** - Generated emails and status
- **scraping_logs** - Scraping session logs
- **analytics** - Performance metrics

### Key Relationships
```
leads (1) → (many) audits
leads (1) → (many) email_campaigns
lead_buckets (1) → (many) leads
```

## 📊 API Endpoints

### Pipeline Management
- `GET /api/pipeline/status` - Complete pipeline status
- `GET /api/pipeline/recommendations` - Optimization suggestions
- `GET /api/stages` - Available stages and status
- `POST /api/process/start` - Start pipeline stage
- `POST /api/process/stop` - Stop running process

### Data Access
- `GET /api/stats` - Pipeline statistics
- `GET /api/leads` - Lead data with pagination
- `GET /api/buckets` - Lead bucket configurations
- `GET /api/analytics` - Detailed analytics

### Quality Control
- `POST /api/quality/check` - Run quality check

## 🔧 Configuration

### Lead Buckets
Configure target segments in `lead_buckets.py`:

```python
LeadBucket(
    name="Interior Designers & Architects",
    categories=["Interior Designer", "Architect"],
    conversion_probability=0.75,
    monthly_target=500
)
```

### Scraping Sources
Enable/disable sources in `stage_a_scraper.py`:

```python
scraping_schedule = {
    'google_maps': {'enabled': True, 'priority': 1},
    'yellow_pages': {'enabled': True, 'priority': 2},
    'linkedin': {'enabled': True, 'priority': 3},
    'facebook': {'enabled': True, 'priority': 4}
}
```

### Email Templates
Customize templates in `stage_c_messaging.py` for different buckets and issue types.

## 📈 Performance Metrics

### Key KPIs
- Lead generation rate (leads/hour)
- Audit coverage (%)
- Qualification rate (%)
- Email generation rate (emails/hour)
- Personalization score (0.0-1.0)
- Quality issues count

### Monitoring
- Real-time pipeline status
- Stage-specific performance
- Error tracking and alerts
- Database health checks

## 🛠️ Development

### Adding New Stages
1. Create new stage file following existing pattern
2. Add to `pipeline_orchestrator.py`
3. Update `main.py` process management
4. Add quality control checks

### Adding New Scrapers
1. Create scraper class with `scrape_by_buckets()` method
2. Add to `stage_a_scraper.py`
3. Configure rate limiting and anti-blocking

### Custom Email Templates
1. Add templates to `stage_c_messaging.py`
2. Define bucket-specific patterns
3. Test with Ollama integration

## 🔒 Security Considerations

### Scraping Ethics
- Respect robots.txt files
- Implement proper rate limiting
- Use user agent rotation
- Monitor for blocking

### Data Privacy
- No personal data storage beyond business info
- GDPR compliance considerations
- Secure email sending practices

## 🚨 Troubleshooting

### Common Issues
1. **Ollama Connection**: Ensure Ollama is running and model is pulled
2. **Database Errors**: Check file permissions and SQLite integrity
3. **Scraping Blocks**: Check rate limits and proxy configuration
4. **Email Sending**: Verify Gmail app password and SMTP settings

### Debug Mode
Enable debug logging in individual stage files:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📝 License

This project is for educational and demonstration purposes. Users are responsible for complying with terms of service of scraped websites and applicable laws.

## 🤝 Contributing

1. Follow existing code patterns
2. Add proper error handling
3. Include quality control checks
4. Update documentation

## 📞 Support

For issues and questions:
1. Check quality control alerts
2. Review pipeline recommendations
3. Check individual stage logs
4. Verify configuration settings
