"""
Stage C: AI-Powered Messaging
Generates personalized outreach emails using local Ollama LLM
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv
import requests

load_dotenv()

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
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model_name = os.getenv('OLLAMA_MODEL', 'llama3.2')
        
        # Email templates by bucket and issue type
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Dict[str, EmailTemplate]]:
        """Load email templates from JSON config"""
        config_path = os.path.join(os.getcwd(), 'config', 'email_templates.json')
        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
                
            templates = {}
            for bucket, bucket_templates in data.get('templates', {}).items():
                templates[bucket] = {}
                for issue, tpl_data in bucket_templates.items():
                    templates[bucket][issue] = EmailTemplate(
                        template_id=tpl_data['template_id'],
                        bucket_name=tpl_data['bucket_name'],
                        issue_type=tpl_data['issue_type'],
                        subject_pattern=tpl_data['subject_pattern'],
                        body_template=tpl_data['body_template'],
                        tone=tpl_data['tone'],
                        word_count_range=tuple(tpl_data['word_count_range']),
                        conversion_focus=tpl_data['conversion_focus']
                    )
            return templates
        except FileNotFoundError:
            print(f"Warning: Email template config not found at {config_path}. Using empty defaults.")
            return {}
        except Exception as e:
            print(f"Error loading email templates: {e}")
            return {}
    
    def generate_email_with_ollama(self, business_name: str, issues: List[Dict], bucket_name: str, llm_analysis: Optional[Dict] = None) -> Dict[str, str]:
        """Generate personalized email and subject line using Ollama LLM"""
        
        # Select an example template for style
        example_template = self._select_best_template(issues, bucket_name)
        
        # Create prompt for Ollama
        prompt = self._create_prompt(business_name, issues, example_template, llm_analysis)
        
        try:
            response = requests.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "system": "You are a professional outreach specialist. You output ONLY valid JSON. No conversational filler, no 'Sure', no 'Here is the email'.",
                "options": {
                    "temperature": 0.8,
                    "top_p": 0.9,
                    "max_tokens": 500
                }
            }, timeout=300)
            
            if response.status_code == 200:
                raw_response = response.json().get('response', '{}')
                
                # Robust JSON extraction
                try:
                    data = json.loads(raw_response)
                except json.JSONDecodeError:
                    start = raw_response.find('{')
                    end = raw_response.rfind('}') + 1
                    if start != -1 and end != 0:
                        try:
                            data = json.loads(raw_response[start:end])
                        except:
                            print(f"❌ Failed to parse JSON from Ollama for {business_name}")
                            return {"subject": f"Question about {business_name}", "body": self._fallback_email(business_name, issues, example_template)}
                    else:
                        print(f"❌ No JSON found in Ollama response for {business_name}")
                        return {"subject": f"Question about {business_name}", "body": self._fallback_email(business_name, issues, example_template)}

                subject = data.get('subject', f"Quick question about {business_name}'s website")
                body = data.get('body', '').strip()
                
                if not body:
                     print(f"⚠️  Ollama returned empty body for {business_name}, using fallback.")
                     return {"subject": f"Question about {business_name}", "body": self._fallback_email(business_name, issues, example_template)}

                # Post-process and validate
                processed_body = self._post_process_email(body, business_name, example_template)
                return {"subject": subject, "body": processed_body}
            else:
                print(f"❌ Ollama API error ({response.status_code}) for {business_name}")
                return {"subject": f"Question about {business_name}", "body": self._fallback_email(business_name, issues, example_template)}
                
        except Exception as e:
            print(f"❌ Ollama Exception during email generation: {e}")
            return {"subject": f"Question about {business_name}", "body": self._fallback_email(business_name, issues, example_template)}
    
    def _select_best_template(self, issues: List[Dict], bucket_name: str) -> EmailTemplate:
        """Select the best template based on issues and bucket"""
        if bucket_name not in self.templates:
            # Use generic template
            return self.templates['Interior Designers & Architects']
        bucket_templates = self.templates[bucket_name]
        
        # Find template for highest priority issue
        priority_issues = [ 'mobile_unfriendly', 'no_contact_info', 'slow_loading', 'missing_meta']
        
        for issue in issues:
            issue_type = issue.get('issue_type', '')
            if issue_type in bucket_templates:
                return bucket_templates[issue_type]
        
        # Fallback to first available template
        return list(bucket_templates.values())[0]
    
    def _create_prompt(self, business_name: str, issues: List[Dict], template: EmailTemplate, llm_analysis: Optional[Dict] = None) -> str:
        """Create a highly dynamic prompt for Ollama"""
        issues_text = '\n'.join([f"- {issue['description']} (Severity: {issue.get('severity', 'medium')})" for issue in issues[:4]])
        
        llm_context = ""
        if llm_analysis:
            critique = llm_analysis.get('critique', '')
            impact = llm_analysis.get('business_impact', '')
            hooks = ", ".join(llm_analysis.get('hooks', []))
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
    
    def _post_process_email(self, generated_text: str, business_name: str, template: EmailTemplate) -> str:
        """Post-process generated email"""
        # Clean up common issues
        email = generated_text.strip()
        
        # Ensure proper business name
        # Ensure proper business name
        placeholders = ['[Business Name]', '{business_name}', '[Company Name]', '{company_name}']
        for placeholder in placeholders:
            if placeholder in email:
                email = email.replace(placeholder, business_name)
        
        if 'Hi there,' in email or 'Hello there,' in email:
             email = email.replace('Hi there,', f'Hi {business_name},').replace('Hello there,', f'Hi {business_name},')
        
        # Check word count
        word_count = len(email.split())
        if word_count < template.word_count_range[0] or word_count > template.word_count_range[1]:
            # Adjust length
            if word_count < template.word_count_range[0]:
                # Add more detail
                email += "\n\nThis small improvement could make a big difference for your business."
            else:
                # Trim down
                sentences = email.split('. ')
                if len(sentences) > 4:
                    email = '. '.join(sentences[:4]) + '.'
        
        return email
    
    def _fallback_email(self, business_name: str, issues: List[Dict], template: EmailTemplate) -> str:
        """Fallback email generation without Ollama"""
        issues_text = ', '.join([issue['issue_type'].replace('_', ' ').title() for issue in issues[:2]])
        
        fallback = f"""Hi {business_name},

