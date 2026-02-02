import json
import time
import random
import os
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List, Optional
from flask import current_app
from flask_mail import Message
from loguru import logger

load_dotenv()

def send_email(to_email, subject, body, mail_instance=None):
    """Send via Flask-Mail with enhanced logging and error handling"""
    if not to_email or '@' not in to_email:
        logger.error(f"Cannot send email: invalid or missing recipient: {to_email}")
        return False
        
    logger.info(f"Attempting to send email to {to_email} with subject: {subject}")
    try:
        # Create message
        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                <p>Hi,</p>
                <p>{body.replace(chr(10), '<br>')}</p>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                    <p>Best regards,<br><strong>Manas</strong><br>
                    <a href="https://man27.netlify.app/services" style="color: #381E72; text-decoration: none;">Web Services & Automation</a></p>
                </div>
            </div>
        </body></html>
        """
        
        msg = Message(
            subject=subject,
            recipients=[to_email],
            html=html_body
        )

        if mail_instance:
            mail_instance.send(msg)
        else:
            with current_app.app_context():
                current_app.extensions['mail'].send(msg)
        
        logger.success(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def fetch_reviewable_emails(min_score: float = 0.7) -> List[Dict]:
    """Fetch pending emails for high-quality leads"""
    from core.db import LeadRepository
    repo = LeadRepository()
    
    emails = repo.get_reviewable_emails(min_score)
    
    # Parse JSON in llm_analysis if present
    for email in emails:
        if email.get('llm_analysis'):
            try:
                if isinstance(email['llm_analysis'], str):
                    email['llm_analysis'] = json.loads(email['llm_analysis'])
            except:
                pass
    
    return emails

def update_campaign_status(campaign_id: int, status: str, body: Optional[str] = None, error_message: Optional[str] = None):
    """Update campaign status with enhanced metadata"""
    from core.db import LeadRepository
    repo = LeadRepository()
    
    repo.update_campaign_status(campaign_id, status, body, error_message)
    logger.info(f"Updated campaign {campaign_id} status to {status}")

def send_pending_emails(mail_instance=None):
    """Send all pending emails"""
    from core.db import LeadRepository
    repo = LeadRepository()
    
    pending_emails = repo.get_pending_emails_to_send(limit=50)
    
    sent_count = 0
    fail_count = 0
    
    for email in pending_emails:
        email_id = email['id']
        lead_id = email['lead_id']
        subject = email['subject']
        body = email['body']
        business_name = email['business_name']
        
        try:
            # Fetch actual email from leads table
            to_email = repo.get_lead_email(lead_id)
            
            if not to_email:
                logger.error(f"Skipping {business_name} - No email found (guessing disabled for HITL enforcement)")
                update_campaign_status(email_id, 'failed', error_message="Verified email address not found; guessing is disabled.")
                continue
            
            success = send_email(to_email, subject, body, mail_instance)
            
            if success:
                update_campaign_status(email_id, 'sent', body)
                sent_count += 1
            else:
                update_campaign_status(email_id, 'failed', error_message="SMTP send failure")
                fail_count += 1
            
            # Add delay between emails to avoid spam filters
            time.sleep(random.uniform(30, 60))
            
        except Exception as e:
            logger.error(f"Error processing pending email {email_id}: {e}")
            update_campaign_status(email_id, 'failed', error_message=str(e))
            fail_count += 1
    
    print(f"Sent {sent_count} emails successfully")
    return sent_count

if __name__ == '__main__':
    send_pending_emails()
