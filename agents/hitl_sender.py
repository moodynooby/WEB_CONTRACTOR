"""
Stage D: Human-In-Loop Email Sender
Provides a CLI interface for reviewing, editing, and sending outreach emails.
"""

import sqlite3
import json
import os
import sys
import tempfile
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional

# Import sending logic from existing agent
from email_sender import send_email

class HITLSender:
    def __init__(self, db_path: str = 'leads.db'):
        self.db_path = db_path
        self.min_score = 0.7  # Score threshold for "good" leads

    def fetch_reviewable_emails(self) -> List[Dict]:
        """Fetch pending emails for high-quality leads"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = '''
        SELECT 
            ec.id as campaign_id,
            l.id as lead_id,
            l.business_name,
            l.website,
            l.email as lead_email,
            a.overall_score,
            a.llm_analysis,
            ec.subject,
            ec.body
        FROM email_campaigns ec
        JOIN leads l ON ec.lead_id = l.id
        JOIN audits a ON l.id = a.lead_id
        WHERE ec.status = 'pending'
        AND a.overall_score >= ?
        AND a.qualified = 1
        ORDER BY a.overall_score DESC
        '''
        
        cursor.execute(query, (self.min_score,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_status(self, campaign_id: int, status: str, body: Optional[str] = None):
        """Update campaign status and optionally the body"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if body:
            cursor.execute('''
                UPDATE email_campaigns 
                SET status = ?, body = ?, sent_at = ? 
                WHERE id = ?
            ''', (status, body, datetime.now().isoformat() if status == 'sent' else None, campaign_id))
        else:
            cursor.execute('''
                UPDATE email_campaigns 
                SET status = ?, sent_at = ? 
                WHERE id = ?
            ''', (status, datetime.now().isoformat() if status == 'sent' else None, campaign_id))
            
        conn.commit()
        conn.close()

    def edit_body(self, initial_body: str) -> str:
        """Open temporary file in editor for manual editing"""
        editor = os.environ.get('EDITOR', 'nano')
        with tempfile.NamedTemporaryFile(suffix=".txt", mode='w+', delete=False) as tf:
            tf.write(initial_body)
            temp_path = tf.name

        subprocess.call([editor, temp_path])

        with open(temp_path, 'r') as f:
            edited_body = f.read()

        os.unlink(temp_path)
        return edited_body.strip()

    def run_review_loop(self):
        """Main interface loop"""
        print("\n" + "="*60)
        print("   HUMAN-IN-THE-LOOP EMAIL SENDER")
        print("="*60)
        
        emails = self.fetch_reviewable_emails()
        if not emails:
            print("No high-quality pending emails found for review.")
            return

        print(f"Found {len(emails)} emails ready for review (Score >= {self.min_score})\n")

        for i, mail in enumerate(emails):
            print(f"[{i+1}/{len(emails)}] BUSINESS: {mail['business_name']}")
            print(f"WEBSITE: {mail['website']} | SCORE: {mail['overall_score']:.2f}")
            
            # Show LLM Analysis if available
            if mail['llm_analysis']:
                try:
                    analysis = json.loads(mail['llm_analysis'])
                    print(f"CRITIQUE: {analysis.get('critique', 'N/A')}")
                    print(f"IMPACT: {analysis.get('business_impact', 'N/A')}")
                except:
                    pass
            
            print("-" * 30)
            print(f"SUBJECT: {mail['subject']}")
            print(f"BODY:\n{mail['body']}")
            print("-" * 30)
            
            while True:
                choice = input("\nAction: [S]end, [E]dit & Send, [I]gnore, [P]ass, [Q]uit: ").lower()
                
                if choice == 's':
                    to_addr = mail['lead_email'] or f"contact@{mail['business_name'].lower().replace(' ', '')}.com"
                    print(f"Sending to {to_addr}...")
                    if send_email(to_addr, mail['subject'], mail['body']):
                        self.update_status(mail['campaign_id'], 'sent')
                        print("✅ Sent.")
                    else:
                        print("❌ Failed to send.")
                    break
                
                elif choice == 'e':
                    new_body = self.edit_body(mail['body'])
                    print(f"\nREVISED BODY:\n{new_body}")
                    confirm = input("Send this revised version? (y/n): ").lower()
                    if confirm == 'y':
                        to_addr = mail['lead_email'] or f"contact@{mail['business_name'].lower().replace(' ', '')}.com"
                        if send_email(to_addr, mail['subject'], new_body):
                            self.update_status(mail['campaign_id'], 'sent', new_body)
                            print("✅ Sent.")
                        else:
                            print("❌ Failed.")
                    break
                
                elif choice == 'i':
                    self.update_status(mail['campaign_id'], 'ignored')
                    print("Marked as IGNORED.")
                    break
                
                elif choice == 'p':
                    print("Skipped for later.")
                    break
                
                elif choice == 'q':
                    print("Exiting review.")
                    return
                
                else:
                    print("Invalid choice.")

if __name__ == "__main__":
    sender = HITLSender()
    sender.run_review_loop()
