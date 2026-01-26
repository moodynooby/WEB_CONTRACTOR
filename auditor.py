import requests
from bs4 import BeautifulSoup
import sqlite3
import json
import re
from datetime import datetime
import time

def audit_website(url):
    """Comprehensive free audit (no APIs used)"""

    audit = {
        'url': url,
        'issues': [],
        'score': 100,
        'qualified': False
    }

    try:
        print(f"Auditing: {url}...", end=' ')
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')

        # CHECK 1: Mobile
        if not soup.find('meta', {'name': 'viewport'}):
            audit['issues'].append({
                'type': 'mobile',
                'issue': 'Not mobile-friendly (missing viewport)',
                'impact': 'Looks broken on phones (70% of users)'
            })
            audit['score'] -= 15

        # CHECK 2: HTTPS
        if url.startswith('http://'):
            audit['issues'].append({
                'type': 'security',
                'issue': 'Using HTTP not HTTPS',
                'impact': 'Not secure; customers avoid'
            })
            audit['score'] -= 20

        # CHECK 3: Outdated copyright
        footer_text = soup.get_text()
        years = re.findall(r'20\d{2}', footer_text)
        if years:
            footer_year = int(max(years))
            if datetime.now().year - footer_year > 2:
                audit['issues'].append({
                    'type': 'staleness',
                    'issue': f'Copyright from {footer_year} (outdated)',
                    'impact': 'Site looks abandoned'
                })
                audit['score'] -= 12

        # CHECK 4: Contact info
        text = soup.get_text().lower()
        has_email = bool(re.search(r'\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b', text))
        has_phone = bool(re.search(r'\+?\d{10,}', text))

        if not (has_email or has_phone):
            audit['issues'].append({
                'type': 'contact',
                'issue': 'No contact information',
                'impact': 'Customers cannot reach you'
            })
            audit['score'] -= 18

        # PRIORITY
        audit['priority'] = 'critical' if audit['score'] < 40 else 'high' if audit['score'] < 60 else 'medium'
        audit['qualified'] = len(audit['issues']) >= 2 and audit['score'] < 70

        print(f"Score: {audit['score']}/100")

    except Exception as e:
        audit['qualified'] = False
        print(f"ERROR: {e}")

    return audit

def audit_all_leads():
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    cursor.execute('SELECT id, website FROM leads WHERE status = "pending_audit" LIMIT 100')
    leads = cursor.fetchall()

    qualified = 0

    for lead_id, website in leads:
        if not website:
            continue

        audit = audit_website(website)

        cursor.execute('''
        INSERT INTO audits (lead_id, url, score, priority, issues_json, qualified)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (lead_id, website, audit['score'], audit['priority'],
              json.dumps(audit['issues']), int(audit['qualified'])))

        if audit['qualified']:
            qualified += 1
            cursor.execute('UPDATE leads SET status = "qualified" WHERE id = ?', (lead_id,))

        time.sleep(1)

    conn.commit()
    conn.close()
    print(f"\n✓ Audited: {qualified} qualified leads found")

if __name__ == '__main__':
    audit_all_leads()
