import time
import random
from flask import current_app
from flask_mail import Message
from loguru import logger

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
                <div style="margin-bottom: 20px;">
                    {body.replace(chr(10), '<br>')}
                </div>
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                    <p style="color: #666; font-size: 0.9em;">Best regards,<br><strong>Manas</strong><br>
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
