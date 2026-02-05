"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)"""
import json
import requests
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from lead_repository import LeadRepository


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation)"""

    def __init__(self):
        self.repo = LeadRepository()
        self.ollama_url = "http://localhost:11434"
        self.ollama_enabled = self._test_ollama()
        self.templates = self._load_templates()

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def _load_templates(self) -> Dict:
        """Load email templates"""
        try:
            with open("config/email_templates.json") as f:
                return json.load(f).get("templates", {})
        except:
            return {}

    def audit_website(self, url: str) -> Dict:
        """Audit website for technical issues"""
        issues = []
        score = 100
        
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            # Check page title
            title = soup.find("title")
            if not title or len(title.text.strip()) < 10:
                issues.append({
                    "type": "missing_title",
                    "severity": "high",
                    "description": "Page title missing or too short"
                })
                score -= 15

            # Check meta description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if not meta_desc:
                issues.append({
                    "type": "missing_meta",
                    "severity": "medium",
                    "description": "Meta description missing"
                })
                score -= 10

            # Check viewport (mobile-friendly)
            viewport = soup.find("meta", attrs={"name": "viewport"})
            if not viewport:
                issues.append({
                    "type": "no_viewport",
                    "severity": "high",
                    "description": "Not mobile-friendly"
                })
                score -= 20

            # Check heading structure
            h1_tags = soup.find_all("h1")
            if len(h1_tags) == 0:
                issues.append({
                    "type": "no_h1",
                    "severity": "medium",
                    "description": "Missing H1 heading"
                })
                score -= 10
            elif len(h1_tags) > 1:
                issues.append({
                    "type": "multiple_h1",
                    "severity": "low",
                    "description": "Multiple H1 tags"
                })
                score -= 5

            # Check images without alt text
            images = soup.find_all("img")
            images_without_alt = [img for img in images if not img.get("alt")]
            if images_without_alt and len(images_without_alt) > len(images) * 0.3:
                issues.append({
                    "type": "missing_alt_text",
                    "severity": "medium",
                    "description": f"{len(images_without_alt)} images without alt text"
                })
                score -= 10

            # Check for Google Analytics
            has_analytics = bool(
                soup.find("script", src=lambda x: x and "google-analytics" in x) or
                soup.find("script", src=lambda x: x and "gtag" in x)
            )
            if not has_analytics:
                issues.append({
                    "type": "no_analytics",
                    "severity": "low",
                    "description": "No Google Analytics detected"
                })
                score -= 5

            # Check SSL
            if not url.startswith("https://"):
                issues.append({
                    "type": "no_ssl",
                    "severity": "critical",
                    "description": "Website not using HTTPS"
                })
                score -= 25

            # Response time check
            response_time = response.elapsed.total_seconds()
            if response_time > 3:
                issues.append({
                    "type": "slow_load",
                    "severity": "medium",
                    "description": f"Slow page load time: {response_time:.2f}s"
                })
                score -= 10

        except requests.exceptions.Timeout:
            issues.append({
                "type": "timeout",
                "severity": "critical",
                "description": "Website timeout"
            })
            score = 20
        except Exception as e:
            issues.append({
                "type": "error",
                "severity": "critical",
                "description": f"Audit error: {str(e)}"
            })
            score = 30

        # Qualification logic: score > 40 and has fixable issues
        qualified = score < 80 and score > 40 and len(issues) >= 2

        return {
            "url": url,
            "score": max(0, score),
            "issues": issues,
            "qualified": 1 if qualified else 0
        }

    def generate_email_ollama(self, business_name: str, issues: List[Dict], bucket: str) -> Dict:
        """Generate email using Ollama LLM"""
        if not self.ollama_enabled:
            return self.generate_email_template(business_name, issues)

        # Build prompt
        issue_summary = "\n".join([f"- {i['description']}" for i in issues[:3]])
        
        prompt = f"""Generate a professional cold email for {business_name}.

Technical issues found:
{issue_summary}

Create a personalized outreach email that:
1. Shows you've reviewed their website
2. Mentions 1-2 specific issues
3. Offers value, not a sales pitch
4. Has a soft call-to-action
5. Keeps it under 150 words

Return ONLY JSON:
{{
  "subject": "brief subject line",
  "body": "email body with proper line breaks"
}}"""

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a professional email writer. Output ONLY valid JSON."
                },
                timeout=60
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                try:
                    data = json.loads(raw)
                    return {
                        "subject": data.get("subject", f"Quick note about {business_name}"),
                        "body": data.get("body", self._fallback_email(business_name, issues))
                    }
                except:
                    pass
        except:
            pass

        return self.generate_email_template(business_name, issues)

    def generate_email_template(self, business_name: str, issues: List[Dict]) -> Dict:
        """Generate email using template fallback"""
        issue_desc = issues[0]["description"] if issues else "website improvements"
        
        subject = f"Quick question about {business_name}'s website"
        body = f"""Hi {business_name} team,

I came across your website while researching local businesses in your area.

I noticed {issue_desc.lower()}, which might be affecting your online visibility.

Would you be open to a quick chat about how to improve your web presence?

Best regards"""

        return {"subject": subject, "body": body}

    def _fallback_email(self, business_name: str, issues: List[Dict]) -> str:
        """Fallback email body"""
        issue_desc = issues[0]["description"] if issues else "some opportunities"
        return f"""Hi {business_name} team,

I recently reviewed your website and noticed {issue_desc.lower()}.

I'd love to share some suggestions that could help improve your online presence.

Would you be interested in a brief conversation?

Best regards"""

    def audit_leads(self, limit: int = 20) -> Dict:
        """Audit pending leads"""
        print(f"\n{'='*60}")
        print("OUTREACH: Lead Auditing")
        print(f"{'='*60}")

        leads = self.repo.get_pending_audits(limit)
        print(f"Auditing {len(leads)} leads...")

        audited = 0
        qualified = 0

        for i, lead in enumerate(leads, 1):
            print(f"\n[{i}/{len(leads)}] {lead['business_name']}")
            
            audit_result = self.audit_website(lead["website"])
            self.repo.save_audit(lead["id"], audit_result)
            
            audited += 1
            if audit_result["qualified"]:
                qualified += 1
                print(f"  ✓ Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])})")
            else:
                print(f"  ✗ Not qualified (Score: {audit_result['score']})")
            
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"Auditing Complete: {audited} audited, {qualified} qualified")
        print(f"{'='*60}\n")

        return {
            "audited": audited,
            "qualified": qualified
        }

    def generate_emails(self, limit: int = 20) -> Dict:
        """Generate emails for qualified leads"""
        print(f"\n{'='*60}")
        print("OUTREACH: Email Generation")
        print(f"{'='*60}")

        leads = self.repo.get_qualified_leads(limit)
        print(f"Generating emails for {len(leads)} qualified leads...")

        generated = 0

        for i, lead in enumerate(leads, 1):
            print(f"\n[{i}/{len(leads)}] {lead['business_name']}")
            
            try:
                issues = json.loads(lead.get("issues_json", "[]"))
                email = self.generate_email_ollama(
                    lead["business_name"],
                    issues,
                    lead["bucket"]
                )
                
                self.repo.save_email(lead["id"], email["subject"], email["body"])
                generated += 1
                print(f"  ✓ Email generated")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"Email Generation Complete: {generated} emails created")
        print(f"{'='*60}\n")

        return {"generated": generated}
