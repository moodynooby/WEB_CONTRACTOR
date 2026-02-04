import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

import requests
from flask import current_app
from flask_mail import Mail, Message


@dataclass
class EmailTemplate:
    """Email template structure"""

    template_id: str
    bucket_name: str
    issue_type: str
    subject_pattern: str
    body_template: str
    tone: str  # 'professional', 'friendly', 'urgent', 'casual'
    word_count_range: tuple
    conversion_focus: str


@dataclass
class GeneratedEmail:
    """Generated email with metadata"""

    lead_id: int
    business_name: str
    subject: str
    body: str
    tone: str
    word_count: int
    personalization_score: float
    urgency_level: str
    call_to_action: str
    generation_timestamp: datetime


class OllamaEmailGenerator:
    """Local AI email generation using Ollama"""

    def __init__(self):
        self.ollama_url = "http://localhost:11434"
        self.model_name = "qwen3:8b"

        # Email templates by bucket and issue type
        self.templates = self._load_templates()

    def _load_templates(self) -> Dict[str, Dict[str, EmailTemplate]]:
        """Load email templates from JSON config"""
        config_path = os.path.join(os.getcwd(), "config", "email_templates.json")
        try:
            with open(config_path, "r") as f:
                data = json.load(f)

            templates = {}
            for bucket, bucket_templates in data.get("templates", {}).items():
                templates[bucket] = {}
                for issue, tpl_data in bucket_templates.items():
                    templates[bucket][issue] = EmailTemplate(
                        template_id=tpl_data["template_id"],
                        bucket_name=tpl_data["bucket_name"],
                        issue_type=tpl_data["issue_type"],
                        subject_pattern=tpl_data["subject_pattern"],
                        body_template=tpl_data["body_template"],
                        tone=tpl_data["tone"],
                        word_count_range=tuple(tpl_data["word_count_range"]),
                        conversion_focus=tpl_data["conversion_focus"],
                    )
            return templates
        except FileNotFoundError:
            print(
                f"Email template config not found at {config_path}. Using empty defaults."
            )
            return {}
        except Exception as e:
            print(f"Error loading email templates: {e}")
            return {}

    def generate_email_with_ollama(
        self,
        business_name: str,
        issues: List[Dict],
        bucket_name: str,
        llm_analysis: Optional[Dict] = None,
    ) -> Dict[str, str]:
        """Generate personalized email and subject line using Ollama LLM"""

        # Select an example template for style
        example_template = self._select_best_template(issues, bucket_name)

        # Create prompt for Ollama
        prompt = self._create_prompt(
            business_name, issues, example_template, llm_analysis
        )

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a professional outreach specialist. You output ONLY valid JSON. No conversational filler, no 'Sure', no 'Here is the email'.",
                    "options": {"temperature": 0.8, "top_p": 0.9, "max_tokens": 500},
                },
                timeout=300,
            )

            if response.status_code == 200:
                raw_response = response.json().get("response", "{}")

                # Robust JSON extraction
                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    start = raw_response.find("{")
                    end = raw_response.rfind("}") + 1
                    if start != -1 and end != 0:
                        try:
                            data = json.loads(raw_response[start:end])
                        except:
                            print(
                                f"❌ Failed to parse JSON from Ollama for {business_name}"
                            )
                            return {
                                "subject": f"Question about {business_name}",
                                "body": self._fallback_email(
                                    business_name, issues, example_template
                                ),
                            }
                    else:
                        print(
                            f"❌ No JSON found in Ollama response for {business_name}"
                        )
                        return {
                            "subject": f"Question about {business_name}",
                            "body": self._fallback_email(
                                business_name, issues, example_template
                            ),
                        }

                subject = data.get(
                    "subject", f"Quick question about {business_name}'s website"
                )
                body = data.get("body", "").strip()

                if not body:
                    print(
                        f"⚠️  Ollama returned empty body for {business_name}, using fallback."
                    )
                    return {
                        "subject": f"Question about {business_name}",
                        "body": self._fallback_email(
                            business_name, issues, example_template
                        ),
                    }

                # Post-process and validate
                processed_body = self._post_process_email(
                    body, business_name, example_template
                )
                return {"subject": subject, "body": processed_body}
            else:
                print(
                    f"❌ Ollama API error ({response.status_code}) for {business_name}"
                )
                return {
                    "subject": f"Question about {business_name}",
                    "body": self._fallback_email(
                        business_name, issues, example_template
                    ),
                }

        except Exception as e:
            logger.exception(f"❌ Ollama Exception during email generation: {e}")
            return {
                "subject": f"Question about {business_name}",
                "body": self._fallback_email(business_name, issues, example_template),
            }

    def _select_best_template(
        self, issues: List[Dict], bucket_name: str
    ) -> EmailTemplate:
        """Select the best template based on issues and bucket"""
        if bucket_name not in self.templates:
            # Use generic template if available, else first one
            if self.templates:
                return (
                    list(self.templates.values())[0]
                    if isinstance(list(self.templates.values())[0], EmailTemplate)
                    else list(list(self.templates.values())[0].values())[0]
                )
            return EmailTemplate(
                "default",
                "General",
                "various",
                "Query",
                "Hello",
                "professional",
                (50, 200),
                "general",
            )

        bucket_templates = self.templates[bucket_name]

        for issue in issues:
            issue_type = issue.get("issue_type", "")
            if issue_type in bucket_templates:
                return bucket_templates[issue_type]

        # Fallback to first available template in bucket
        return list(bucket_templates.values())[0]

    def _create_prompt(
        self,
        business_name: str,
        issues: List[Dict],
        template: EmailTemplate,
        llm_analysis: Optional[Dict] = None,
    ) -> str:
        """Create a highly dynamic prompt for Ollama"""
        issues_text = "\n".join(
            [
                f"- {issue['description']} (Severity: {issue.get('severity', 'medium')})"
                for issue in issues[:4]
            ]
        )

        llm_context = ""
        if llm_analysis:
            critique = llm_analysis.get("critique", "")
            impact = llm_analysis.get("business_impact", "")
            hooks = ", ".join(llm_analysis.get("hooks", []))
            llm_context = f"""
AUDITOR OBSERVATIONS: {critique}
BUSINESS IMPACT IDENTIFIED: {impact}
POTENTIAL HOOKS TO USE: {hooks}
"""

        prompt = f"""Write a personalized cold email for {business_name} and return ONLY a JSON object. No preamble, no explanation.

CONTEXT:
Business Type: {template.bucket_name}
Found Issues:
{issues_text}
{llm_context}

STYLE (Reference only):
Tone: {template.tone}
Focus: {template.conversion_focus}
Ref Example: "{template.body_template}"

TASK:
1. "subject": Catchy subject line (< 50 chars).
2. "body": Personalized email body (100-140 words). 
   - Acknowledge their specific site content.
   - Mention the 'BUSINESS IMPACT'.
   - Offer a solution.
   - End with a low-friction CTA.

OUTPUT FORMAT:
{{
  "subject": "...",
  "body": "..."
}}"""
        return prompt

    def _post_process_email(
        self, generated_text: str, business_name: str, template: EmailTemplate
    ) -> str:
        """Post-process generated email"""
        email = generated_text.strip()

        placeholders = [
            "[Business Name]",
            "{business_name}",
            "[Company Name]",
            "{company_name}",
        ]
        for placeholder in placeholders:
            if placeholder in email:
                email = email.replace(placeholder, business_name)

        if "Hi there," in email or "Hello there," in email:
            email = email.replace("Hi there,", f"Hi {business_name},").replace(
                "Hello there,", f"Hi {business_name},"
            )

        # Check word count
        word_count = len(email.split())
        if (
            word_count < template.word_count_range[0]
            or word_count > template.word_count_range[1]
        ):
            if word_count < template.word_count_range[0]:
                email += "\n\nThis small improvement could make a big difference for your business."
            else:
                sentences = email.split(". ")
                if len(sentences) > 4:
                    email = ". ".join(sentences[:4]) + "."

        return email

    def _fallback_email(
        self, business_name: str, issues: List[Dict], template: EmailTemplate
    ) -> str:
        """Fallback email generation without Ollama"""
        issues_text = ", ".join(
            [issue["issue_type"].replace("_", " ").title() for issue in issues[:2]]
        )

        fallback = f"""Hi {business_name},

I noticed a few technical issues on your website: {issues_text}. These might be affecting your business performance and customer trust.

I specialize in fixing these issues quickly and affordably. A simple update could help you attract more customers and appear more professional.

Would you be interested in a quick consultation about improving your website?

Best regards,
Manas Doshi
Future Forwards"""

        return fallback


