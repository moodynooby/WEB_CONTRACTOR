import sqlite3
import json
import time
import random
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Optional
from flask import current_app
from flask_mail import Message

load_dotenv()

def send_email(to_email, subject, body, mail_instance=None):
    """Send via Flask-Mail"""
    try:
        # Create message
        html_body = f"""
        <html><body style="font-family: Arial; line-height: 1.6;">
            <p>Hi,</p>
            <p>{body}</p>
            <p>Best regards,<br>Manas<br>
            <a href="https://man27.netlify.app/services">Web Services</a></p>
        </body></html>
        """
        
        if mail_instance:
            # Use provided mail instance (from Flask app)
            msg = Message(
                subject=subject,
                recipients=[to_email],
                html=html_body
            )
            mail_instance.send(msg)
        else:
            # Fallback to direct Flask app context
            with current_app.app_context():
                msg = Message(
                    subject=subject,
                    recipients=[to_email],
                    html=html_body
                )
                current_app.extensions['mail'].send(msg)
        
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False

def fetch_reviewable_emails(min_score: float = 0.7) -> List[Dict]:
    """Fetch pending emails for high-quality leads"""
    conn = sqlite3.connect('leads.db')
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
        ec.body,
        l.bucket
    FROM email_campaigns ec
    JOIN leads l ON ec.lead_id = l.id
    JOIN audits a ON l.id = a.lead_id
    WHERE ec.status = 'pending'
    AND a.overall_score >= ?
    AND a.qualified = 1
    ORDER BY a.overall_score DESC
    '''
    
    cursor.execute(query, (min_score,))
    rows = cursor.fetchall()
    conn.close()
    
    emails = [dict(row) for row in rows]
    # Parse JSON in llm_analysis if present
    for email in emails:
        if email['llm_analysis']:
            try:
                email['llm_analysis'] = json.loads(email['llm_analysis'])
            except:
                pass
    
    return emails

def update_campaign_status(campaign_id: int, status: str, body: Optional[str] = None):
    """Update campaign status and optionally the body"""
    conn = sqlite3.connect('leads.db')
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

def send_pending_emails(mail_instance=None):
    """Send all pending emails"""
    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()
    
    # Get pending emails
    cursor.execute('''
    SELECT ec.id, ec.lead_id, ec.subject, ec.body, l.business_name
    FROM email_campaigns ec
    JOIN leads l ON ec.lead_id = l.id
    WHERE ec.status = 'pending'
    ORDER BY ec.campaign_date ASC
    LIMIT 50
    ''')
    
    pending_emails = cursor.fetchall()
    sent_count = 0
    
    for email_id, lead_id, subject, body, business_name in pending_emails:
        try:
            # For demo purposes, we'll use a placeholder email
            # In production, you'd get the actual email from the leads table
            to_email = f"contact@{business_name.lower().replace(' ', '')}.com"
            
            success = send_email(to_email, subject, body, mail_instance)
            
            if success:
                # Update status to sent
                cursor.execute('''
                UPDATE email_campaigns 
                SET status = 'sent', sent_at = ?
                WHERE id = ?
                ''', (datetime.now().isoformat(), email_id))
                
                sent_count += 1
                print(f"Sent email to {business_name}")
            else:
                # Mark as failed
                cursor.execute('''
                UPDATE email_campaigns 
                SET status = 'failed'
                WHERE id = ?
                ''', (email_id,))
            
            # Add delay between emails to avoid spam filters
            time.sleep(random.uniform(30, 60))
            
        except Exception as e:
            print(f"Error sending email to {business_name}: {e}")
            # Mark as failed
            cursor.execute('''
            UPDATE email_campaigns 
            SET status = 'failed'
            WHERE id = ?
            ''', (email_id,))
    
    conn.commit()
    conn.close()
    print(f"Sent {sent_count} emails successfully")
    return sent_count

if __name__ == '__main__':
    send_pending_emails()
