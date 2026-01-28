"""
Stage B: "Needs Update" Auditor Engine
Technical website analysis for lead qualification and issue identification
"""

import requests
import json
import sqlite3
import time
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import ssl
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
    estimated_fix_cost: str
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
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    def analyze_website(self, business_name: str, metrics: Dict, soup: BeautifulSoup) -> Dict:
        """Get LLM-based qualitative analysis and outreach hooks"""
        if not self.enabled:
            return {"error": "Ollama not available"}

        # Extract context
        title = soup.find('title').text.strip() if soup.find('title') else "N/A"
        headings = [h.text.strip() for h in soup.find_all(['h1', 'h2'])[:5]]
        
        prompt = f"""Analyze this website's technical and UX state for a cold outreach campaign.
BUSINESS: {business_name}
WEBSITE TITLE: {title}
TOP HEADINGS: {headings}
METRICS:
- Response Time: {metrics.get('response_time', 'N/A')}s
- Has SSL: {metrics.get('has_ssl', 'N/A')}
- Mobile Ready: {metrics.get('has_viewport', 'N/A')}
- Google Analytics: {metrics.get('has_google_analytics', 'N/A')}

TASK:
1. Provide a 2-sentence technical critique (be specific but professional).
2. Identify the 'Business Impact' of these issues (how it loses them money).
3. Generate 3 unique 'Personalized Hooks' for an email subject line or opening.

FORMAT: Return ONLY a JSON object with:
{{
  "critique": "...",
  "business_impact": "...",
  "hooks": ["...", "...", "..."]
}}"""

        try:
            response = requests.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }, timeout=30)
            
            if response.status_code == 200:
                result = response.json().get('response', '{}')
                return json.loads(result)
            return {"error": f"Ollama error: {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

class TechnicalAuditor:
    """Core technical auditing engine"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # Initialize LLM Auditor
        self.llm_auditor = OllamaAuditor()
        
        # SSL context for HTTPS sites
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # Issue detection patterns
        self.issue_patterns = {
            'missing_ssl': {
                'pattern': lambda url: not url.startswith('https://'),
                'severity': 'high',
                'description': 'Website not using HTTPS encryption',
                'recommendation': 'Install SSL certificate to enable HTTPS',
                'impact_score': 0.7
            },
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
                'pattern': lambda soup: bool(soup.find(text=re.compile(r'WordPress\s*[0-4]\.|Joomla\s*1\.|Drupal\s*[6-7]\.'))),
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
    
    def audit_website(self, url: str, lead_id: int, business_name: str) -> AuditResult:
        """Perform comprehensive website audit"""
        print(f"Auditing: {business_name} - {url}")
        
        issues = []
        technical_metrics = {}
        overall_score = 1.0
        
        try:
            # Normalize URL
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            # Test HTTP and HTTPS
            http_response, https_response = self._test_protocols(url)
            
            # Get main content (prefer HTTPS if available)
            main_response = https_response if https_response else http_response
            
            if not main_response:
                raise Exception("Could not fetch website")
            
            # Parse HTML
            soup = BeautifulSoup(main_response.content, 'html.parser')
            
            # Collect technical metrics
            technical_metrics = self._collect_technical_metrics(main_response, soup)
            
            # Detect issues
            issues = self._detect_issues(url, main_response, soup)
            
            # Calculate overall score
            overall_score = self._calculate_overall_score(issues, technical_metrics)
            
            # Determine qualification
            qualification_status = self._determine_qualification(overall_score, issues)
            
            # Estimate fix cost
            estimated_fix_cost = self._estimate_fix_cost(issues)
            
            # Perform LLM analysis
            llm_analysis = self.llm_auditor.analyze_website(business_name, technical_metrics, soup)
            
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
            estimated_fix_cost = 'Unknown'
        
        return AuditResult(
            lead_id=lead_id,
            business_name=business_name,
            website=url,
            overall_score=overall_score,
            issues=issues,
            technical_metrics=technical_metrics,
            qualification_status=qualification_status,
            audit_timestamp=datetime.now(),
            estimated_fix_cost=estimated_fix_cost,
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
            https_response = self.session.get(https_url, timeout=10, allow_redirects=True, verify=False)
        except:
            pass
        
        return http_response, https_response
    
    def _collect_technical_metrics(self, response: requests.Response, soup: BeautifulSoup) -> Dict:
        """Collect technical metrics about the website"""
        metrics = {
            'response_time': response.elapsed.total_seconds(),
            'status_code': response.status_code,
            'content_size': len(response.content),
            'has_ssl': response.url.startswith('https://'),
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
            'has_navigation': bool(soup.find('nav'))
        }
        
        return metrics
    
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
                if issue_name == 'missing_ssl':
                    if config['pattern'](url):
                        issues.append(WebsiteIssue(
                            issue_type=issue_name,
                            severity=config['severity'],
                            description=config['description'],
                            recommendation=config['recommendation'],
                            affected_pages=[url],
                            impact_score=config['impact_score']
                        ))
                
                elif issue_name == 'slow_loading':
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
        
        # Bonus points for good practices
        if metrics.get('has_ssl', False):
            base_score += 0.1
        
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
    
    def _estimate_fix_cost(self, issues: List[WebsiteIssue]) -> str:
        """Estimate cost to fix identified issues"""
        cost_estimate = 0
        
        for issue in issues:
            if issue.severity == 'critical':
                cost_estimate += 500
            elif issue.severity == 'high':
                cost_estimate += 200
            elif issue.severity == 'medium':
                cost_estimate += 100
            elif issue.severity == 'low':
                cost_estimate += 50
        
        if cost_estimate < 200:
            return 'Low ($50-$200)'
        elif cost_estimate < 500:
            return 'Medium ($200-$500)'
        elif cost_estimate < 1000:
            return 'High ($500-$1000)'
        else:
            return 'Very High ($1000+)'

class StageBAuditor:
    """Stage B: 'Needs Update' Auditor Engine"""
    
    def __init__(self):
        self.technical_auditor = TechnicalAuditor()
        self.audit_queue = []
    
    def audit_pending_leads(self, batch_size: int = 50) -> Dict:
        """Audit all pending leads in database"""
        print("=== STAGE B: 'NEEDS UPDATE' AUDITOR ENGINE ===")
        
        # Get pending leads from database
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, business_name, website
        FROM leads
        WHERE status = 'pending_audit'
        AND website IS NOT NULL
        AND website != ''
        LIMIT ?
        ''', (batch_size,))
        
        pending_leads = cursor.fetchall()
        conn.close()
        
        if not pending_leads:
            print("No pending leads to audit")
            return {'audited_count': 0, 'qualified_count': 0, 'results': []}
        
        print(f"Found {len(pending_leads)} leads to audit")
        
        results = []
        qualified_count = 0
        
        for i, (lead_id, business_name, website) in enumerate(pending_leads):
            print(f"\n[{i+1}/{len(pending_leads)}] Auditing: {business_name}")
            
            try:
                # Perform audit
                audit_result = self.technical_auditor.audit_website(website, lead_id, business_name)
                results.append(audit_result)
                
                # Save audit to database
                self._save_audit_result(audit_result)
                
                if audit_result.qualification_status:
                    qualified_count += 1
                
                # Add delay between audits
                time.sleep(2)
                
            except Exception as e:
                print(f"Error auditing {business_name}: {e}")
                continue
        
        # Update lead statuses
        self._update_lead_status(results)
        
        # Print summary
        self._print_audit_summary(results, qualified_count)
        
        return {
            'audited_count': len(results),
            'qualified_count': qualified_count,
            'qualification_rate': qualified_count / len(results) if results else 0,
            'results': results
        }
    
    def _save_audit_result(self, audit_result: AuditResult):
        """Save audit result to database"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Convert issues to JSON
        issues_json = json.dumps([
            {
                'issue_type': issue.issue_type,
                'severity': issue.severity,
                'description': issue.description,
                'recommendation': issue.recommendation,
                'affected_pages': issue.affected_pages,
                'impact_score': issue.impact_score
            }
            for issue in audit_result.issues
        ])
        
        # Convert metrics to JSON
        metrics_json = json.dumps(audit_result.technical_metrics)
        
        cursor.execute('''
        INSERT OR REPLACE INTO audits
        (lead_id, overall_score, issues_json, technical_metrics, qualified, audit_date, estimated_fix_cost, llm_analysis)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            audit_result.lead_id,
            audit_result.overall_score,
            issues_json,
            metrics_json,
            audit_result.qualification_status,
            audit_result.audit_timestamp.isoformat(),
            audit_result.estimated_fix_cost,
            json.dumps(audit_result.llm_analysis) if audit_result.llm_analysis else None
        ))
        
        conn.commit()
        conn.close()
    
    def _update_lead_status(self, results: List[AuditResult]):
        """Update lead statuses based on audit results"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        for result in results:
            if result.qualification_status:
                new_status = 'qualified'
            else:
                new_status = 'disqualified'
            
            cursor.execute('''
            UPDATE leads
            SET status = ?, quality_score = ?
            WHERE id = ?
            ''', (new_status, result.overall_score, result.lead_id))
        
        conn.commit()
        conn.close()
    
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
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Get audit stats
        cursor.execute('''
        SELECT 
            COUNT(*) as total_audits,
            COUNT(CASE WHEN qualified = 1 THEN 1 END) as qualified,
            AVG(overall_score) as avg_score,
            estimated_fix_cost,
            COUNT(*) as total
        FROM audits
        ''')
        
        audit_stats = cursor.fetchone()
        
        # Get issue statistics
        cursor.execute('SELECT issues_json FROM audits WHERE issues_json IS NOT NULL')
        all_issues_json = cursor.fetchall()
        
        issue_counts = {}
        for (issues_json,) in all_issues_json:
            try:
                issues = json.loads(issues_json)
                for issue in issues:
                    issue_type = issue.get('issue_type', 'unknown')
                    issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
            except:
                continue
        
        conn.close()
        
        return {
            'total_audits': audit_stats[0] or 0,
            'qualified_count': audit_stats[1] or 0,
            'qualification_rate': (audit_stats[1] or 0) / max(audit_stats[0] or 1, 1),
            'average_score': audit_stats[2] or 0,
            'top_issues': dict(sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        }

if __name__ == '__main__':
    # Demo usage
    auditor = StageBAuditor()
    
    print("Stage B: 'Needs Update' Auditor Engine")
    print("Choose an option:")
    print("1. Audit pending leads")
    print("2. Get audit statistics")
    print("3. Audit single website (test)")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == '1':
        results = auditor.audit_pending_leads(batch_size=20)
        print(f"\n✅ Audit completed: {results['qualified_count']}/{results['audited_count']} qualified")
    elif choice == '2':
        stats = auditor.get_audit_statistics()
        print(f"\n=== AUDIT STATISTICS ===")
        print(f"Total Audits: {stats['total_audits']}")
        print(f"Qualified: {stats['qualified_count']}")
        print(f"Qualification Rate: {stats['qualification_rate']:.1%}")
        print(f"Average Score: {stats['average_score']:.2f}")
        if stats['top_issues']:
            print(f"\nTop Issues:")
            for issue, count in stats['top_issues'].items():
                print(f"  {issue}: {count}")
    elif choice == '3':
        url = input("Enter website URL to test: ").strip()
        business_name = input("Enter business name: ").strip()
        
        audit_result = auditor.technical_auditor.audit_website(url, 1, business_name)
        
        print(f"\n=== AUDIT RESULT ===")
        print(f"Overall Score: {audit_result.overall_score:.2f}")
        print(f"Qualified: {audit_result.qualification_status}")
        print(f"Estimated Fix Cost: {audit_result.estimated_fix_cost}")
        print(f"\nIssues Found ({len(audit_result.issues)}):")
        for issue in audit_result.issues:
            print(f"  - {issue.issue_type} ({issue.severity}): {issue.description}")
            
        if audit_result.llm_analysis:
            print(f"\n=== LLM ANALYSIS ===")
            print(f"Critique: {audit_result.llm_analysis.get('critique', 'N/A')}")
            print(f"Business Impact: {audit_result.llm_analysis.get('business_impact', 'N/A')}")
            print(f"Hooks: {', '.join(audit_result.llm_analysis.get('hooks', []))}")
    else:
        print("Invalid choice")
