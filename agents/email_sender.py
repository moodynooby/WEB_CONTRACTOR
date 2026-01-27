import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import time
import random
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

def send_email(to_email, subject, body):
    """Send via Gmail free tier"""

    try:
        message = MIMEMultipart('alternative')
        message['Subject'] = subject
        message['From'] = os.getenv('GMAIL_EMAIL')
        message['To'] = to_email

        html = f"""
        <html><body style="font-family: Arial; line-height: 1.6;">
            <p>Hi,</p>
            <p>{body}</p>
            <p>Best regards,<br>Your Name<br>
            <a href="https://man27.netlify.app">Web Services</a></p>
        </body></html>
        """

        part = MIMEText(html, 'html')
        message.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.getenv('GMAIL_EMAIL'), os.getenv('GMAIL_PASSWORD'))
        server.send_message(message)
        server.quit()

        return True
    except Exception as e:
        print(f"Email send error: {e}")
        return False

def send_pending_emails():
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
            
            success = send_email(to_email, subject, body)
            
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
