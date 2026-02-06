"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)"""

import json
import requests
import time
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from lead_repository import LeadRepository


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation)"""

    def __init__(self, repo=None, logger=None):
        self.repo = repo or LeadRepository()
        self.ollama_url = "http://localhost:11434"
        self.ollama_enabled = self._test_ollama()
        self.logger = logger
        self.audit_settings = self._load_audit_settings()

    def _load_audit_settings(self) -> Dict:
        """Load audit settings from config file"""
        try:
            with open("config/audit_settings.json", "r") as f:
                return json.load(f)
        except Exception as e:
            self.log(f"Error loading audit settings: {e}", "error")
            return {"technical_checks": [], "llm_audit": {"enabled": False}}

    def log(self, message: str, style: str = ""):
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False

    def deep_discovery(self, soup: BeautifulSoup, base_url: str) -> Dict:
        """Deep discovery of contact information from website"""
        contact_info = {
            "email": None,
            "social_links": {},
            "contact_form_url": None,
            "phone": None,
        }

        # 1. Extract Emails using Regex
        email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(email_regex, soup.get_text())
        if emails:
            # Simple heuristic: ignore common false positives or generic images
            valid_emails = [
                e for e in emails if not e.endswith((".png", ".jpg", ".jpeg", ".gif"))
            ]
            if valid_emails:
                contact_info["email"] = valid_emails[0].lower()

        # 2. Extract Social Links & Contact Forms
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()

            # Social Media
            if "linkedin.com" in href:
                contact_info["social_links"]["linkedin"] = link["href"]
            elif "facebook.com" in href:
                contact_info["social_links"]["facebook"] = link["href"]
            elif "instagram.com" in href:
                contact_info["social_links"]["instagram"] = link["href"]
            elif "twitter.com" in href or "x.com" in href:
                contact_info["social_links"]["twitter"] = link["href"]

            # Contact Form/Page
            if any(k in href for k in ["contact", "get-in-touch", "support"]):
                if not href.startswith("http"):
                    # Resolve relative URL
                    from urllib.parse import urljoin

                    contact_info["contact_form_url"] = urljoin(base_url, link["href"])
                else:
                    contact_info["contact_form_url"] = link["href"]

        # 3. Detect Phone (mailto/tel)
        tel_link = soup.find("a", href=lambda x: x and x.startswith("tel:"))
        if tel_link:
            contact_info["phone"] = tel_link["href"].replace("tel:", "")

        return contact_info

    def audit_website(
        self, url: str, business_name: str = "this business", bucket_name: str = None
    ) -> Dict:
        """Audit website for technical and qualitative issues + Deep Discovery"""
        issues = []
        score = 100
        discovered_info = {}

        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            # DEEP DISCOVERY: Find contact info
            discovered_info = self.deep_discovery(soup, url)

            # If no email yet, try crawling contact page if found
            if not discovered_info["email"] and discovered_info["contact_form_url"]:
                try:
                    c_resp = requests.get(
                        discovered_info["contact_form_url"], headers=headers, timeout=5
                    )
                    c_soup = BeautifulSoup(c_resp.content, "html.parser")
                    c_info = self.deep_discovery(
                        c_soup, discovered_info["contact_form_url"]
                    )
                    if c_info["email"]:
                        discovered_info["email"] = c_info["email"]
                    if c_info["phone"] and not discovered_info["phone"]:
                        discovered_info["phone"] = c_info["phone"]
                except:
                    pass

            # Combine global checks with bucket overrides
            checks = self.audit_settings.get("technical_checks", []).copy()
            if bucket_name and bucket_name in self.audit_settings.get(
                "bucket_overrides", {}
            ):
                overrides = self.audit_settings["bucket_overrides"][bucket_name]
                checks.extend(overrides.get("technical_checks", []))

            # Technical checks
            for check in checks:
                check_type = check.get("type")
                selector = check.get("selector")

                if check_type == "html_exists":
                    elem = soup.select_one(selector)
                    if not elem or (
                        check.get("min_length")
                        and len(elem.text.strip()) < check["min_length"]
                    ):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "html_count":
                    count = len(soup.select(selector))
                    if (
                        check.get("max_count") is not None
                        and count > check["max_count"]
                    ):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": f"{check['description']} ({count} found)",
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "image_alt_ratio":
                    images = soup.find_all("img")
                    if images:
                        without_alt = [img for img in images if not img.get("alt")]
                        if len(without_alt) > len(images) * check.get("threshold", 0.3):
                            issues.append(
                                {
                                    "type": check["id"],
                                    "severity": check["severity"],
                                    "description": f"{len(without_alt)}/{len(images)} images missing alt text",
                                }
                            )
                            score -= check["score_impact"]

                elif check_type == "script_match":
                    patterns = check.get("patterns", [])
                    found = False
                    for script in soup.find_all("script", src=True):
                        if any(p in script["src"] for p in patterns):
                            found = True
                            break
                    if not found:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "protocol_check":
                    if not url.startswith(check.get("protocol", "https://")):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "load_time":
                    if response.elapsed.total_seconds() > check.get("threshold", 3.0):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": f"{check['description']} ({response.elapsed.total_seconds():.2f}s)",
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "link_match":
                    patterns = check.get("patterns", [])
                    found = False
                    for link in soup.find_all("a", href=True):
                        href = link["href"].lower()
                        if any(p in href for p in patterns):
                            found = True
                            break
                    if not found:
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": check["severity"],
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

            # Qualitative LLM Audit
            llm_config = self.audit_settings.get("llm_audit", {})
            if self.ollama_enabled and llm_config.get("enabled"):
                # Extract text for LLM
                for script in soup(["script", "style"]):
                    script.decompose()
                text_content = soup.get_text(separator=" ", strip=True)[:2000]

                llm_result = self._run_llm_audit(
                    business_name, text_content, llm_config
                )
                if llm_result:
                    qual_score = llm_result.get("qualitative_score", 100)
                    # Adjust main score based on qualitative score (weighted 30%)
                    score = (score * 0.7) + (qual_score * 0.3)

                    for obs in llm_result.get("observations", []):
                        issues.append(
                            {
                                "type": f"llm_{obs.get('type', 'observation')}",
                                "severity": obs.get("severity", "info"),
                                "description": f"LLM: {obs.get('description')}",
                            }
                        )

        except requests.exceptions.Timeout:
            issues.append(
                {
                    "type": "timeout",
                    "severity": "critical",
                    "description": "Website timeout",
                }
            )
            score = 20
        except Exception as e:
            issues.append(
                {
                    "type": "error",
                    "severity": "critical",
                    "description": f"Audit error: {str(e)}",
                }
            )
            score = 30

        # Qualification logic
        qualified = score < 85 and score > 40 and len(issues) >= 2

        return {
            "url": url,
            "score": int(max(0, score)),
            "issues": issues,
            "qualified": 1 if qualified else 0,
            "discovered_info": discovered_info,
        }

    def _run_llm_audit(
        self, business_name: str, content: str, config: Dict
    ) -> Optional[Dict]:
        """Run qualitative audit using Ollama"""
        prompt = config.get("prompt", "").format(
            business_name=business_name, content=content
        )

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": config.get("model", "qwen3:8b"),
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a website quality auditor and you are a professional web developer and end the mail with the signature Best regards, Manas Doshi, Future Forwards - https://man27.netlify.app/services. Output ONLY valid JSON.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                return json.loads(raw)
        except:
            pass
        return None

    def generate_email_ollama(
        self, business_name: str, issues: List[Dict], bucket: str
    ) -> Dict:
        """Generate email using Ollama LLM"""
        if not self.ollama_enabled:
            return self.generate_email_template(business_name, issues, bucket)

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
6. end the mail with Best regards,
Manas Doshi,
Future Forwards - https://man27.netlify.app/services

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
                    "system": "You are a professional email writer and end the mail with the signature Best regards, Manas Doshi, Future Forwards - https://man27.netlify.app/services. Output ONLY valid JSON.",
                },
                timeout=60,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                try:
                    data = json.loads(raw)
                    return {
                        "subject": data.get(
                            "subject", f"Quick note about {business_name}"
                        ),
                        "body": data.get(
                            "body", self._fallback_email(business_name, issues)
                        ),
                    }
                except:
                    pass
        except:
            pass

        return self.generate_email_template(business_name, issues, bucket)

    def generate_email_template(
        self, business_name: str, issues: List[Dict], bucket: str = None
    ) -> Dict:
        """Generate email using DB templates"""
        if bucket:
            templates = self.repo.get_templates_for_bucket(bucket)
            # Map audit issues to template issue types
            # Audit issues types: missing_title, missing_meta, no_viewport, etc.
            # Template issue types (from file): mobile_unfriendly, etc.

            # Simple mapping for now
            issue_map = {
                "no_viewport": "mobile_unfriendly",
                "missing_title": "seo_issue",
                "missing_meta": "seo_issue",
            }

            for issue in issues:
                mapped_type = issue_map.get(issue["type"])
                if mapped_type and mapped_type in templates:
                    tpl = templates[mapped_type]
                    subject = tpl.get("subject_pattern", "").replace(
                        "{business_name}", business_name
                    )
                    body = tpl.get("body_template", "").replace(
                        "{business_name}", business_name
                    )
                    if subject and body:
                        return {"subject": subject, "body": body}

        # Fallback if no template found
        issue_desc = issues[0]["description"] if issues else "website improvements"

        subject = f"Quick question about {business_name}'s website"
        body = f"""Hi {business_name} team,