class StageCEmailGenerator:
    """Stage C: AI-Powered Messaging & HITL Orchestration"""

    def __init__(self, mail_instance: Optional[Mail] = None):
        self.ollama_generator = OllamaEmailGenerator()
        self.mail = mail_instance
        from core.db import LeadRepository

        self.repo = LeadRepository()

    def set_mail_instance(self, mail_instance: Mail):
        """Update mail instance (useful for late binding in Flask)"""
        self.mail = mail_instance

    # --- Email Generation ---

    def generate_emails_for_qualified_leads(self, batch_size: int = 20) -> Dict:
        """Generate email campaigns for qualified leads (Status: pending)"""
        print("=== STAGE C: AI EMAIL GENERATOR ===")

        candidates = self.repo.get_qualified_leads_for_email(batch_size)

        if not candidates:
            print("No qualified leads found for email generation")
            return {"generated_count": 0, "emails": []}

        print(f"Found {len(candidates)} candidates for email generation")

        generated_emails = []

        for i, lead in enumerate(candidates):
            business_name = lead.get("business_name")
            print(f"[{i + 1}/{len(candidates)}] Generating email for: {business_name}")

            try:
                issues = json.loads(lead.get("issues_json", "[]"))
                llm_analysis = json.loads(lead.get("llm_analysis", "{}"))
                bucket_name = lead.get("bucket", "default")

                email_content = self.ollama_generator.generate_email_with_ollama(
                    business_name, issues, bucket_name, llm_analysis
                )

                email = GeneratedEmail(
                    lead_id=lead["id"],
                    business_name=business_name,
                    subject=email_content.get("subject", "Partnership Opportunity"),
                    body=email_content.get("body", ""),
                    tone="professional",  # Default
                    word_count=len(email_content.get("body", "").split()),
                    personalization_score=0.8,
                    urgency_level="low",
                    call_to_action="Reply for more info",
                    generation_timestamp=datetime.now(),
                )

                self.repo.save_email_campaign(
                    {
                        "lead_id": email.lead_id,
                        "subject": email.subject,
                        "body": email.body,
                        "status": "pending",  # Strict HITL: Starts as pending
                        "tone": email.tone,
                        "word_count": email.word_count,
                        "personalization_score": email.personalization_score,
                        "urgency_level": email.urgency_level,
                        "call_to_action": email.call_to_action,
                    }
                )

                generated_emails.append(email)
                time.sleep(1)  # Delay between LLM generations

            except Exception as e:
                print(f"Error generating email for {business_name}: {e}")
                continue

        return {"generated_count": len(generated_emails), "emails": generated_emails}

    # --- HITL Orchestration & Actual Sending ---

    def process_approved_emails(self, limit: int = 50) -> int:
        """Fetch and send emails with status 'approved'"""
        pending_emails = self.repo.get_pending_emails_to_send(limit=limit)
        sent_count = 0

        print(f"Processing {len(pending_emails)} approved emails for sending")

        for i, email in enumerate(pending_emails):
            success = self.send_single_email(email["id"])
            if success:
                sent_count += 1

            # Rate limiting: 30s delay between actual sends
            if i < len(pending_emails) - 1:
                print("Waiting 30 seconds before next email send...")
                time.sleep(30)

        return sent_count

    def send_single_email(
        self, campaign_id: int, body_override: Optional[str] = None
    ) -> bool:
        """Send a single campaign email immediately. Used by API and Batch Senders."""
        try:
            row = self.repo.get_email_campaign(campaign_id)
            if not row:
                print(f"Campaign {campaign_id} not found")
                return False

            to_email = row["email"]
            business_name = row["business_name"]

            if not to_email:
                err = f"No verified email address found for {business_name}"
                print(err)
                self.repo.update_campaign_status(
                    campaign_id, "failed", error_message=err
                )
                return False

            subject = row["subject"]
            final_body = body_override if body_override else row["body"]

            # Actual SMTP send
            success = self._execute_smtp_send(to_email, subject, final_body)

            if success:
                self.repo.update_campaign_status(campaign_id, "sent", final_body)
                return True
            else:
                self.repo.update_campaign_status(
                    campaign_id, "failed", error_message="SMTP send failure"
                )
                return False

        except Exception as e:
            logger.exception(f"Exception sending email for campaign {campaign_id}: {e}")
            self.repo.update_campaign_status(
                campaign_id, "failed", error_message=str(e)
            )
            return False

    def _execute_smtp_send(self, to_email: str, subject: str, body: str) -> bool:
        """Low-level SMTP send via Flask-Mail"""
        print(f"Attempting SMTP send to {to_email}")

        try:
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; padding: 30px; border: 1px solid #ddd; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                    <div style="margin-bottom: 25px;">
                        {body.replace("\n", "<br>")}
                    </div>
                    <div style="margin-top: 40px; padding-top: 25px; border-top: 2px solid #381E72; color: #555;">
                        <p style="margin: 0; font-size: 0.95em;">Best regards,<br>
                        <strong style="color: #381E72;">Manas Doshi</strong><br>
                        <a href="https://man27.netlify.app/services" style="color: #381E72; text-decoration: none; font-weight: bold;">Web Services & Automation</a></p>
                    </div>
                </div>
                <div style="max-width: 600px; margin: 15px auto; text-align: center; color: #888; font-size: 0.8em;">
                    Disclaimer: This is a professional outreach email based on website discovery findings.
                </div>
            </body>
            </html>
            """

            msg = Message(subject=subject, recipients=[to_email], html=html_body)

            if self.mail:
                self.mail.send(msg)
            else:
                if not current_app:
                    raise RuntimeError(
                        "No Flask app context and no Mail instance provided."
                    )
                current_app.extensions["mail"].send(msg)

            logger.success(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            print(f"SMTP failed for {to_email}: {e}")
            return False

    def get_email_statistics(self) -> Dict:
        """Helper for orchestrator stats"""
        return self.repo.get_email_statistics()
