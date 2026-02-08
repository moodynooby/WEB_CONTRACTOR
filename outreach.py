"""Outreach Module: Lead Auditing + Email Generation (Stage B + Stage C)

Performance optimizations:
- ThreadPoolExecutor for parallel website auditing
- LRU cache for generate_email_ollama()
- HTTP session reuse
- Batch email generation with parallel LLM calls
- Thread-safe _audit_single_lead() method
- LLM rate limiting with cooldown between calls
"""

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple, TypeVar

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options

from lead_repository import LeadRepository

T = TypeVar("T")


class Outreach:
    """Consolidated Stage B (Auditing) + Stage C (Email Generation) with parallel processing"""

    def __init__(
        self,
        repo: Optional[LeadRepository] = None,
        logger: Optional[Callable] = None,
        max_workers: int = 5,
        llm_cooldown: float = 0.5,
    ):
        self.repo = repo or LeadRepository()
        self.ollama_url = "http://localhost:11434"
        self.logger = logger
        self.audit_settings = self._load_audit_settings()
        self.email_prompts = self._load_email_prompts()
        self.max_workers = max_workers
        self.llm_cooldown = llm_cooldown
        self._driver: Optional[webdriver.Chrome] = None

        # HTTP session for reuse - MUST be initialized before _test_ollama()
        self._session: Optional[requests.Session] = None

        # LLM rate limiting: lock ensures only one call at a time, last_call tracks cooldown
        self._llm_lock = threading.Lock()
        self._last_llm_call: float = 0.0

        # Test Ollama connection after _session is initialized
        self.ollama_enabled = self._test_ollama()

    def _load_audit_settings(self) -> Dict:
        """Load audit settings from config file"""
        try:
            with open("config/audit_settings.json", "r") as f:
                return json.load(f)
        except Exception:
            return {
                "technical_checks": [],
                "llm_audit": {"enabled": False},
                "visual_audit": {"enabled": False},
            }

    def _load_email_prompts(self) -> Dict:
        """Load email prompts from config file"""
        try:
            with open("config/email_prompts.json", "r") as f:
                return json.load(f)
        except Exception:
            return {
                "cold_email": {"system_message": "", "prompt_template": ""},
                "email_signature": {},
            }

    def log(self, message: str, style: str = "") -> None:
        """Log message to provided logger or print"""
        if self.logger:
            self.logger(message, style)
        else:
            print(message)

    def _get_session(self) -> requests.Session:
        """Get or create reusable HTTP session"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
        return self._session

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

    def _quit_driver(self) -> None:
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
        """Run visual audit using Ollama Vision model with retry logic for 500 errors.

        This method is wrapped with cooldown to prevent overwhelming the API.
        """

        def _do_visual_audit() -> Optional[Dict]:
            prompt = config.get("prompt", "").format(business_name=business_name)

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    response = self._get_session().post(
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": config.get(
                                "model", "richardyoung/smolvlm2-2.2b-instruct"
                            ),
                            "prompt": prompt,
                            "images": [base64_image],
                            "stream": False,
                            "format": "json",
                            "system": system_message,
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
                    elif response.status_code == 500:
                        # Server error - might be resource limit or temporary issue
                        if attempt < max_retries - 1:
                            delay = base_delay * (2**attempt)
                            self.log(
                                f"Visual audit API returned 500 (attempt {attempt + 1}/{max_retries}). "
                                f"Retrying in {delay:.1f}s...",
                                "error",
                            )
                            time.sleep(delay)
                            continue
                        else:
                            self.log(
                                f"Visual audit API failed with 500 after {max_retries} attempts. "
                                "This may be due to resource limits or server overload.",
                                "error",
                            )
                    else:
                        self.log(
                            f"Visual audit API failed: {response.status_code}", "error"
                        )
                        # Don't retry on non-500 errors
                        break
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        self.log(
                            f"Visual audit timeout (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay:.1f}s...",
                            "error",
                        )
                        time.sleep(delay)
                    else:
                        self.log(
                            "Visual audit timed out after all retry attempts", "error"
                        )
                except Exception as e:
                    self.log(f"Visual audit call failed: {e}", "error")
                    break
            return None

        return self._llm_call_with_cooldown(_do_visual_audit)

    def _normalize_severity(self, severity: str) -> str:
        """Normalize severity to match DB constraints ('critical', 'warning', 'info')"""
        s = str(severity).lower().strip()
        if s in ["critical", "high", "error", "fatal"]:
            return "critical"
        if s in ["warning", "medium", "warn"]:
            return "warning"
        return "info"

    def _llm_call_with_cooldown(self, call_fn: Callable[[], T]) -> T:
        """Execute an LLM call with cooldown to prevent overwhelming the API.

        This method ensures:
        1. Only one LLM call happens at a time (thread-safe)
        2. A cooldown period between calls to avoid rate limiting
        """
        with self._llm_lock:
            # Calculate time since last call
            elapsed = time.time() - self._last_llm_call
            if elapsed < self.llm_cooldown:
                sleep_time = self.llm_cooldown - elapsed
                self.log(f"  LLM cooldown: waiting {sleep_time:.1f}s...", "info")
                time.sleep(sleep_time)

            try:
                result = call_fn()
                return result
            finally:
                self._last_llm_call = time.time()

    def _test_ollama(self) -> bool:
        """Test Ollama connection"""
        try:
            response = self._get_session().get(f"{self.ollama_url}/api/tags", timeout=5)
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
        self,
        url: str,
        business_name: str = "this business",
        bucket_name: Optional[str] = None,
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
            response = self._get_session().get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.content, "html.parser")

            # DEEP DISCOVERY: Find contact info
            discovered_info = self.deep_discovery(soup, url)

            # If no email yet, try crawling contact page if found
            if not discovered_info["email"] and discovered_info["contact_form_url"]:
                try:
                    c_resp = self._get_session().get(
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
                        "error",
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

                elif check_type == "text_match":
                    patterns = check.get("patterns", [])
                    text = soup.get_text().lower()
                    found = any(p.lower() in text for p in patterns)
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
            qual_score = 100
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
                    for obs in llm_result.get("observations", []):
                        issues.append(
                            {
                                "type": f"llm_{obs.get('type', 'observation')}",
                                "severity": self._normalize_severity(
                                    obs.get("severity", "info")
                                ),
                                "description": f"LLM: {obs.get('description')}",
                            }
                        )

            # Visual LLM Audit (Stage B.2)
            visual_config = self.audit_settings.get("visual_audit", {})
            vis_score = 100
            if self.ollama_enabled and visual_config.get("enabled"):
                self.log("  Capturing screenshot for visual audit...", "info")
                base64_image = self._take_screenshot(url)
                if base64_image:
                    visual_result = self._run_visual_audit(
                        business_name, base64_image, visual_config
                    )
                    if visual_result:
                        vis_score = visual_result.get("visual_score", 100)
                        for obs in visual_result.get("observations", []):
                            issues.append(
                                {
                                    "type": f"visual_{obs.get('type', 'observation')}",
                                    "severity": self._normalize_severity(
                                        obs.get("severity", "info")
                                    ),
                                    "description": f"Visual: {obs.get('description')}",
                                }
                            )
                        self.log(
                            f"  Visual audit complete (Score: {vis_score})", "success"
                        )

            # Unified Weighted Scoring
            weights = self.audit_settings.get(
                "scoring_weights",
                {"technical_score": 0.35, "content_score": 0.35, "visual_score": 0.30},
            )

            # Technical score is the base 'score' calculated from manual checks
            tech_score = max(0, score)

            final_score = (
                (tech_score * weights.get("technical_score", 0.35))
                + (qual_score * weights.get("content_score", 0.35))
                + (vis_score * weights.get("visual_score", 0.30))
            )
            score = final_score

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

        # Formalized Qualification Logic (Imperfect Site Targeting)
        rules = self.audit_settings.get("qualification_rules", {})
        target_min = rules.get("target_score_min", 40)
        target_max = rules.get("target_score_max", 84)
        min_issues = rules.get("min_issues_required", 2)

        qualified = (
            score >= target_min
            and score <= target_max
            and len([i for i in issues if i["severity"] in ["warning", "critical"]])
            >= min_issues
        )

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
        """Run qualitative audit using Ollama with retry logic for 500 errors.

        This method is wrapped with cooldown to prevent overwhelming the API.
        """

        def _do_llm_audit() -> Optional[Dict]:
            prompt_template = config.get("prompt_template", "")
            system_message = config.get(
                "system_message",
                "You are a professional website quality auditor. Output ONLY valid JSON.",
            )
            prompt = prompt_template.format(
                business_name=business_name, content=content
            )

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    response = self._get_session().post(
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": config.get("model", "qwen3:1.7b"),
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                            "system": system_message,
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
                            self.log(
                                f"Failed to parse LLM audit JSON: {e}\nRaw: {raw}",
                                "error",
                            )
                            return None
                    elif response.status_code == 500:
                        # Server error - might be resource limit or temporary issue
                        if attempt < max_retries - 1:
                            delay = base_delay * (2**attempt)
                            self.log(
                                f"LLM audit API returned 500 (attempt {attempt + 1}/{max_retries}). "
                                f"Retrying in {delay:.1f}s...",
                                "error",
                            )
                            time.sleep(delay)
                            continue
                        else:
                            self.log(
                                f"LLM audit API failed with 500 after {max_retries} attempts. "
                                "This may be due to resource limits or server overload.",
                                "error",
                            )
                    else:
                        self.log(
                            f"LLM audit API failed with status {response.status_code}: {response.text}",
                            "error",
                        )
                        # Don't retry on non-500 errors
                        break
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        self.log(
                            f"LLM audit timeout (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay:.1f}s...",
                            "error",
                        )
                        time.sleep(delay)
                    else:
                        self.log(
                            "LLM audit timed out after all retry attempts", "error"
                        )
                except Exception as e:
                    self.log(f"LLM audit call failed: {e}", "error")
                    break
            return None

        return self._llm_call_with_cooldown(_do_llm_audit)

    def refine_email_ollama(self, subject: str, body: str, instructions: str) -> Dict:
        """Refine an existing email based on user instructions using Ollama with retry logic.

        This method is wrapped with cooldown to prevent overwhelming the API.
        """
        if not self.ollama_enabled:
            return {"subject": subject, "body": body}

        def _do_refinement() -> Dict:
            prompt = f"""Refine this cold email based on instructions.

