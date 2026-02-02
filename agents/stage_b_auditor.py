"""
Stage B: "Needs Update" Auditor Engine
Technical website analysis for lead qualification and issue identification
"""

import requests
import json
import time
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from datetime import datetime

@dataclass
class WebsiteIssue:
    """Represents a website issue found during audit"""
    issue_type: str
    severity: str  # 'critical', 'high', 'medium', 'low'
    description: str
    recommendation: str
    affected_pages: List[str]
    impact_score: float  # 0.0 to 1.0

@dataclass
class AuditResult:
    """Complete audit result for a website"""
    lead_id: int
    business_name: str
    website: str
    overall_score: float
    issues: List[WebsiteIssue]
    technical_metrics: Dict
    qualification_status: bool
    audit_timestamp: datetime
    llm_analysis: Optional[Dict] = None

class OllamaAuditor:
    """LLM-based technical critique and hook generator"""
    
    def __init__(self):
        import os
        from dotenv import load_dotenv
        load_dotenv()
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        self.model_name = os.getenv('OLLAMA_MODEL', 'llama3.2')
        self.enabled = self._test_connection()

    def _test_connection(self) -> bool:
        """Test connection to Ollama"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                print(f"✅ Auditor connected to Ollama at {self.ollama_url}")
                tags = response.json().get('models', [])
                model_names = [m.get('name', '') for m in tags]
                if self.model_name not in model_names and self.model_name != 'llama3.2':
                    print(f"⚠️  Warning: Model {self.model_name} not found in Ollama tags. Available: {model_names}")
                return True
            print(f"❌ Ollama connection test failed with status: {response.status_code}")
            return False
        except Exception as e:
            print(f"❌ Ollama connection error: {e}")
            return False

    def analyze_website(self, business_name: str, metrics: Dict, soup: BeautifulSoup) -> Dict:
        """Get LLM-based qualitative analysis and outreach hooks"""
        if not self.enabled:
            return {"error": "Ollama not available"}

        # Extract context
        title = soup.find('title').text.strip() if soup.find('title') else "N/A"
        headings = [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3'])[:8]]
        
        # Get snippet of body text for tone/messaging check
        body_text = " ".join([p.text.strip() for p in soup.find_all('p')[:3]])
        if len(body_text) > 500:
            body_text = body_text[:500] + "..."

        prompt = f"""Analyze this website and return ONLY a JSON object. No preamble, no "Sure", no explanation.

BUSINESS: {business_name}
WEBSITE TITLE: {title}
TOP HEADINGS: {headings}
SAMPLE CONTENT: {body_text}
TECHNICAL METRICS:
- Response Time: {metrics.get('response_time', 'N/A')}s
- Mobile Ready: {metrics.get('has_viewport', 'N/A')}
- Google Analytics: {metrics.get('has_google_analytics', 'N/A')}
- Page Title: {metrics.get('page_title', 'N/A')}

TASK:
1. Provide a specific technical/UX critique.
2. Identify the 'Business Impact' of these issues.
3. Generate 3 unique 'Personalized Hooks'.
4. Identify any "Dynamic Issues" (UX, marketing, trust).
5. Provide a "Score Adjustment" [-0.3, +0.1].