I came across your website while researching local businesses in your area.

I noticed {issue_desc.lower()}, which might be affecting your online visibility.

Would you be open to a quick chat about how to improve your web presence?

Best regards,
Manas Doshi,
Future Forwards - https://man27.netlify.app/services

"""

        return {"subject": subject, "body": body}

    def _fallback_email(self, business_name: str, issues: List[Dict]) -> str:
        """Fallback email body"""
        issue_desc = issues[0]["description"] if issues else "some opportunities"
        return f"""Hi {business_name} team,

I recently reviewed your website and noticed {issue_desc.lower()}.

I'd love to share some suggestions that could help improve your online presence.

Would you be interested in a brief conversation?

Best regards,
Manas Doshi,
Future Forwards - https://man27.netlify.app/services
"""

    def audit_leads(self, limit: int = 20) -> Dict:
        """Audit pending leads"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Lead Auditing")
        self.log(f"{'=' * 60}")

        leads = self.repo.get_pending_audits(limit)
        self.log(f"Auditing {len(leads)} leads...", "info")

        audited = 0
        qualified = 0

        for i, lead in enumerate(leads, 1):
            self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

            audit_result = self.audit_website(
                lead["website"], lead["business_name"], lead["bucket"]
            )
            self.repo.save_audit(lead["id"], audit_result)

            # DEEP DISCOVERY: Update lead with newly found contact info
            if "discovered_info" in audit_result:
                info = audit_result["discovered_info"]
                self.repo.update_lead_contact_info(lead["id"], info)
                if info["email"]:
                    self.log(f"  ✉ Found email: {info['email']}", "success")
                if info["social_links"]:
                    self.log(
                        f"  🔗 Found {len(info['social_links'])} social links",
                        "success",
                    )

            audited += 1
            if audit_result["qualified"]:
                qualified += 1
                self.log(
                    f"  ✓ Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])})",
                    "success",
                )
            else:
                self.log(f"  ✗ Not qualified (Score: {audit_result['score']})", "error")

            time.sleep(1)

        self.log(f"\n{'=' * 60}")
        self.log(
            f"Auditing Complete: {audited} audited, {qualified} qualified", "success"
        )
        self.log(f"{'=' * 60}\n")

        return {"audited": audited, "qualified": qualified}

    def generate_emails(self, limit: int = 20) -> Dict:
        """Generate emails for qualified leads"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Email Generation")
        self.log(f"{'=' * 60}")

        leads = self.repo.get_qualified_leads(limit)
        self.log(f"Generating emails for {len(leads)} qualified leads...", "info")

        generated = 0

        for i, lead in enumerate(leads, 1):
            self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

            try:
                issues = json.loads(lead.get("issues_json", "[]"))
                email = self.generate_email_ollama(
                    lead["business_name"], issues, lead["bucket"]
                )

                self.repo.save_email(lead["id"], email["subject"], email["body"])
                generated += 1
                self.log("  ✓ Email generated", "success")

            except Exception as e:
                self.log(f"  ✗ Error: {e}", "error")

            time.sleep(1)

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Generation Complete: {generated} emails created", "success")
        self.log(f"{'=' * 60}\n")

        return {"generated": generated}