Instructions: {instructions}

Current Subject: {subject}
Current Body:
{body}

Return ONLY JSON:
{{
"subject": "refined subject line",
"body": "refined email body with proper line breaks"
}}"""

            max_retries = 3
            base_delay = 2.0

            for attempt in range(max_retries):
                try:
                    response = self._get_session().post(
                        f"{self.ollama_url}/api/generate",
                        json={
                            "model": "qwen3:1.7b",
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
                            self.log(
                                f"Failed to parse email refinement JSON: {e}\nRaw response: {raw}",
                                "error",
                            )
                            return {
                                "subject": subject,
                                "body": body,
                            }  # Return original, unchanged
                        except Exception as e:
                            self.log(f"Error in email refinement parsing: {e}", "error")
                            return {"subject": subject, "body": body}
                    elif response.status_code == 500:
                        # Server error - might be resource limit or temporary issue
                        if attempt < max_retries - 1:
                            delay = base_delay * (2**attempt)
                            self.log(
                                f"Email refinement API returned 500 (attempt {attempt + 1}/{max_retries}). "
                                f"Retrying in {delay:.1f}s...",
                                "error",
                            )
                            time.sleep(delay)
                            continue
                        else:
                            self.log(
                                f"Email refinement API failed with 500 after {max_retries} attempts. "
                                "This may be due to resource limits or server overload.",
                                "error",
                            )
                    else:
                        self.log(
                            f"Email refinement failed: {response.status_code}", "error"
                        )
                        break
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        self.log(
                            f"Email refinement timeout (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay:.1f}s...",
                            "error",
                        )
                        time.sleep(delay)
                    else:
                        self.log(
                            "Email refinement timed out after all retry attempts",
                            "error",
                        )
                except Exception as e:
                    self.log(f"Error refining email: {e}", "error")
                    break

            return {"subject": subject, "body": body}

        return self._llm_call_with_cooldown(_do_refinement)

    def _generate_email_uncached(
        self, business_name: str, issues_key: str, bucket: str
    ) -> Dict:
        """Uncached email generation with retry logic - wrapped by cooldown in public method."""
        if not self.ollama_enabled:
            raise Exception("Ollama is not enabled. Cannot generate email.")

        # Parse issues from key
        issues = json.loads(issues_key)

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

        prompt_template = self.email_prompts.get("cold_email", {}).get(
            "prompt_template", ""
        )
        system_message = self.email_prompts.get("cold_email", {}).get(
            "system_message",
            "You are a professional email writer. Output ONLY valid JSON. Do not include signatures.",
        )
        prompt = prompt_template.format(
            business_name=business_name, issue_summary=issue_summary
        )

        for attempt in range(max_retries):
            try:
                response = self._get_session().post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": "qwen3:1.7b",
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                        "system": system_message,
                    },
                    timeout=60,
                )

                if response.status_code == 200:
                    raw = response.json().get("response", "{}")
                    if not raw or raw.strip() == "":
                        raise Exception("Empty response from LLM")

                    try:
                        data = json.loads(raw)
                        body = data.get("body", "")
                        if not body:
                            raise Exception("Missing body in LLM response")

                        # Ensure the body doesn't already have a signature (safety check)
                        if "Best regards" in body or "Manas Doshi" in body:
                            # Simple cleanup if LLM ignored instruction
                            body = (
                                body.split("Best regards")[0]
                                .split("Sincerely")[0]
                                .strip()
                            )

                        # Append signature from email_prompts config
                        signature = self.email_prompts.get("email_signature", {}).get(
                            "template",
                            "\n\nBest regards,\nManas Doshi,\nFuture Forwards - https://man27.netlify.app/services",
                        )
                        if "{name}" in signature or "{company}" in signature:
                            signature = signature.format(
                                name=self.email_prompts.get("email_signature", {}).get(
                                    "name", "Manas Doshi"
                                ),
                                company=self.email_prompts.get(
                                    "email_signature", {}
                                ).get("company", "Future Forwards"),
                                website=self.email_prompts.get(
                                    "email_signature", {}
                                ).get("website", "https://man27.netlify.app/services"),
                            )
                        final_body = body.strip() + signature

                        return {
                            "subject": data.get(
                                "subject", f"Quick note about {business_name}"
                            ),
                            "body": final_body,
                        }
                    except json.JSONDecodeError as e:
                        self.log(
                            f"Failed to parse email JSON: {e}\nRaw: {raw}", "error"
                        )
                        raise
                elif response.status_code == 500:
                    # Server error - might be resource limit or temporary issue
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        self.log(
                            f"Email generation API returned 500 (attempt {attempt + 1}/{max_retries}). "
                            f"Retrying in {delay:.1f}s...",
                            "error",
                        )
                        time.sleep(delay)
                        continue
                    else:
                        self.log(
                            f"Email generation API failed with 500 after {max_retries} attempts. "
                            "This may be due to resource limits or server overload.",
                            "error",
                        )
                        raise Exception("API failed with status 500 after retries")
                else:
                    self.log(
                        f"Email generation API failed with status {response.status_code}: {response.text}",
                        "error",
                    )
                    raise Exception(f"API failed with status {response.status_code}")
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    self.log(
                        f"Email generation timeout (attempt {attempt + 1}/{max_retries}). "
                        f"Retrying in {delay:.1f}s...",
                        "error",
                    )
                    time.sleep(delay)
                else:
                    self.log(
                        "Email generation timed out after all retry attempts", "error"
                    )
                    raise Exception("API timeout after retries")
            except Exception as e:
                self.log(f"Error generating email: {e}", "error")
                raise

    def generate_email_ollama(
        self, business_name: str, issues: List[Dict], bucket: str
    ) -> Dict:
        """Generate email using Ollama LLM with LRU caching and cooldown.

        This method applies a cooldown between API calls to prevent overwhelming
        the LLM service. Cached results are returned immediately without cooldown.
        """
        # Create a cacheable key from issues
        issues_key = json.dumps(issues, sort_keys=True)

        # Use a simple cache dict on the instance
        cache_key = (business_name, issues_key, bucket)
        if not hasattr(self, "_email_cache"):
            self._email_cache: Dict[Tuple[str, str, str], Dict] = {}

        if cache_key in self._email_cache:
            return self._email_cache[cache_key]

        # Not in cache - apply cooldown and make API call
        def _do_generate() -> Dict:
            return self._generate_email_uncached(business_name, issues_key, bucket)

        result = self._llm_call_with_cooldown(_do_generate)

        # Store in cache (limit size to prevent memory growth)
        if len(self._email_cache) >= 128:
            # Clear oldest entries (simple approach)
            self._email_cache.clear()
        self._email_cache[cache_key] = result

        return result

    def _audit_single_lead(self, lead: Dict) -> Tuple[int, Dict, float]:
        """Thread-safe method to audit a single lead"""
        start_time = time.time()

        try:
            audit_result = self.audit_website(
                lead["website"],
                lead["business_name"],
                lead.get("bucket") or "default",
            )
            duration = time.time() - start_time

            return lead["id"], audit_result, duration
        except Exception as e:
            duration = time.time() - start_time
            error_result = {
                "url": lead.get("website", ""),
                "score": 0,
                "issues": [
                    {"type": "error", "severity": "critical", "description": str(e)}
                ],
                "qualified": 0,
                "discovered_info": {},
            }
            return lead["id"], error_result, duration

    def audit_leads(
        self,
        limit: int = 20,
        parallel: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Audit pending leads with duration tracking and parallel processing"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Lead Auditing")
        self.log(f"{'=' * 60}")

        leads = self.repo.get_pending_audits(limit)
        self.log(f"Auditing {len(leads)} leads...", "info")

        audited = 0
        qualified = 0
        audit_batch = []

        try:
            if parallel and len(leads) > 1:
                # Parallel auditing
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {
                        executor.submit(self._audit_single_lead, lead): lead
                        for lead in leads
                    }

                    for i, future in enumerate(as_completed(futures), 1):
                        lead = futures[future]
                        lead_id, audit_result, duration = future.result()

                        # Update contact info
                        if "discovered_info" in audit_result:
                            info = audit_result["discovered_info"]
                            self.repo.update_lead_contact_info(lead_id, info)

                        # Queue for batch save
                        audit_batch.append(
                            {
                                "lead_id": lead_id,
                                "data": audit_result,
                                "duration": duration,
                            }
                        )

                        audited += 1
                        if audit_result["qualified"]:
                            qualified += 1

                        if progress_callback:
                            progress_callback(i, len(leads), lead["business_name"])

                        self.log(
                            f"[{i}/{len(leads)}] {lead['business_name']} - "
                            f"Score: {audit_result['score']}, Qualified: {bool(audit_result['qualified'])}",
                            "success" if audit_result["qualified"] else "info",
                        )
            else:
                # Sequential auditing
                for i, lead in enumerate(leads, 1):
                    self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                    lead_id, audit_result, duration = self._audit_single_lead(lead)

                    # Update contact info
                    if "discovered_info" in audit_result:
                        info = audit_result["discovered_info"]
                        self.repo.update_lead_contact_info(lead_id, info)
                        if info.get("email"):
                            self.log(f"  Found email: {info['email']}", "success")
                        if info.get("social_links"):
                            self.log(
                                f"  Found {len(info['social_links'])} social links",
                                "success",
                            )

                    # Queue for batch save
                    audit_batch.append(
                        {
                            "lead_id": lead_id,
                            "data": audit_result,
                            "duration": duration,
                        }
                    )

                    audited += 1
                    if audit_result["qualified"]:
                        qualified += 1
                        self.log(
                            f"  Qualified (Score: {audit_result['score']}, Issues: {len(audit_result['issues'])}, Time: {duration:.1f}s)",
                            "success",
                        )
                    else:
                        self.log(
                            f"  Not qualified (Score: {audit_result['score']}, Time: {duration:.1f}s)",
                            "error",
                        )

            # Batch save all audits
            if audit_batch:
                self.repo.save_audits_batch(audit_batch)

        finally:
            self._quit_driver()

        self.log(f"\n{'=' * 60}")
        self.log(
            f"Auditing Complete: {audited} audited, {qualified} qualified", "success"
        )
        self.log(f"{'=' * 60}\n")

        return {"audited": audited, "qualified": qualified}

    def _generate_single_email(self, lead: Dict) -> Optional[Dict]:
        """Generate email for a single lead"""
        try:
            issues = json.loads(lead.get("issues_json", "[]"))

            start_time = time.time()
            email = self.generate_email_ollama(
                lead["business_name"], issues, lead.get("bucket") or "default"
            )
            duration = time.time() - start_time

            return {
                "lead_id": lead["id"],
                "subject": email["subject"],
                "body": email["body"],
                "status": "needs_review",
                "duration": duration,
            }
        except Exception as e:
            self.log(
                f"  Error generating email for {lead['business_name']}: {e}", "error"
            )
            return None

    def generate_emails(
        self,
        limit: int = 20,
        parallel: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> Dict:
        """Generate emails for qualified leads with duration tracking and parallel processing"""
        self.log(f"\n{'=' * 60}")
        self.log("OUTREACH: Email Generation")
        self.log(f"{'=' * 60}")

        leads = self.repo.get_qualified_leads(limit)
        self.log(f"Generating emails for {len(leads)} qualified leads...", "info")

        generated = 0
        email_batch = []

        if parallel and len(leads) > 1:
            # Parallel email generation
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._generate_single_email, lead): lead
                    for lead in leads
                }

                for i, future in enumerate(as_completed(futures), 1):
                    lead = futures[future]
                    result = future.result()

                    if result:
                        email_batch.append(result)
                        generated += 1

                    if progress_callback:
                        progress_callback(i, len(leads), lead["business_name"])

                    self.log(
                        f"[{i}/{len(leads)}] {lead['business_name']} - "
                        f"{'Generated' if result else 'Failed'}",
                        "success" if result else "error",
                    )
        else:
            # Sequential email generation
            for i, lead in enumerate(leads, 1):
                self.log(f"\n[{i}/{len(leads)}] {lead['business_name']}", "info")

                result = self._generate_single_email(lead)
                if result:
                    email_batch.append(result)
                    generated += 1
                    self.log(
                        f"  Email generated (Time: {result['duration']:.1f}s)",
                        "success",
                    )

        # Batch save all emails
        if email_batch:
            self.repo.save_emails_batch(email_batch)

        self.log(f"\n{'=' * 60}")
        self.log(f"Email Generation Complete: {generated} emails created", "success")
        self.log(f"{'=' * 60}\n")

        return {"generated": generated}
