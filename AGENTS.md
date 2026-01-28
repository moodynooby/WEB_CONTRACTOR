he system targets businesses with web presence gaps (particularly Interior Designers, Web Agencies, Local Services) and converts them through value-first messaging.

Layer,Tool,Purpose,Cost
Scraping,Selenium + BeautifulSoup,Extracting data from websites,$0
Anti-Blocking,Tor / ProxyScrape (Free),Rotating IPs to avoid bans,$0
Database,SQLite,Storing lead data locally,$0
Auditing,Python + Lighthouse API,Technical website analysis,$0
AI Email,Ollama (Local),Generating personalized copy,$0
Email Sending,Gmail SMTP (Personal),Sending via free @gmail account,$0
Analytics,Google Sheets API,Logging and tracking results,$0
Scheduling,APScheduler,Automating the timing of tasks,$0
Infrastructure


Local Machine / EC2
├─ Scraper script (runs daily 2am IST)
├─ Audit script (runs after scrape)
├─ Email generation (runs before campaign)
├─ Outreach orchestrator (runs every morning)
├─ Sqlite (lead database)
├─ Ollama (email generation)
└─ Analytics logger (logs every interaction)

Cloud Components

├─ Gmail SMTP / Instantly.ai (email sending)
└─ Google Sheets (campaign tracking)


Stage 0: Planning & Analytics (What do we need to scrape today?)
Stage A: Execution (Go scrape it!)
Stage B: "Needs Update" Auditor Engine
Stage C: AI-Powered Messaging
Quality Control Agent

STACK -
UV ISNTEAD OF PIP
INTERAGRATE AL THE STAGE PYTHON FILES BACK TO A FLASK FRONTEND FORM CONTROL AND ANALYSTICS