I noticed a few technical issues on your website: {issues_text}. These might be affecting your business performance and customer trust.

I specialize in fixing these issues quickly and affordably. A simple update could help you attract more customers and appear more professional.

Would you be interested in a quick consultation about improving your website?

Best regards,
Manas Doshi
Future Forwards"""
        
        return fallback

class StageCEmailGenerator:
    """Stage C: AI-Powered Messaging"""
    
    def __init__(self):
        self.ollama_generator = OllamaEmailGenerator()
        self.generation_queue = []
    
    def generate_email_campaigns(self, batch_size: int = 20) -> Dict:
        """Generate email campaigns for qualified leads"""
        print("=== STAGE C: AI EMAIL GENERATOR ===")
        
        from core.db import LeadRepository
        repo = LeadRepository()
        
        # Fetch qualified leads that don't have campaigns
        print(f"Fetching qualified leads (limit {batch_size})...")
        candidates = repo.get_qualified_leads_for_email(batch_size)
        
        if not candidates:
            print("No qualified leads found for email generation")
            return {'generated_count': 0, 'emails': []}
            
        print(f"Found {len(candidates)} candidates for email generation")
        
        generated_emails = []
        
        for i, lead in enumerate(candidates):
            business_name = lead.get('business_name')
            print(f"\n[{i+1}/{len(candidates)}] Generating email for: {business_name}")
            
            try:
                # Parse audits
                issues = []
                if lead.get('issues_json'):
                    issues = json.loads(lead.get('issues_json'))
                
                llm_analysis = None
                if lead.get('llm_analysis'):
                    llm_analysis = json.loads(lead.get('llm_analysis'))
                
                # Generate email
                bucket_name = lead.get('bucket', 'default')
                email_content = self.generate_email_with_ollama(
                    business_name, 
                    issues, 
                    bucket_name,
                    llm_analysis
                )
                
                if not email_content:
                    print(f"Failed to generate email for {business_name}")
                    continue
                
                # Create email object
                email = GeneratedEmail(
                    lead_id=lead['id'],
                    business_name=business_name,
                    subject=email_content.get('subject', 'Partnership Opportunity'),
                    body=email_content.get('body', ''),
                    tone=email_content.get('tone', 'professional'),
                    word_count=len(email_content.get('body', '').split()),
                    personalization_score=0.8, # Estimated
                    urgency_level=email_content.get('urgency_level', 'low'),
                    call_to_action=email_content.get('call_to_action', 'Reply for more info'),
                    generation_timestamp=datetime.now()
                )
                
                # Save to database
                self._save_generated_email(email)
                generated_emails.append(email)
                
                # Delay to avoid rate limits
                time.sleep(1)
                
            except Exception as e:
                print(f"Error generating email for {business_name}: {e}")
                continue
                
        return {
            'generated_count': len(generated_emails),
            'emails': generated_emails
        }
    
    def _save_generated_email(self, email: GeneratedEmail):
        """Save generated email to database via repository"""
        from core.db import LeadRepository
        repo = LeadRepository()
        
        campaign_data = {
            'lead_id': email.lead_id,
            'subject': email.subject,
            'body': email.body,
            'status': 'pending',
            'tone': email.tone,
            'word_count': email.word_count,
            'personalization_score': email.personalization_score,
            'urgency_level': email.urgency_level,
            'call_to_action': email.call_to_action
        }
        
        repo.save_email_campaign(campaign_data)
    
    def _print_generation_summary(self, results: List[GeneratedEmail]):
        """Print email generation summary"""
        print(f"\n{'='*60}")
        print("STAGE C: AI-POWERED MESSAGING SUMMARY")
        print(f"{'='*60}")
        print(f"Emails Generated: {len(results)}")
        
        if results:
            # Tone distribution
            tone_counts = {}
            for email in results:
                tone_counts[email.tone] = tone_counts.get(email.tone, 0) + 1
            
            print(f"\n--- Tone Distribution ---")
            for tone, count in tone_counts.items():
                print(f"{tone}: {count}")
            
            # Personalization scores
            scores = [email.personalization_score for email in results]
            avg_score = sum(scores) / len(scores)
            print(f"\n--- Personalization ---")
            print(f"Average Score: {avg_score:.2f}")
            print(f"Best Score: {max(scores):.2f}")
            
            # Word count distribution
            word_counts = [email.word_count for email in results]
            avg_words = sum(word_counts) / len(word_counts)
            print(f"\n--- Word Count ---")
            print(f"Average: {avg_words:.0f} words")
            print(f"Range: {min(word_counts)} - {max(word_counts)} words")
            
            # Urgency levels
            urgency_counts = {}
            for email in results:
                urgency_counts[email.urgency_level] = urgency_counts.get(email.urgency_level, 0) + 1
            
            print(f"\n--- Urgency Levels ---")
            for urgency, count in urgency_counts.items():
                print(f"{urgency}: {count}")
    
    def get_email_statistics(self) -> Dict:
        """Get email generation statistics"""
        from core.db import LeadRepository
        repo = LeadRepository()
        return repo.get_email_statistics()

