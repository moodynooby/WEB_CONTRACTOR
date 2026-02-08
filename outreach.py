"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)"""

import json
import requests
import time
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from lead_repository import LeadRepository


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation)"""

    def __init__(self, repo=None, logger=None):
        self.repo = repo or LeadRepository()
        self.ollama_url = "http://localhost:11434"
        self.ollama_enabled = self._test_ollama()
        self.logger = logger
        self.audit_settings = self._load_audit_settings()
        self.max_workers = 5  # Number of parallel audits/generations
        self._driver: Optional[webdriver.Chrome] = None

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

    def _get_driver(self) -> Optional[webdriver.Chrome]:
        """Lazy initialization of headless Chrome driver"""
        if self._driver is None:
            try:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--window-size=1280,720")
                self._driver = webdriver.Chrome(options=chrome_options)
                self._driver.set_page_load_timeout(30)
            except Exception as e:
                self.log(
                    f"Failed to initialize Chrome driver for visual audit: {e}", "error"
                )
        return self._driver

    def _quit_driver(self):
        """Properly shut down the driver"""
        if self._driver:
            try:
                self._driver.quit()
            except WebDriverException:
                pass  # Driver already closed or cleanup failed, continue anyway
            except Exception as e:
                self.log(f"Unexpected error closing driver: {e}", "error")
            self._driver = None

    def _take_screenshot(self, url: str) -> Optional[str]:
        """Capture website screenshot and return as base64 string"""
        driver = self._get_driver()
        if not driver:
            return None

        try:
            driver.get(url)
            time.sleep(3)  # Wait for rendering
            screenshot = driver.get_screenshot_as_base64()
            return screenshot
        except Exception as e:
            self.log(f"Failed to take screenshot: {e}", "error")
            return None

    def _run_visual_audit(
        self, business_name: str, base64_image: str, config: Dict
    ) -> Optional[Dict]:
        """Run visual audit using Ollama Vision model"""
        prompt = config.get("prompt", "").format(business_name=business_name)

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": config.get("model", "qwen3-vl:4b"),
                    "prompt": prompt,
                    "images": [base64_image],
                    "stream": False,
                    "format": "json",
                    "system": "You are a professional website visual auditor. Output ONLY valid JSON with 'visual_score' and 'observations'.",
                },
                timeout=60,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                if not raw or raw.strip() == "":
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse visual audit JSON: {e}", "error")
                    return None
            else:
                self.log(f"Visual audit API failed: {response.status_code}", "error")
        except Exception as e:
            self.log(f"Visual audit call failed: {e}", "error")
        return None

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity to match DB constraints ('critical', 'warning', 'info')"""
        s = str(severity).lower().strip()
        if s in ["critical", "high", "error", "fatal"]:
            return "critical"
        if s in ["warning", "medium", "warn"]:
            return "warning"
        return "info"

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
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
        self, url: str, business_name: str = "this business", bucket_name: Optional[str] = None
    ) -> Dict:
        """Audit website for technical and qualitative issues + Deep Discovery"""
        issues = []
        score = 100
        discovered_info = {
            "email": None,
            "social_links": {},
            "contact_form_url": None,
            "phone": None,
        }

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
                except requests.RequestException as e:
                    self.log(
                        f"Error fetching contact page {discovered_info['contact_form_url']}: {e}",
                        "error"
                    )
                    # Continue with what we already found
                except Exception as e:
                    self.log(f"Error parsing contact page: {e}", "error")
                    # Continue with what we already found

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
                severity = self._normalize_severity(check.get("severity", "info"))

                if check_type == "html_exists":
                    elem = soup.select_one(selector)
                    if not elem or (
                        check.get("min_length")
                        and len(elem.text.strip()) < check["min_length"]
                    ):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
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
                                "severity": severity,
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
                                    "severity": severity,
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
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "protocol_check":
                    if not url.startswith(check.get("protocol", "https://")):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

                elif check_type == "load_time":
                    if response.elapsed.total_seconds() > check.get("threshold", 3.0):
                        issues.append(
                            {
                                "type": check["id"],
                                "severity": severity,
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
                                "severity": severity,
                                "description": check["description"],
                            }
                        )
                        score -= check["score_impact"]

            # Qualitative LLM Audit (Stage B.1)
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
                                "severity": self._normalize_severity(obs.get("severity", "info")),
                                "description": f"LLM: {obs.get('description')}",
                            }
                        )

            # Visual LLM Audit (Stage B.2)
            visual_config = self.audit_settings.get("visual_audit", {})
            if self.ollama_enabled and visual_config.get("enabled"):
                self.log("  📸 Capturing screenshot for visual audit...", "info")
                base64_image = self._take_screenshot(url)
                if base64_image:
                    visual_result = self._run_visual_audit(
                        business_name, base64_image, visual_config
                    )
                    if visual_result:
                        vis_score = visual_result.get("visual_score", 100)
                        # Adjust main score based on visual score (weighted 20%)
                        score = (score * 0.8) + (vis_score * 0.2)

                        for obs in visual_result.get("observations", []):
                            issues.append(
                                {
                                    "type": f"visual_{obs.get('type', 'observation')}",
                                    "severity": self._normalize_severity(obs.get("severity", "info")),
                                    "description": f"Visual: {obs.get('description')}",
                                }
                            )
                        self.log(
                            f"  ✓ Visual audit complete (Score: {vis_score})", "success"
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
                    "model": config.get("model", "qwen3:4b"),
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a professional website quality auditor. Output ONLY valid JSON with 'qualitative_score' and 'observations'.",
                },
                timeout=30,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                if not raw or raw.strip() == "":
                    self.log("LLM audit returned an empty response", "error")
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse LLM audit JSON: {e}\nRaw: {raw}", "error")
                    return None
            else:
                self.log(f"LLM audit API failed with status {response.status_code}: {response.text}", "error")
        except Exception as e:
            self.log(f"LLM audit call failed: {e}", "error")
        return None

    def refine_email_ollama(self, subject: str, body: str, instructions: str) -> Dict:
        """Refine an existing email based on user instructions using Ollama"""
        if not self.ollama_enabled:
            return {"subject": subject, "body": body}

        prompt = f"""Refine this cold email based on the following instructions.

    Instructions: {instructions}

    Current Subject: {subject}
    Current Body:
    {body}

    Return ONLY JSON:
    {{
    "subject": "refined subject line",
    "body": "refined email body with proper line breaks"
    }}"""

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": "qwen3:4b",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "system": "You are a professional email editor. Output ONLY valid JSON. Preserve the signature if present, or add one if missing.",
                },
                timeout=60,
            )

            if response.status_code == 200:
                raw = response.json().get("response", "{}")
                try:
                    data = json.loads(raw)
                    return {
                        "subject": data.get("subject", subject),
                        "body": data.get("body", body),
                    }
                except json.JSONDecodeError as e:
                    self.log(f"Failed to parse email refinement JSON: {e}\nRaw response: {raw}", "error")
                    return {"subject": subject, "body": body}  # Return original, unchanged
                except Exception as e:
                    self.log(f"Error in email refinement parsing: {e}", "error")
                    return {"subject": subject, "body": body}
            else:
                self.log(f"Email refinement failed: {response.status_code}", "error")
        except Exception as e:
            self.log(f"Error refining email: {e}", "error")

        return {"subject": subject, "body": body}

    def generate_email_ollama(self, business_name: str, issues: List[Dict], bucket: str) -> Dict:
        """Generate email using Ollama LLM"""
        if not self.ollama_enabled:
            raise Exception(
                "Ollama is not enabled. Cannot generate email."
            )

        # Prioritize LLM issues and critical issues
        sorted_issues = sorted(
           issues,
           key=lambda x: (
               0 if x.get("type", "").startswith("llm_") else 1,
               0
               if x.get("severity") == "critical"
               else 1
               if x.get("severity") == "warning"
               else 2,
           ),
        )

        # Build prompt
        issue_summary = "\n".join([f"- {i['description']}" for i in sorted_issues[:6]])

        prompt = f"""Generate a professional cold email for {business_name}.

        Website Audit Findings:
        {issue_summary}

        Create a personalized outreach email that:
        1. Shows you've reviewed their website (mention 1-2 specific visual or technical details).
        2. Highlights 1-2 critical areas for improvement from the list above (especially visual updates, performance issues, bugs, or responsiveness).
        3. Briefly explains how these issues might be affecting their business (e.g., losing mobile customers, slow loading scaring users).
        4. Offers value and a soft call-to-action for a brief audit review call.
        5. Keeps it professional, under 150 words, and avoids being pushy.
        6. DO NOT include a signature or closing like "Best regards" - I will add that myself.

        Return ONLY JSON:
        {{
        "subject": "brief subject line",
        "body": "email body with proper line breaks"
        }}"""

        try:
           response = requests.post(
               f"{self.ollama_url}/api/generate",
               json={
                   "model": "qwen3:4b",
                   "prompt": prompt,
                   "stream": False,
                   "format": "json",
                   "system": "You are a professional email writer. Output ONLY valid JSON. Do not include signatures.",
               },
               timeout=60,
           )

           if response.status_code == 200:
               raw = response.json().get("response", "{}")
               if not raw or raw.strip() == "":
                   self.log("Email generation LLM returned an empty response", "error")
                   raise Exception("Empty response from LLM")
               
               try:
                   data = json.loads(raw)
                   body = data.get("body", "")
                   if not body:
                       self.log(f"LLM returned JSON without body: {raw}", "error")
                       raise Exception("Missing body in LLM response")

                   # Ensure the body doesn't already have a signature (safety check)
                   if "Best regards" in body or "Manas Doshi" in body:
                       # Simple cleanup if LLM ignored instruction
                       body = (
                           body.split("Best regards")[0].split("Sincerely")[0].strip()
                       )

                   # Append consistent signature
                   signature = "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services"
                   final_body = body.strip() + signature

                   return {
                       "subject": data.get(
                           "subject", f"Quick note about {business_name}"
                       ),
                       "body": final_body,
                   }
               except json.JSONDecodeError as e:
                   self.log(f"Failed to parse email JSON: {e}\nRaw: {raw}", "error")
                   raise
           else:
               self.log(f"Email generation API failed with status {response.status_code}: {response.text}", "error")
               raise Exception(f"API failed with status {response.status_code}")
        except Exception as e:
           self.log(f"Error generating email: {e}", "error")
           raise

    def audit_leads(self, limit: int = 20) -> Dict:
        """Audit pending leads with duration tracking"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Lead Auditing")
        self.log(f"{'=' * 60}")

        leads = self.repo.get_pending_audits(limit)
        self.log(f"Auditing {len(leads)} leads...", "info")

        audited = 0
        qualified = 0

        try:
            for i, lead in enumerate(leads, 1):
                self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                start_time = time.time()
                audit_result = self.audit_website(
                    lead["website"],
                    lead["business_name"],
                    lead.get("bucket") or "default",
                )
                duration = time.time() - start_time

                self.repo.save_audit(lead["id"], audit_result, duration=duration)

                # DEEP DISCOVERY: Update lead with newly found contact info
                if "discovered_info" in audit_result:
                    info = audit_result["discovered_info"]
                    self.repo.update_lead_contact_info(lead["id"], info)
                    if info.get("email"):
                        self.log(f"  ✉ Found email: {info['email']}", "success")
                    if info.get("social_links"):
                        self.log(
                            f"  🔗 Found {len(info['social_links'])} social links",
                            "success",
                        )

                audited += 1
                if audit_result["qualified"]:
                    qualified += 1
                    self.log(
                        f"  ✓ Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])}, Time: {duration:.1f}s)",
                        "success",
                    )
                else:
                    self.log(
                        f"  ✗ Not qualified (Score: {audit_result['score']}, Time: {duration:.1f}s)",
                        "error",
                    )

                time.sleep(1)
        finally:
            self._quit_driver()

        self.log(f"\n{'=' * 60}")
        self.log(
            f"Auditing Complete: {audited} audited, {qualified} qualified", "success"
        )
        self.log(f"{'=' * 60}\n")

        return {"audited": audited, "qualified": qualified}

    def generate_emails(self, limit: int = 20) -> Dict:
        """Generate emails for qualified leads with duration tracking"""
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

                start_time = time.time()
                email = self.generate_email_ollama(
                    lead["business_name"], issues, lead.get("bucket") or "default"
                )
                duration = time.time() - start_time

                self.repo.save_email(
                    lead["id"], email["subject"], email["body"], duration=duration
                )
                generated += 1
                self.log(f"  ✓ Email generated (Time: {duration:.1f}s)", "success")

            except Exception as e:
                self.log(f"  ✗ Error: {e}", "error")

            time.sleep(1)

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Generation Complete: {generated} emails created", "success")
        self.log(f"{'=' * 60}\n")

        return {"generated": generated}