JSON FORMAT (STRICT):
{{
  "critique": "...",
  "business_impact": "...",
  "hooks": ["...", "...", "..."],
  "dynamic_issues": [
    {{"issue_type": "ux_design", "description": "...", "severity": "medium", "impact_score": 0.4}}
  ],
  "score_adjustment": -0.1
}}"""

        try:
            response = requests.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "system": "You are a technical SEO and UX auditor. You output ONLY valid JSON. No conversational filler."
            }, timeout=300)
            
            if response.status_code == 200:
                raw_response = response.json().get('response', '{}')
                
                try:
                    return json.loads(raw_response)
                except json.JSONDecodeError:
                    start = raw_response.find('{')
                    end = raw_response.rfind('}') + 1
                    if start != -1 and end != 0:
                        try:
                            return json.loads(raw_response[start:end])
                        except:
                            pass
                    print(f"❌ Failed to parse JSON from Ollama for {business_name}")
                    return {"error": "Invalid JSON response from Ollama"}
            
            print(f"❌ Ollama API error ({response.status_code}) for {business_name}")
            return {"error": f"Ollama error: {response.status_code}"}
        except Exception as e:
            print(f"❌ Ollama Exception during analysis: {str(e)}")
            return {"error": str(e)}

class TechnicalAuditor:
    """Core technical auditing engine"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        })
        
        # Initialize LLM Auditor
        self.llm_auditor = OllamaAuditor()
        
        # Selenium driver (lazy loaded)
        self.driver = None
        
    
        # Issue detection patterns
        self.issue_patterns = {
            'slow_loading': {
                'pattern': lambda response: response.elapsed.total_seconds() > 5.0,
                'severity': 'medium',
                'description': 'Website loading slowly (>5 seconds)',
                'recommendation': 'Optimize images, enable caching, use CDN',
                'impact_score': 0.5
            },
            'mobile_unfriendly': {
                'pattern': lambda soup: not soup.find('meta', attrs={'name': 'viewport'}),
                'severity': 'high',
                'description': 'Not optimized for mobile devices',
                'recommendation': 'Add responsive design and mobile viewport',
                'impact_score': 0.8
            },
            'missing_meta': {
                'pattern': lambda soup: not soup.find('meta', attrs={'name': 'description'}),
                'severity': 'medium',
                'description': 'Missing meta description for SEO',
                'recommendation': 'Add meta description to improve search visibility',
                'impact_score': 0.4
            },
            'old_technology': {
                'pattern': lambda soup: bool(soup.find(string=re.compile(r'WordPress\s*[0-4]\.|Joomla\s*1\.|Drupal\s*[6-7]\.'))),
                'severity': 'medium',
                'description': 'Using outdated CMS version',
                'recommendation': 'Update CMS to latest version',
                'impact_score': 0.6
            },
            'broken_links': {
                'pattern': lambda links: len([l for l in links if l.get('status_code', 200) >= 400]) > 0,
                'severity': 'medium',
                'description': 'Broken internal/external links found',
                'recommendation': 'Fix or remove broken links',
                'impact_score': 0.3
            },
            'no_contact_info': {
                'pattern': lambda soup: not any([
                    soup.find('a', href=re.compile(r'tel:|mailto:', re.I)),
                    soup.find(text=re.compile(r'phone|email|contact', re.I))
                ]),
                'severity': 'high',
                'description': 'No clear contact information visible',
                'recommendation': 'Add prominent contact details',
                'impact_score': 0.7
            },
            'poor_navigation': {
                'pattern': lambda soup: len(soup.find_all('nav')) == 0,
                'severity': 'medium',
                'description': 'Poor or missing navigation structure',
                'recommendation': 'Implement clear navigation menu',
                'impact_score': 0.5
            },
            'no_social_proof': {
                'pattern': lambda soup: not any([
                    soup.find('a', href=re.compile(r'facebook|twitter|instagram|linkedin', re.I)),
                    soup.find('div', class_=re.compile(r'testimonial|review', re.I))
                ]),
                'severity': 'low',
                'description': 'Missing social proof elements',
                'recommendation': 'Add testimonials, reviews, or social media links',
                'impact_score': 0.2
            },
            'accessibility_issues': {
                'pattern': lambda soup: not any([
                    soup.find('img', alt=True),
                    soup.find('h1'),
                    soup.find('main')
                ]),
                'severity': 'medium',
                'description': 'Basic accessibility issues detected',
                'recommendation': 'Add alt text, proper heading structure, semantic HTML',
                'impact_score': 0.4
            }
        }
    
    def _init_driver(self):
        """Initialize the Selenium WebDriver for fallback fetching"""
        if self.driver:
            return
            
        from core.selenium_utils import SeleniumDriverFactory
        self.driver = SeleniumDriverFactory.create_driver(headless=True)

    def _fetch_with_selenium(self, url: str) -> Optional[requests.Response]:
        """Fetch a website using Selenium as a fallback"""
        print(f"🔄 Using Selenium fallback for: {url}")
        self._init_driver()
        
        if not self.driver:
            return None
            
        try:
            self.driver.get(url)
            time.sleep(3) # Wait for JS execution
            
            # Create a mock response object that requests-based code expects
            # We only need content and status_code for now
            from requests.models import Response
            from datetime import timedelta
            
            mock_response = Response()
            mock_response.status_code = 200 # Assume 200 if we got content via Selenium
            mock_response._content = self.driver.page_source.encode('utf-8')
            mock_response.url = self.driver.current_url
            mock_response.encoding = 'utf-8'
            mock_response.elapsed = timedelta(seconds=3) # Approximate
            
            return mock_response
        except Exception as e:
            print(f"❌ Selenium fetch failed: {e}")
            return None

    def close(self):
        """Clean up resources"""
        from core.selenium_utils import SeleniumDriverFactory
        SeleniumDriverFactory.safe_close(self.driver)
        self.driver = None

    def audit_website(self, url: str, lead_id: int, business_name: str) -> AuditResult:
        """Perform comprehensive website audit"""
        print(f"Auditing: {business_name} - {url}")
        
        issues = []
        technical_metrics = {}
        overall_score = 1.0
        llm_analysis = None
        
        try:
            # Normalize URL
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            # Test HTTP and HTTPS
            http_response, https_response = self._test_protocols(url)
            
            # Get main content (prefer HTTPS if available)
            main_response = https_response if (https_response and https_response.status_code < 400) else http_response
            
            # If still no valid response or we got a block code, try Selenium
            if not main_response or (main_response and main_response.status_code in [403, 401]):
                main_response = self._fetch_with_selenium(url)
                
            if not main_response:
                raise Exception("Could not fetch website (even with Selenium fallback)")
            
            # Parse HTML
            soup = BeautifulSoup(main_response.content, 'html.parser')
            
            # Collect technical metrics
            technical_metrics = self._collect_technical_metrics(main_response, soup)
            
            # Detect issues
            issues = self._detect_issues(url, main_response, soup)
            
            # Calculate base technical score
            overall_score = self._calculate_overall_score(issues, technical_metrics)
            
            # Perform LLM analysis
            llm_analysis = self.llm_auditor.analyze_website(business_name, technical_metrics, soup)
            
            # Incorporate LLM results
            if llm_analysis and "error" not in llm_analysis:
                # Add dynamic issues from LLM
                for issue_data in llm_analysis.get('dynamic_issues', []):
                    issues.append(WebsiteIssue(
                        issue_type=issue_data.get('issue_type', 'llm_observation'),
                        severity=issue_data.get('severity', 'medium'),
                        description=issue_data.get('description', ''),
                        recommendation="Review and improve based on UX/Marketing best practices",
                        affected_pages=[url],
                        impact_score=issue_data.get('impact_score', 0.3)
                    ))
                
                # Apply score adjustment
                score_adj = llm_analysis.get('score_adjustment', 0.0)
                overall_score = max(0.0, min(1.0, overall_score + score_adj))
            elif llm_analysis and "error" in llm_analysis:
                print(f"⚠️  Skipping dynamic analysis for {business_name}: {llm_analysis['error']}")
            
            # Determine qualification based on final score and issues
            qualification_status = self._determine_qualification(overall_score, issues)
            
            # Estimate fix cost

        except Exception as e:
            print(f"Error auditing {url}: {e}")
            issues.append(WebsiteIssue(
                issue_type='audit_error',
                severity='critical',
                description=f'Could not audit website: {str(e)}',
                recommendation='Website may be down or inaccessible',
                affected_pages=[url],
                impact_score=1.0
            ))
            overall_score = 0.0
            qualification_status = False
        
        return AuditResult(
            lead_id=lead_id,
            business_name=business_name,
            website=url,
            overall_score=overall_score,
            issues=issues,
            technical_metrics=technical_metrics,
            qualification_status=qualification_status,
            audit_timestamp=datetime.now(),
            llm_analysis=llm_analysis
        )
    
    def _test_protocols(self, url: str) -> Tuple[Optional[requests.Response], Optional[requests.Response]]:
        """Test both HTTP and HTTPS protocols"""
        http_response = None
        https_response = None
        
        # Test HTTP
        try:
            http_url = url.replace('https://', 'http://')
            http_response = self.session.get(http_url, timeout=10, allow_redirects=True)
        except:
            pass
        
        # Test HTTPS
        try:
            https_url = url.replace('http://', 'https://')
            # First try with verification
            try:
                https_response = self.session.get(https_url, timeout=10, allow_redirects=True, verify=True)
            except requests.exceptions.SSLError:
                # Fallback to no verification only if explicitly needed, but log a warning
                # For now, let's keep it strict or allow a retry with verify=False if we want to be permissive
                # Given user feedback, Marriott is not SSL insecure, so we should trust verify=True
                https_response = self.session.get(https_url, timeout=10, allow_redirects=True, verify=False)
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception as e:
            print(f"Error testing protocols for {url}: {e}")
        
        return http_response, https_response
    
    def _collect_technical_metrics(self, response: requests.Response, soup: BeautifulSoup) -> Dict:
        """Collect technical metrics about the website"""
        metrics = {
            'response_time': response.elapsed.total_seconds(),
            'status_code': response.status_code,
            'content_size': len(response.content),
            'redirects': len(response.history),
            'server': response.headers.get('Server', 'Unknown'),
            'content_type': response.headers.get('Content-Type', 'Unknown'),
            'has_viewport': bool(soup.find('meta', attrs={'name': 'viewport'})),
            'has_meta_description': bool(soup.find('meta', attrs={'name': 'description'})),
            'has_favicon': bool(soup.find('link', rel=re.compile(r'icon', re.I))),
            'image_count': len(soup.find_all('img')),
            'link_count': len(soup.find_all('a')),
            'has_forms': bool(soup.find('form')),
            'uses_bootstrap': bool(soup.find(class_=re.compile(r'bootstrap', re.I))),
            'uses_jquery': bool(soup.find(src=re.compile(r'jquery', re.I))),
            'has_google_analytics': bool(soup.find(src=re.compile(r'google-analytics|gtag', re.I))),
            'has_facebook_pixel': bool(soup.find(src=re.compile(r'facebook\.com/tr', re.I))),
            'page_title': soup.find('title').text.strip() if soup.find('title') else '',
            'h1_count': len(soup.find_all('h1')),
            'has_navigation': bool(soup.find('nav')),
            'discovered_email': self._extract_email_from_soup(soup)
        }
        
        return metrics
    
    def _extract_email_from_soup(self, soup: BeautifulSoup) -> str:
        """Extract email address from soup using mailto links and regex"""
        # 1. Check mailto links
        mailto_links = soup.select('a[href^="mailto:"]')
        for link in mailto_links:
            email = link['href'].replace('mailto:', '').split('?')[0].strip()
            if email and '@' in email:
                return email
                
        # 2. Regex search in text
        email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        text = soup.get_text()
        matches = re.findall(email_regex, text)
        if matches:
            # Filter common false positives
            for email in matches:
                if not any(ext in email.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg']):
                    return email
                    
        return ''
    
    def _detect_issues(self, url: str, response: requests.Response, soup: BeautifulSoup) -> List[WebsiteIssue]:
        """Detect website issues using predefined patterns"""
        issues = []
        
        # Check internal links for broken links (sample check)
        sample_links = soup.find_all('a', href=True)[:10]  # Check first 10 links
        link_statuses = []
        
        for link in sample_links:
            href = link['href']
            if href.startswith('http'):
                try:
                    link_response = self.session.head(href, timeout=5, allow_redirects=True)
                    link_statuses.append({'url': href, 'status_code': link_response.status_code})
                except:
                    link_statuses.append({'url': href, 'status_code': 0})
        
        for issue_name, config in self.issue_patterns.items():
            try:
                # Special handling for different issue types
                if issue_name == 'slow_loading':
                    if config['pattern'](response):
                        issues.append(WebsiteIssue(
                            issue_type=issue_name,
                            severity=config['severity'],
                            description=config['description'],
                            recommendation=config['recommendation'],
                            affected_pages=[url],
                            impact_score=config['impact_score']
                        ))
                
                elif issue_name == 'broken_links':
                    if config['pattern'](link_statuses):
                        broken_links = [l['url'] for l in link_statuses if l['status_code'] >= 400]
                        issues.append(WebsiteIssue(
                            issue_type=issue_name,
                            severity=config['severity'],
                            description=f"Found {len(broken_links)} broken links",
                            recommendation=config['recommendation'],
                            affected_pages=broken_links[:5],  # Show first 5
                            impact_score=config['impact_score']
                        ))
                
                else:
                    # Generic pattern matching
                    if config['pattern'](soup):
                        issues.append(WebsiteIssue(
                            issue_type=issue_name,
                            severity=config['severity'],
                            description=config['description'],
                            recommendation=config['recommendation'],
                            affected_pages=[url],
                            impact_score=config['impact_score']
                        ))
            
            except Exception as e:
                print(f"Error checking issue {issue_name}: {e}")
                continue
        
        return issues
    
    def _calculate_overall_score(self, issues: List[WebsiteIssue], metrics: Dict) -> float:
        """Calculate overall website quality score"""
        base_score = 1.0
        
        # Deduct points for issues based on severity
        severity_weights = {
            'critical': 0.4,
            'high': 0.25,
            'medium': 0.15,
            'low': 0.05
        }
        
        for issue in issues:
            weight = severity_weights.get(issue.severity, 0.1)
            base_score -= (weight * issue.impact_score)
        
        if metrics.get('has_viewport', False):
            base_score += 0.05
        
        if metrics.get('has_meta_description', False):
            base_score += 0.05
        
        if metrics.get('has_google_analytics', False):
            base_score += 0.05
        
        return max(0.0, min(1.0, base_score))
    
    def _determine_qualification(self, overall_score: float, issues: List[WebsiteIssue]) -> bool:
        """Determine if lead qualifies for outreach"""
        # Critical issues disqualify
        critical_issues = [i for i in issues if i.severity == 'critical']
        if critical_issues:
            return False
        
        # Score threshold
        if overall_score < 0.4:
            return False
        
        # Too many high-severity issues
        high_issues = [i for i in issues if i.severity == 'high']
        if len(high_issues) > 3:
            return False
        
        return True
    
        
class StageBAuditor:
    """Stage B: 'Needs Update' Auditor Engine"""
    
    def __init__(self):
        self.technical_auditor = TechnicalAuditor()
        self.audit_queue = []
    
    def audit_pending_leads(self, batch_size: int = 50) -> Dict:
        """Audit all pending leads in database"""
        print("=== STAGE B: 'NEEDS UPDATE' AUDITOR ENGINE ===")
        
        # Get pending leads
        pending_leads = self._fetch_pending_leads(batch_size)
        
        if not pending_leads:
            print("No pending leads to audit")
            return {'audited_count': 0, 'qualified_count': 0, 'results': []}
        
        print(f"Found {len(pending_leads)} leads to audit")
        
        results = []
        qualified_count = 0
        
        for i, lead in enumerate(pending_leads):
            business_name = lead.get('business_name')
            website = lead.get('website')
            lead_id = lead.get('id')
            
            print(f"\n[{i+1}/{len(pending_leads)}] Auditing: {business_name}")
            
            try:
                # Perform audit
                audit_result = self.technical_auditor.audit_website(website, lead_id, business_name)
                results.append(audit_result)
                
                # Save audit to database (this saves the audit record and updates status to qualified/disqualified locally)
                self._save_audit_result(audit_result)
                
                if audit_result.qualification_status:
                    qualified_count += 1
                
                # Add delay between audits
                time.sleep(2)
                
            except Exception as e:
                print(f"Error auditing {business_name}: {e}")
                continue
        
        # Update lead statuses (batch update for extra fields like quality score and email)
        self._update_lead_status(results)
        
        # Print summary
        self._print_audit_summary(results, qualified_count)
        
        return {
            'audited_count': len(results),
            'qualified_count': qualified_count,
            'qualification_rate': qualified_count / len(results) if results else 0,
            'results': results
        }
    
    def _fetch_pending_leads(self, limit: int = 10) -> List[Dict]:
        """Fetch leads that need auditing via repository"""
        from core.db import LeadRepository
        repo = LeadRepository()
        
        print(f"Fetching {limit} pending leads for audit...")
        return repo.get_pending_audits(limit)
    
    def _save_audit_result(self, audit_result: AuditResult):
        """Save audit result via repository"""
        from core.db import LeadRepository
        repo = LeadRepository()
        
        result_data = {
            'overall_score': audit_result.overall_score,
            'issues': audit_result.issues,
            'technical_metrics': audit_result.technical_metrics,
            'qualified': audit_result.qualified,
            'llm_analysis': audit_result.llm_analysis
        }
        
        # Serialize issues manually here locally to match expectations if needed
        # But repo handles basic serialization if passed as dicts
        result_data['issues'] = [
            {
                'issue_type': issue.issue_type,
                'severity': issue.severity,
                'description': issue.description,
                'recommendation': issue.recommendation,
                'affected_pages': issue.affected_pages,
                'impact_score': issue.impact_score
            }
            for issue in audit_result.issues
        ]
        
        repo.save_audit_result(audit_result.lead_id, result_data)
    
    def _update_lead_status(self, results: List[AuditResult]):
        """Update lead statuses based on audit results via repository"""
        from core.db import LeadRepository
        repo = LeadRepository()
        
        for result in results:
            updates = {}
            
            if result.qualification_status:
                updates['status'] = 'qualified'
            else:
                updates['status'] = 'disqualified'
                
            updates['quality_score'] = result.overall_score
            
            # Extract discovered email
            discovered_email = result.technical_metrics.get('discovered_email', '')
            if discovered_email:
                updates['email'] = discovered_email
            
            repo.update_lead(result.lead_id, **updates)
    
    def _print_audit_summary(self, results: List[AuditResult], qualified_count: int):
        """Print audit summary"""
        print(f"\n{'='*60}")
        print("STAGE B: AUDIT ENGINE SUMMARY")
        print(f"{'='*60}")
        print(f"Total Audited: {len(results)}")
        print(f"Qualified: {qualified_count}")
        print(f"Disqualified: {len(results) - qualified_count}")
        print(f"Qualification Rate: {qualified_count/len(results):.1%}" if results else "0%")
        
        # Issue statistics
        all_issues = []
        for result in results:
            all_issues.extend(result.issues)
        
        if all_issues:
            print(f"\n--- Top Issues Found ---")
            issue_counts = {}
            for issue in all_issues:
                issue_counts[issue.issue_type] = issue_counts.get(issue.issue_type, 0) + 1
            
            sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
            for issue_type, count in sorted_issues[:10]:
                print(f"{issue_type}: {count}")
        
        # Score distribution
        if results:
            scores = [r.overall_score for r in results]
            avg_score = sum(scores) / len(scores)
            print(f"\n--- Score Distribution ---")
            print(f"Average Score: {avg_score:.2f}")
            print(f"Best Score: {max(scores):.2f}")
            print(f"Worst Score: {min(scores):.2f}")
    
    def get_audit_statistics(self) -> Dict:
        """Get overall audit statistics"""
        from core.db import LeadRepository
        repo = LeadRepository()
        return repo.get_audit_statistics()
