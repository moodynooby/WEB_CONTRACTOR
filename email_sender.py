import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
import time
import random
import os
from dotenv import load_dotenv

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

        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as server:
            server.login(os.getenv('GMAIL_EMAIL'), os.getenv('GMAIL_PASSWORD'))
            server.sendmail(os.getenv('GMAIL_EMAIL'), to_email, message.as_string())

        print(f"✓ Sent to {to_email}")
        return True
    except Exception as e:
        print(f"✗ Failed {to_email}: {e}")
        return False

def send_batch(count=10):
    """Send emails with rate limiting (safe for Gmail)"""

    conn = sqlite3.connect('leads.db')
    cursor = conn.cursor()

    cursor.execute('''
    SELECT e.id, l.email, e.subject, e.body
    FROM email_campaigns e
    JOIN leads l ON e.lead_id = l.id
    WHERE e.status = "pending"
    LIMIT ?
    ''', (count,))

    emails = cursor.fetchall()
    sent = 0

    for email_id, to_email, subject, body in emails:
        if send_email(to_email, subject, body):
            cursor.execute('UPDATE email_campaigns SET status = "sent" WHERE id = ?', (email_id,))
            sent += 1

        # CRITICAL: Rate limiting for Gmail
        delay = random.uniform(45, 90)  # 45-90 sec between emails
        print(f"Waiting {delay:.0f}s...")
        time.sleep(delay)

    conn.commit()
    conn.close()
    print(f"\n✓ Sent {sent} emails")

if __name__ == '__main__':
    send_batch(count=10)
