"""
Stage C: AI-Powered Messaging
Generates personalized outreach emails using local Ollama LLM
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import sqlite3
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
        
        # Test Ollama connection
        self._test_connection()
        
        # Email templates by bucket and issue type
        self.templates = self._initialize_templates()
    
    def _test_connection(self):
        """Test connection to Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print(f"✅ Connected to Ollama at {self.ollama_url}")
            else:
                print(f"⚠️  Ollama responded with status {response.status_code}")
        except Exception as e:
            print(f"❌ Cannot connect to Ollama: {e}")
            print("Make sure Ollama is running: ollama serve")
    
    def _initialize_templates(self) -> Dict[str, Dict[str, EmailTemplate]]:
        """Initialize email templates by bucket and issue type"""
        templates = {
            'Interior Designers & Architects': {
                'missing_ssl': EmailTemplate(
                    template_id='int_missing_ssl',
                    bucket_name='Interior Designers & Architects',
                    issue_type='missing_ssl',
                    subject_pattern='Security notice for {business_name}',
                    body_template='''Hi {business_name},

I noticed your beautiful portfolio website isn't using HTTPS encryption. In today's digital landscape, potential clients expect secure browsing, especially when viewing design portfolios.

A simple SSL certificate would:
- Build trust with high-value clients
- Improve your Google ranking
- Protect your portfolio images from theft
- Show professionalism to architecture firms

I can help you get this set up in under 24 hours. Your work deserves a secure showcase.

Would you be open to a quick chat about securing your site?

Best regards,
[Your Name]
Web Security Specialist''',
                    tone='professional',
                    word_count_range=(110, 130),
                    conversion_focus='trust_and_security'
                ),
                'mobile_unfriendly': EmailTemplate(
                    template_id='int_mobile',
                    bucket_name='Interior Designers & Architects',
                    issue_type='mobile_unfriendly',
                    subject_pattern='Mobile experience for {business_name}',
                    body_template='''Hi {business_name},

I was admiring your design work on my phone and noticed your site doesn't display properly on mobile. With 70% of clients browsing on phones, you might be missing opportunities.

Your stunning designs deserve to shine on every device. A responsive update would:
- Impress mobile-first clients
- Showcase your portfolio beautifully on phones
- Help you stand out from competitors
- Increase inquiry rates

I specialize in making design portfolios mobile-perfect. Quick turnaround, beautiful results.

Interested in seeing how your site could look on mobile?

Best regards,
[Your Name]
Mobile Design Specialist''',
                    tone='friendly',
                    word_count_range=(115, 135),
                    conversion_focus='visual_appeal'
                ),
                'slow_loading': EmailTemplate(
                    template_id='int_slow',
                    bucket_name='Interior Designers & Architects',
                    issue_type='slow_loading',
                    subject_pattern='Portfolio speed for {business_name}',
                    body_template='''Hi {business_name},

Your design portfolio is impressive, but it's taking over 5 seconds to load. Potential clients likely leave before seeing your best work.

Fast loading matters because:
- 53% of visitors abandon sites after 3 seconds
- Google ranks faster sites higher
- Slow sites appear unprofessional
- You lose high-value client inquiries

I can optimize your portfolio to load in under 2 seconds while maintaining image quality. Your work deserves instant impact.

Want me to show you the speed improvement potential?

Best regards,
[Your Name]
Performance Specialist''',
                    tone='professional',
                    word_count_range=(110, 130),
                    conversion_focus='performance'
                )
            },
            'Local Service Providers': {
                'missing_ssl': EmailTemplate(
                    template_id='svc_missing_ssl',
                    bucket_name='Local Service Providers',
                    issue_type='missing_ssl',
                    subject_pattern='Customer trust for {business_name}',
                    body_template='''Hi {business_name},

I found your business while searching for local services, but noticed your site isn't secure (no HTTPS). Many customers won't trust non-secure sites with their information.

Security matters for service businesses because:
- Customers feel safer sharing contact details
- Google favors secure sites in local search
- Builds credibility for your services
- Helps you stand out from competitors

I can add SSL security quickly and affordably. More trust = more customers.

Would you like to discuss securing your site?

Best regards,
[Your Name]
Local Business Specialist''',
                    tone='friendly',
                    word_count_range=(110, 130),
                    conversion_focus='trust_and_leads'
                ),
                'no_contact_info': EmailTemplate(
                    template_id='svc_no_contact',
                    bucket_name='Local Service Providers',
                    issue_type='no_contact_info',
                    subject_pattern='Missing calls for {business_name}',
                    body_template='''Hi {business_name},

I was interested in your services but couldn't find your phone number easily. You might be missing customer calls every day.

Clear contact information helps:
- Customers reach you immediately
- Emergency service inquiries
- Local search rankings
- Build trust with visitors

A simple contact section could double your customer inquiries. Small change, big impact.

Want me to show you how to make your contact info impossible to miss?

Best regards,
[Your Name]
Customer Acquisition Specialist''',
                    tone='urgent',
                    word_count_range=(105, 125),
                    conversion_focus='lead_generation'
                ),
                'poor_navigation': EmailTemplate(
                    template_id='svc_navigation',
                    bucket_name='Local Service Providers',
                    issue_type='poor_navigation',
                    subject_pattern='Website navigation for {business_name}',
                    body_template='''Hi {business_name},

I was exploring your services but had trouble finding what I needed. Poor navigation confuses customers and costs you business.

Good navigation helps customers:
- Find your services quickly
- Understand what you offer
- Contact you faster
- Choose you over competitors

I can redesign your navigation to guide customers straight to your services. More clarity = more customers.

Interested in seeing how better navigation could help?

Best regards,
[Your Name]
User Experience Specialist''',
                    tone='casual',
                    word_count_range=(110, 130),
                    conversion_focus='user_experience'
                )
            },
            'Small B2B Agencies': {
                'missing_meta': EmailTemplate(
                    template_id='b2b_meta',
                    bucket_name='Small B2B Agencies',
                    issue_type='missing_meta',
                    subject_pattern='Google visibility for {business_name}',
                    body_template='''Hi {business_name},

Your agency does great work, but you're invisible to Google searches because you're missing meta descriptions. Potential clients can't find you online.

Meta descriptions help by:
- Appearing in Google search results
- Explaining your services to searchers
- Increasing click-through rates
- Attracting your ideal clients

I can write compelling meta descriptions that get you found by the right clients. Better visibility = better clients.

Want help getting discovered by your target market?

Best regards,
[Your Name]
SEO Specialist''',
                    tone='professional',
                    word_count_range=(110, 130),
                    conversion_focus='visibility_and_leads'
                ),
                'old_technology': EmailTemplate(
                    template_id='b2b_old_tech',
                    bucket_name='Small B2B Agencies',
                    issue_type='old_technology',
                    subject_pattern='Website update for {business_name}',
                    body_template='''Hi {business_name},

I noticed your site is running on outdated technology. This can make your agency appear behind the times to potential B2B clients.

Modern technology shows clients you're:
- Current with industry standards
- Serious about your online presence
- Technologically capable
- Worth premium rates

I can modernize your site while keeping your brand intact. Look current, charge more.

Ready to update your digital image?

Best regards,
[Your Name]
Technology Specialist''',
                    tone='professional',
                    word_count_range=(105, 125),
                    conversion_focus='professional_image'
                )
            }
        }
        
        return templates
    
    def generate_email_with_ollama(self, business_name: str, issues: List[Dict], bucket_name: str, llm_analysis: Optional[Dict] = None) -> str:
        """Generate personalized email using Ollama LLM"""
        
        # Select best template
        template = self._select_best_template(issues, bucket_name)
        
        # Create prompt for Ollama
        prompt = self._create_prompt(business_name, issues, template, llm_analysis)
        
        try:
            response = requests.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 300
                }
            }, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                generated_text = data.get('response', '').strip()
                
                # Post-process and validate
                return self._post_process_email(generated_text, business_name, template)
            else:
                print(f"Ollama error: {response.status_code}")
                return self._fallback_email(business_name, issues, template)
                
        except Exception as e:
            print(f"Error generating email with Ollama: {e}")
            return self._fallback_email(business_name, issues, template)
    
    def _select_best_template(self, issues: List[Dict], bucket_name: str) -> EmailTemplate:
        """Select the best template based on issues and bucket"""
        if bucket_name not in self.templates:
            # Use generic template
            return self.templates['Interior Designers & Architects']['missing_ssl']
        
        bucket_templates = self.templates[bucket_name]
        
        # Find template for highest priority issue
        priority_issues = ['missing_ssl', 'mobile_unfriendly', 'no_contact_info', 'slow_loading', 'missing_meta']
        
        for issue in issues:
            issue_type = issue.get('issue_type', '')
            if issue_type in bucket_templates:
                return bucket_templates[issue_type]
        
        # Fallback to first available template
        return list(bucket_templates.values())[0]
    
    def _create_prompt(self, business_name: str, issues: List[Dict], template: EmailTemplate, llm_analysis: Optional[Dict] = None) -> str:
        """Create prompt for Ollama"""
        issues_text = '\n'.join([f"- {issue['description']}" for issue in issues[:3]])
        
        llm_context = ""
        if llm_analysis:
            critique = llm_analysis.get('critique', '')
            impact = llm_analysis.get('business_impact', '')
            hooks = ", ".join(llm_analysis.get('hooks', []))
            llm_context = f"""
TECHNICAL CRITIQUE FROM AUDITOR: {critique}
BUSINESS IMPACT: {impact}
PERSONALIZED HOOKS TO USE: {hooks}
"""

        prompt = f"""Write a short cold email (110-130 words exactly) to {business_name}.

BUSINESS TYPE: {template.bucket_name}
{llm_context}
ISSUES ON THEIR SITE:
{issues_text}

TONE: {template.tone}
FOCUS: {template.conversion_focus}

TEMPLATE GUIDELINES:
{template.body_template}

REQUIREMENTS:
1. Acknowledge their business briefly.
2. USE ONE OF THE PERSONALIZED HOOKS provided above.
3. Mention the specific 'BUSINESS IMPACT' identified by the auditor.
4. Offer a clear solution (no hard selling).
5. End with a simple, specific call-to-action.
6. conversational but {template.tone}.
7. Exactly 110-130 words.

Write the email now:"""

        return prompt
    
    def _post_process_email(self, generated_text: str, business_name: str, template: EmailTemplate) -> str:
        """Post-process generated email"""
        # Clean up common issues
        email = generated_text.strip()
        
        # Ensure proper business name
        if business_name not in email:
            email = email.replace('[Business Name]', business_name)
            email = email.replace('Hi there,', f'Hi {business_name},')
        
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
[Your Name]
Web Services Specialist"""
        
        return fallback

class StageCEmailGenerator:
    """Stage C: AI-Powered Messaging"""
    
    def __init__(self):
        self.ollama_generator = OllamaEmailGenerator()
        self.generation_queue = []
    
    def generate_emails_for_qualified_leads(self, batch_size: int = 50) -> Dict:
        """Generate emails for all qualified leads without existing emails"""
        print("=== STAGE C: AI-POWERED MESSAGING ===")
        
        # Get qualified leads from database
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT l.id, l.business_name, l.bucket, a.issues_json, a.overall_score, a.llm_analysis
        FROM leads l
        JOIN audits a ON l.id = a.lead_id
        WHERE a.qualified = 1 
        AND l.id NOT IN (
            SELECT DISTINCT lead_id FROM email_campaigns
        )
        ORDER BY a.overall_score DESC
        LIMIT ?
        ''', (batch_size,))
        
        qualified_leads = cursor.fetchall()
        conn.close()
        
        if not qualified_leads:
            print("No qualified leads without emails")
            return {'generated_count': 0, 'results': []}
        
        print(f"Found {len(qualified_leads)} qualified leads for email generation")
        
        results = []
        generated_count = 0
        
        for i, (lead_id, business_name, bucket, issues_json, overall_score, llm_analysis_json) in enumerate(qualified_leads):
            print(f"\n[{i+1}/{len(qualified_leads)}] Generating email for: {business_name}")
            
            try:
                # Parse issues and llm_analysis
                issues = json.loads(issues_json) if issues_json else []
                llm_analysis = json.loads(llm_analysis_json) if llm_analysis_json else None
                
                # Generate email
                email_body = self.ollama_generator.generate_email_with_ollama(
                    business_name, issues, bucket or 'Interior Designers & Architects', llm_analysis
                )
                
                # Create subject line
                subject = f"Quick question about {business_name}'s website"
                
                # Create email object
                generated_email = GeneratedEmail(
                    lead_id=lead_id,
                    business_name=business_name,
                    subject=subject,
                    body=email_body,
                    tone=self._detect_tone(email_body),
                    word_count=len(email_body.split()),
                    personalization_score=self._calculate_personalization_score(email_body, business_name, issues),
                    urgency_level=self._detect_urgency(email_body, issues),
                    call_to_action=self._extract_call_to_action(email_body),
                    generation_timestamp=datetime.now()
                )
                
                results.append(generated_email)
                
                # Save to database
                self._save_generated_email(generated_email)
                
                generated_count += 1
                print(f"✅ Generated email ({generated_email.word_count} words)")
                
                # Add delay between generations
                time.sleep(1)
                
            except Exception as e:
                print(f"❌ Error generating email for {business_name}: {e}")
                continue
        
        # Print summary
        self._print_generation_summary(results)
        
        return {
            'generated_count': generated_count,
            'results': results
        }
    
    def _detect_tone(self, email_body: str) -> str:
        """Detect email tone"""
        friendly_words = ['hi', 'hello', 'great', 'wonderful', 'love', 'excited']
        professional_words = ['regards', 'professional', 'specialist', 'expert', 'quality']
        urgent_words = ['urgent', 'immediately', 'quickly', 'now', 'today']
        
        body_lower = email_body.lower()
        
        if any(word in body_lower for word in urgent_words):
            return 'urgent'
        elif any(word in body_lower for word in professional_words):
            return 'professional'
        elif any(word in body_lower for word in friendly_words):
            return 'friendly'
        else:
            return 'casual'
    
    def _calculate_personalization_score(self, email_body: str, business_name: str, issues: List[Dict]) -> float:
        """Calculate personalization score (0.0 to 1.0)"""
        score = 0.0
        
        # Business name mention
        if business_name.lower() in email_body.lower():
            score += 0.3
        
        # Issue-specific content
        for issue in issues[:2]:
            issue_desc = issue.get('description', '').lower()
            if any(word in email_body.lower() for word in issue_desc.split()[:3]):
                score += 0.2
        
        # Industry-specific language
        industry_keywords = ['portfolio', 'clients', 'customers', 'services', 'business']
        if any(keyword in email_body.lower() for keyword in industry_keywords):
            score += 0.2
        
        # Call to action
        if 'interested' in email_body.lower() or 'would you like' in email_body.lower():
            score += 0.1
        
        # Proper length
        word_count = len(email_body.split())
        if 110 <= word_count <= 130:
            score += 0.2
        
        return min(score, 1.0)
    
    def _detect_urgency(self, email_body: str, issues: List[Dict]) -> str:
        """Detect urgency level"""
        high_urgency_issues = ['missing_ssl', 'no_contact_info', 'audit_error']
        medium_urgency_issues = ['slow_loading', 'mobile_unfriendly']
        
        for issue in issues:
            issue_type = issue.get('issue_type', '')
            if issue_type in high_urgency_issues:
                return 'high'
            elif issue_type in medium_urgency_issues:
                return 'medium'
        
        return 'low'
    
    def _extract_call_to_action(self, email_body: str) -> str:
        """Extract call to action from email"""
        sentences = email_body.split('.')
        
        for sentence in sentences:
            if any(keyword in sentence.lower() for keyword in ['interested', 'would you', 'let me', 'contact']):
                return sentence.strip()
        
        return 'Standard inquiry'
    
    def _save_generated_email(self, email: GeneratedEmail):
        """Save generated email to database"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO email_campaigns 
        (lead_id, subject, body, status, tone, word_count, personalization_score, urgency_level, call_to_action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            email.lead_id,
            email.subject,
            email.body,
            'pending',
            email.tone,
            email.word_count,
            email.personalization_score,
            email.urgency_level,
            email.call_to_action
        ))
        
        conn.commit()
        conn.close()
    
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
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            COUNT(*) as total_emails,
            COUNT(CASE WHEN status = 'sent' THEN 1 END) as sent,
            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
            AVG(personalization_score) as avg_personalization,
            AVG(word_count) as avg_word_count
        FROM email_campaigns
        ''')
        
        stats = cursor.fetchone()
        conn.close()
        
        return {
            'total_generated': stats[0] or 0,
            'sent': stats[1] or 0,
            'pending': stats[2] or 0,
            'failed': stats[3] or 0,
            'personalization_avg': stats[4] or 0,
            'word_count_avg': stats[5] or 0
        }

if __name__ == '__main__':
    # Demo usage
    generator = StageCEmailGenerator()
    
    print("Stage C: AI-Powered Messaging")
    print("Choose an option:")
    print("1. Generate emails for qualified leads")
    print("2. Get email statistics")
    print("3. Test single email generation")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == '1':
        results = generator.generate_emails_for_qualified_leads(batch_size=20)
        print(f"\n✅ Generated {results['generated_count']} emails")
    elif choice == '2':
        stats = generator.get_email_statistics()
        print(f"\n=== EMAIL STATISTICS ===")
        print(f"Total Generated: {stats['total_generated']}")
        print(f"Sent: {stats['sent']}")
        print(f"Pending: {stats['pending']}")
        print(f"Failed: {stats['failed']}")
        print(f"Avg Personalization: {stats['personalization_avg']:.2f}")
        print(f"Avg Word Count: {stats['word_count_avg']:.0f}")
    elif choice == '3':
        business_name = input("Enter business name: ").strip()
        bucket_name = input("Enter bucket name: ").strip()
        
        # Sample issues for testing
        sample_issues = [
            {'issue_type': 'missing_ssl', 'description': 'Website not using HTTPS encryption'},
            {'issue_type': 'mobile_unfriendly', 'description': 'Not optimized for mobile devices'}
        ]
        
        email = generator.ollama_generator.generate_email_with_ollama(business_name, sample_issues, bucket_name)
        
        print(f"\n=== GENERATED EMAIL ===")
        print(f"Word Count: {len(email.split())}")
        print(f"\n{email}")
    else:
        print("Invalid choice")
