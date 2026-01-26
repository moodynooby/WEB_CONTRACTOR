import requests
import sqlite3
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')

def generate_email(company, issues_list):
    """Generate using LOCAL Ollama (100% FREE - no API calls)"""

    issues_text = '\n'.join([f"- {issue['issue']}" for issue in issues_list[:3]])

    prompt = f"""Write a short cold email (110-130 words exactly) to {company}.

ISSUES ON THEIR SITE:
{issues_text}

RULES:
- Mention specific issue
- Explain business impact
- Helpful tone (not salesy)
- End with: https://man27.netlify.app/services
- NO generic greetings

EMAIL:"""

    try:
        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': 'mistral',
                'prompt': prompt,
                'stream': False,
                'temperature': 0.7,
            },
            timeout=60
        )

        email_body = response.json()['response'].strip()
        print(f"✓ Generated for {company}")
        return email_body

    except Exception as e:
        print(f"✗ Error: {e}")
        return None

def generate_all_emails():
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT l.id, l.business_name, a.issues_json
    FROM leads l
    JOIN audits a ON l.id = a.lead_id
    WHERE a.qualified = 1 AND NOT EXISTS (
        SELECT 1 FROM email_campaigns WHERE lead_id = l.id
    )
    LIMIT 20
    ''')

    leads = cursor.fetchall()

    for lead_id, company, issues_json in leads:
        issues = json.loads(issues_json)
        body = generate_email(company, issues)

        if body:
            subject = f"Quick fix for {company}: Website issue"
            cursor.execute('''
            INSERT INTO email_campaigns (lead_id, subject, body, status)
            VALUES (?, ?, ?, ?)
            ''', (lead_id, subject, body, 'pending'))

        time.sleep(2)

    conn.commit()
    conn.close()
    print("\n✓ Email generation complete")

if __name__ == '__main__':
    generate_all_emails()
