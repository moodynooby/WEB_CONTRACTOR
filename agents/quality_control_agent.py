"""
Quality Control Agent
Monitors and validates the entire lead generation pipeline
"""

import sqlite3
import json
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from enum import Enum

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class QualityAlert:
    """Quality control alert"""
    alert_id: str
    level: AlertLevel
    category: str  # 'scraping', 'auditing', 'email_generation', 'data_quality'
    title: str
    description: str
    affected_items: List[str]
    recommendation: str
    timestamp: datetime
    auto_fixable: bool
    priority: int  # 1-10, 1 being highest

@dataclass
class QualityMetrics:
    """Quality metrics for a stage"""
    stage_name: str
    success_rate: float
    error_rate: float
    throughput: float  # items per hour
    quality_score: float  # 0.0 to 1.0
    last_check: datetime
    issues_found: int
    issues_resolved: int

class DataQualityValidator:
    """Validates data quality across the pipeline"""
    
    def __init__(self):
        self.validation_rules = {
            'leads': {
                'required_fields': ['business_name', 'website'],
                'field_validators': {
                    'business_name': lambda x: len(x.strip()) > 2,
                    'website': lambda x: self._is_valid_url(x),
                    'phone': lambda x: x is None or self._is_valid_phone(x),
                    'category': lambda x: x is not None and len(x.strip()) > 0
                },
                'duplicate_threshold': 0.1,  # Max 10% duplicates
                'quality_threshold': 0.7  # Min 70% quality score
            },
            'audits': {
                'required_fields': ['lead_id', 'overall_score'],
                'field_validators': {
                    'overall_score': lambda x: 0.0 <= x <= 1.0,
                    'qualified': lambda x: x in [0, 1],
                    'issues_json': lambda x: x is None or self._is_valid_json(x)
                },
                'qualification_rate_range': (0.2, 0.8),  # 20-80% qualification rate
                'score_distribution_check': True
            },
            'emails': {
                'required_fields': ['lead_id', 'subject', 'body'],
                'field_validators': {
                    'subject': lambda x: len(x.strip()) > 5,
                    'body': lambda x: 50 <= len(x.strip()) <= 500,
                    'word_count': lambda x: 50 <= x <= 200,
                    'personalization_score': lambda x: 0.0 <= x <= 1.0
                },
                'word_count_range': (100, 150),  # Target word count
                'personalization_threshold': 0.5  # Min 50% personalization
            }
        }
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format"""
        if not url or not isinstance(url, str):
            return False
        
        url = url.strip()
        if not url:
            return False
        
        # Basic URL pattern
        pattern = r'^https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.])*(?:\?(?:[\w&=%.])*)?(?:#(?:\w*))?)?$'
        return bool(re.match(pattern, url))
    
    def _is_valid_phone(self, phone: str) -> bool:
        """Validate phone number format"""
        if not phone or not isinstance(phone, str):
            return False
        
        # Remove non-digit characters
        digits = re.sub(r'[^\d+]', '', phone)
        
        # Basic phone validation (10-15 digits)
        return 10 <= len(digits) <= 15 and digits.startswith(('+', '0', '1', '9', '8', '7'))
    
    def _is_valid_json(self, json_str: str) -> bool:
        """Validate JSON string"""
        if not json_str or not isinstance(json_str, str):
            return False
        
        try:
            json.loads(json_str)
            return True
        except:
            return False
    
    def validate_leads_quality(self, sample_size: int = 100) -> List[QualityAlert]:
        """Validate leads data quality"""
        alerts = []
        
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Sample validation
        cursor.execute('SELECT * FROM leads ORDER BY RANDOM() LIMIT ?', (sample_size,))
        leads = cursor.fetchall()
        
        if not leads:
            alerts.append(QualityAlert(
                alert_id='no_leads_found',
                level=AlertLevel.ERROR,
                category='data_quality',
                title='No Leads Found',
                description='No leads found in database for validation',
                affected_items=['leads table'],
                recommendation='Run Stage 0 scraper to generate leads',
                timestamp=datetime.now(),
                auto_fixable=False,
                priority=1
            ))
            conn.close()
            return alerts
        
        # Get column names
        cursor.execute('PRAGMA table_info(leads)')
        columns = [col[1] for col in cursor.fetchall()]
        
        # Validate each lead
        invalid_leads = []
        duplicate_leads = []
        low_quality_leads = []
        
        for lead in leads:
            lead_dict = dict(zip(columns, lead))
            
            # Check required fields
            missing_fields = []
            for field in self.validation_rules['leads']['required_fields']:
                if not lead_dict.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                invalid_leads.append(f"{lead_dict.get('business_name', 'Unknown')}: Missing {', '.join(missing_fields)}")
            
            # Check field validators
            for field, validator in self.validation_rules['leads']['field_validators'].items():
                value = lead_dict.get(field)
                if value is not None and not validator(value):
                    invalid_leads.append(f"{lead_dict.get('business_name', 'Unknown')}: Invalid {field}")
            
            # Check quality score
            quality_score = lead_dict.get('quality_score', 0)
            if quality_score < self.validation_rules['leads']['quality_threshold']:
                low_quality_leads.append(lead_dict.get('business_name', 'Unknown'))
        
        # Check for duplicates
        cursor.execute('''
        SELECT business_name, website, COUNT(*) as count
        FROM leads
        GROUP BY business_name, website
        HAVING count > 1
        LIMIT 10
        ''')
        
        duplicates = cursor.fetchall()
        for dup in duplicates:
            duplicate_leads.append(f"{dup[0]} ({dup[1]}): {dup[2]} duplicates")
        
        conn.close()
        
        # Create alerts
        if invalid_leads:
            alerts.append(QualityAlert(
                alert_id='invalid_leads',
                level=AlertLevel.WARNING,
                category='data_quality',
                title='Invalid Lead Data Found',
                description=f'Found {len(invalid_leads)} leads with validation errors',
                affected_items=invalid_leads[:10],
                recommendation='Review and clean invalid lead records',
                timestamp=datetime.now(),
                auto_fixable=False,
                priority=3
            ))
        
        if duplicate_leads:
            alerts.append(QualityAlert(
                alert_id='duplicate_leads',
                level=AlertLevel.WARNING,
                category='data_quality',
                title='Duplicate Leads Found',
                description=f'Found {len(duplicate_leads)} sets of duplicate leads',
                affected_items=duplicate_leads,
                recommendation='Remove duplicate records or implement deduplication',
                timestamp=datetime.now(),
                auto_fixable=True,
                priority=4
            ))
        
        if low_quality_leads:
            alerts.append(QualityAlert(
                alert_id='low_quality_leads',
                level=AlertLevel.INFO,
                category='data_quality',
                title='Low Quality Leads',
                description=f'Found {len(low_quality_leads)} leads with quality score below threshold',
                affected_items=low_quality_leads[:10],
                recommendation='Review lead quality scoring criteria',
                timestamp=datetime.now(),
                auto_fixable=False,
                priority=6
            ))
        
        return alerts
    
    def validate_audit_quality(self, sample_size: int = 50) -> List[QualityAlert]:
        """Validate audit data quality"""
        alerts = []
        
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Check audit completion rate
        cursor.execute('SELECT COUNT(*) FROM leads WHERE status = "pending_audit"')
        pending_audits = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM leads')
        total_leads = cursor.fetchone()[0]
        
        if total_leads > 0:
            pending_rate = pending_audits / total_leads
            if pending_rate > 0.3:  # More than 30% pending
                alerts.append(QualityAlert(
                    alert_id='high_pending_audits',
                    level=AlertLevel.WARNING,
                    category='auditing',
                    title='High Number of Pending Audits',
                    description=f'{pending_audits} leads ({pending_rate:.1%}) waiting for audit',
                    affected_items=[f'{pending_audits} pending audits'],
                    recommendation='Run Stage B auditor to process pending leads',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=2
                ))
        
        # Validate audit data
        cursor.execute('SELECT * FROM audits ORDER BY RANDOM() LIMIT ?', (sample_size,))
        audits = cursor.fetchall()
        
        if audits:
            cursor.execute('PRAGMA table_info(audits)')
            columns = [col[1] for col in cursor.fetchall()]
            
            invalid_audits = []
            qualification_rates = []
            
            for audit in audits:
                audit_dict = dict(zip(columns, audit))
                
                # Check required fields
                missing_fields = []
                for field in self.validation_rules['audits']['required_fields']:
                    if audit_dict.get(field) is None:
                        missing_fields.append(field)
                
                if missing_fields:
                    invalid_audits.append(f"Audit {audit_dict.get('lead_id', 'Unknown')}: Missing {', '.join(missing_fields)}")
                
                # Check field validators
                for field, validator in self.validation_rules['audits']['field_validators'].items():
                    value = audit_dict.get(field)
                    if value is not None and not validator(value):
                        invalid_audits.append(f"Audit {audit_dict.get('lead_id', 'Unknown')}: Invalid {field}")
                
                # Track qualification rates
                if audit_dict.get('qualified') is not None:
                    qualification_rates.append(audit_dict['qualified'])
            
            if invalid_audits:
                alerts.append(QualityAlert(
                    alert_id='invalid_audits',
                    level=AlertLevel.ERROR,
                    category='auditing',
                    title='Invalid Audit Data',
                    description=f'Found {len(invalid_audits)} audits with validation errors',
                    affected_items=invalid_audits[:10],
                    recommendation='Review audit process and fix data validation',
                    timestamp=datetime.now(),
                    auto_fixable=False,
                    priority=3
                ))
            
            # Check qualification rate
            if qualification_rates:
                qual_rate = sum(qualification_rates) / len(qualification_rates)
                min_rate, max_rate = self.validation_rules['audits']['qualification_rate_range']
                
                if qual_rate < min_rate:
                    alerts.append(QualityAlert(
                        alert_id='low_qualification_rate',
                        level=AlertLevel.WARNING,
                        category='auditing',
                        title='Low Qualification Rate',
                        description=f'Only {qual_rate:.1%} of leads qualify (target: {min_rate:.1%}-{max_rate:.1%})',
                        affected_items=[f'Current rate: {qual_rate:.1%}'],
                        recommendation='Review qualification criteria or improve lead quality',
                        timestamp=datetime.now(),
                        auto_fixable=False,
                        priority=5
                    ))
                elif qual_rate > max_rate:
                    alerts.append(QualityAlert(
                        alert_id='high_qualification_rate',
                        level=AlertLevel.INFO,
                        category='auditing',
                        title='High Qualification Rate',
                        description=f'{qual_rate:.1%} of leads qualify (very high)',
                        affected_items=[f'Current rate: {qual_rate:.1%}'],
                        recommendation='Consider tightening qualification criteria',
                        timestamp=datetime.now(),
                        auto_fixable=False,
                        priority=7
                    ))
        
        conn.close()
        return alerts
    
    def validate_email_quality(self, sample_size: int = 50) -> List[QualityAlert]:
        """Validate email generation quality"""
        alerts = []
        
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Check email generation backlog
        cursor.execute('''
        SELECT COUNT(*) FROM leads l
        JOIN audits a ON l.id = a.lead_id
        WHERE a.qualified = 1
        AND l.id NOT IN (SELECT DISTINCT lead_id FROM email_campaigns)
        ''')
        
        pending_emails = cursor.fetchone()[0]
        
        if pending_emails > 20:  # More than 20 qualified leads without emails
            alerts.append(QualityAlert(
                alert_id='email_generation_backlog',
                level=AlertLevel.WARNING,
                category='email_generation',
                title='Email Generation Backlog',
                description=f'{pending_emails} qualified leads waiting for email generation',
                affected_items=[f'{pending_emails} pending emails'],
                recommendation='Run Stage C email generator',
                timestamp=datetime.now(),
                auto_fixable=True,
                priority=2
            ))
        
        # Validate email data
        cursor.execute('SELECT * FROM email_campaigns ORDER BY RANDOM() LIMIT ?', (sample_size,))
        emails = cursor.fetchall()
        
        if emails:
            cursor.execute('PRAGMA table_info(email_campaigns)')
            columns = [col[1] for col in cursor.fetchall()]
            
            invalid_emails = []
            low_personalization = []
            word_count_issues = []
            
            for email in emails:
                email_dict = dict(zip(columns, email))
                
                # Check required fields
                missing_fields = []
                for field in self.validation_rules['emails']['required_fields']:
                    if not email_dict.get(field):
                        missing_fields.append(field)
                
                if missing_fields:
                    invalid_emails.append(f"Email {email_dict.get('id', 'Unknown')}: Missing {', '.join(missing_fields)}")
                
                # Check field validators
                for field, validator in self.validation_rules['emails']['field_validators'].items():
                    value = email_dict.get(field)
                    if value is not None and not validator(value):
                        invalid_emails.append(f"Email {email_dict.get('id', 'Unknown')}: Invalid {field}")
                
                # Check personalization
                pers_score = email_dict.get('personalization_score', 0)
                if pers_score < self.validation_rules['emails']['personalization_threshold']:
                    low_personalization.append(f"Email {email_dict.get('id', 'Unknown')}: {pers_score:.2f}")
                
                # Check word count
                word_count = email_dict.get('word_count', 0)
                min_words, max_words = self.validation_rules['emails']['word_count_range']
                if word_count < min_words or word_count > max_words:
                    word_count_issues.append(f"Email {email_dict.get('id', 'Unknown')}: {word_count} words")
            
            if invalid_emails:
                alerts.append(QualityAlert(
                    alert_id='invalid_emails',
                    level=AlertLevel.ERROR,
                    category='email_generation',
                    title='Invalid Email Data',
                    description=f'Found {len(invalid_emails)} emails with validation errors',
                    affected_items=invalid_emails[:10],
                    recommendation='Review email generation process',
                    timestamp=datetime.now(),
                    auto_fixable=False,
                    priority=3
                ))
            
            if low_personalization:
                alerts.append(QualityAlert(
                    alert_id='low_personalization',
                    level=AlertLevel.WARNING,
                    category='email_generation',
                    title='Low Email Personalization',
                    description=f'{len(low_personalization)} emails below personalization threshold',
                    affected_items=low_personalization[:10],
                    recommendation='Improve email personalization algorithms',
                    timestamp=datetime.now(),
                    auto_fixable=False,
                    priority=5
                ))
            
            if word_count_issues:
                alerts.append(QualityAlert(
                    alert_id='word_count_issues',
                    level=AlertLevel.INFO,
                    category='email_generation',
                    title='Word Count Issues',
                    description=f'{len(word_count_issues)} emails with incorrect word count',
                    affected_items=word_count_issues[:10],
                    recommendation='Adjust email generation word count targets',
                    timestamp=datetime.now(),
                    auto_fixable=False,
                    priority=6
                ))
        
        conn.close()
        return alerts

class PipelineMonitor:
    """Monitors pipeline performance and health"""
    
    def __init__(self):
        self.stage_thresholds = {
            'stage0_scraper': {
                'min_throughput': 10,  # leads per hour
                'max_error_rate': 0.1,  # 10% error rate
                'min_success_rate': 0.7  # 70% success rate
            },
            'stage_b_auditor': {
                'min_throughput': 20,  # audits per hour
                'max_error_rate': 0.05,  # 5% error rate
                'min_success_rate': 0.9  # 90% success rate
            },
            'stage_c_messaging': {
                'min_throughput': 30,  # emails per hour
                'max_error_rate': 0.05,  # 5% error rate
                'min_success_rate': 0.95  # 95% success rate
            }
        }
    
    def check_pipeline_health(self) -> List[QualityAlert]:
        """Check overall pipeline health"""
        alerts = []
        
        # Check database connectivity
        try:
            conn = sqlite3.connect('leads.db')
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            conn.close()
        except Exception as e:
            alerts.append(QualityAlert(
                alert_id='database_connection_failed',
                level=AlertLevel.CRITICAL,
                category='infrastructure',
                title='Database Connection Failed',
                description=f'Cannot connect to database: {str(e)}',
                affected_items=['database'],
                recommendation='Check database file and permissions',
                timestamp=datetime.now(),
                auto_fixable=False,
                priority=1
            ))
            return alerts
        
        # Check stage performance
        alerts.extend(self._check_stage_performance())
        
        # Check data flow between stages
        alerts.extend(self._check_data_flow())
        
        return alerts
    
    def _check_stage_performance(self) -> List[QualityAlert]:
        """Check individual stage performance"""
        alerts = []
        
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Check Stage 0 (Scraping) performance
        cursor.execute('''
        SELECT 
            COUNT(*) as total_leads,
            DATE(created_at) as date
        FROM leads
        WHERE created_at >= date('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        ''')
        
        scraping_data = cursor.fetchall()
        if scraping_data:
            avg_daily_leads = sum(row[0] for row in scraping_data) / len(scraping_data)
            if avg_daily_leads < self.stage_thresholds['stage0_scraper']['min_throughput']:
                alerts.append(QualityAlert(
                    alert_id='low_scraping_throughput',
                    level=AlertLevel.WARNING,
                    category='scraping',
                    title='Low Scraping Throughput',
                    description=f'Average {avg_daily_leads:.1f} leads per day (target: {self.stage_thresholds["stage0_scraper"]["min_throughput"]})',
                    affected_items=[f'Current: {avg_daily_leads:.1f}/day'],
                    recommendation='Check scraper configuration and anti-blocking measures',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=4
                ))
        
        # Check Stage B (Auditing) performance
        cursor.execute('''
        SELECT 
            COUNT(*) as total_audits,
            DATE(audit_date) as date
        FROM audits
        WHERE audit_date >= date('now', '-7 days')
        GROUP BY DATE(audit_date)
        ORDER BY date DESC
        ''')
        
        audit_data = cursor.fetchall()
        if audit_data:
            avg_daily_audits = sum(row[0] for row in audit_data) / len(audit_data)
            if avg_daily_audits < self.stage_thresholds['stage_b_auditor']['min_throughput']:
                alerts.append(QualityAlert(
                    alert_id='low_audit_throughput',
                    level=AlertLevel.WARNING,
                    category='auditing',
                    title='Low Audit Throughput',
                    description=f'Average {avg_daily_audits:.1f} audits per day (target: {self.stage_thresholds["stage_b_auditor"]["min_throughput"]})',
                    affected_items=[f'Current: {avg_daily_audits:.1f}/day'],
                    recommendation='Check auditor performance and optimize audit process',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=4
                ))
        
        # Check Stage C (Email) performance
        cursor.execute('''
        SELECT 
            COUNT(*) as total_emails,
            DATE(campaign_date) as date
        FROM email_campaigns
        WHERE campaign_date >= date('now', '-7 days')
        GROUP BY DATE(campaign_date)
        ORDER BY date DESC
        ''')
        
        email_data = cursor.fetchall()
        if email_data:
            avg_daily_emails = sum(row[0] for row in email_data) / len(email_data)
            if avg_daily_emails < self.stage_thresholds['stage_c_messaging']['min_throughput']:
                alerts.append(QualityAlert(
                    alert_id='low_email_throughput',
                    level=AlertLevel.WARNING,
                    category='email_generation',
                    title='Low Email Generation Throughput',
                    description=f'Average {avg_daily_emails:.1f} emails per day (target: {self.stage_thresholds["stage_c_messaging"]["min_throughput"]})',
                    affected_items=[f'Current: {avg_daily_emails:.1f}/day'],
                    recommendation='Check email generation process and Ollama connection',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=4
                ))
        
        conn.close()
        return alerts
    
    def _check_data_flow(self) -> List[QualityAlert]:
        """Check data flow between stages"""
        alerts = []
        
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Check leads -> audits flow
        cursor.execute('SELECT COUNT(*) FROM leads')
        total_leads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM audits')
        total_audits = cursor.fetchone()[0]
        
        if total_leads > 0:
            audit_coverage = total_audits / total_leads
            if audit_coverage < 0.8:  # Less than 80% coverage
                alerts.append(QualityAlert(
                    alert_id='low_audit_coverage',
                    level=AlertLevel.WARNING,
                    category='data_flow',
                    title='Low Audit Coverage',
                    description=f'Only {audit_coverage:.1%} of leads have been audited',
                    affected_items=[f'{total_audits}/{total_leads} leads audited'],
                    recommendation='Run Stage B auditor to improve coverage',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=3
                ))
        
        # Check audits -> emails flow
        cursor.execute('SELECT COUNT(*) FROM audits WHERE qualified = 1')
        qualified_leads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT lead_id) FROM email_campaigns')
        emailed_leads = cursor.fetchone()[0]
        
        if qualified_leads > 0:
            email_coverage = emailed_leads / qualified_leads
            if email_coverage < 0.8:  # Less than 80% coverage
                alerts.append(QualityAlert(
                    alert_id='low_email_coverage',
                    level=AlertLevel.WARNING,
                    category='data_flow',
                    title='Low Email Coverage',
                    description=f'Only {email_coverage:.1%} of qualified leads have emails',
                    affected_items=[f'{emailed_leads}/{qualified_leads} qualified leads emailed'],
                    recommendation='Run Stage C email generator',
                    timestamp=datetime.now(),
                    auto_fixable=True,
                    priority=3
                ))
        
        conn.close()
        return alerts

class QualityControlAgent:
    """Main Quality Control Agent"""
    
    def __init__(self):
        self.data_validator = DataQualityValidator()
        self.pipeline_monitor = PipelineMonitor()
        self.alert_history = []
    
    def run_quality_check(self, comprehensive: bool = True) -> Dict:
        """Run comprehensive quality check"""
        print("=== QUALITY CONTROL AGENT ===")
        print(f"Check started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        all_alerts = []
        
        # Data quality checks
        print("\n--- Checking Data Quality ---")
        leads_alerts = self.data_validator.validate_leads_quality()
        audit_alerts = self.data_validator.validate_audit_quality()
        email_alerts = self.data_validator.validate_email_quality()
        
        all_alerts.extend(leads_alerts)
        all_alerts.extend(audit_alerts)
        all_alerts.extend(email_alerts)
        
        # Pipeline health checks
        if comprehensive:
            print("\n--- Checking Pipeline Health ---")
            pipeline_alerts = self.pipeline_monitor.check_pipeline_health()
            all_alerts.extend(pipeline_alerts)
        
        # Store alerts
        self.alert_history.extend(all_alerts)
        
        # Generate summary
        summary = self._generate_quality_summary(all_alerts)
        
        # Print results
        self._print_quality_results(all_alerts, summary)
        
        # Auto-fix if possible
        auto_fixed = self._attempt_auto_fix(all_alerts)
        
        return {
            'total_alerts': len(all_alerts),
            'alerts_by_level': summary['by_level'],
            'alerts_by_category': summary['by_category'],
            'auto_fixed': auto_fixed,
            'recommendations': summary['recommendations'],
            'alerts': all_alerts
        }
    
    def _generate_quality_summary(self, alerts: List[QualityAlert]) -> Dict:
        """Generate quality summary"""
        summary = {
            'by_level': {},
            'by_category': {},
            'recommendations': []
        }
        
        # Count by level
        for alert in alerts:
            level = alert.level.value
            summary['by_level'][level] = summary['by_level'].get(level, 0) + 1
        
        # Count by category
        for alert in alerts:
            category = alert.category
            summary['by_category'][category] = summary['by_category'].get(category, 0) + 1
        
        # Generate recommendations
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL]
        error_alerts = [a for a in alerts if a.level == AlertLevel.ERROR]
        
        if critical_alerts:
            summary['recommendations'].append("URGENT: Address critical issues immediately")
        
        if error_alerts:
            summary['recommendations'].append("Fix error-level issues before proceeding")
        
        if len(alerts) > 10:
            summary['recommendations'].append("High number of issues detected - consider system review")
        
        # Auto-fixable issues
        auto_fixable = [a for a in alerts if a.auto_fixable]
        if auto_fixable:
            summary['recommendations'].append(f"{len(auto_fixable)} issues can be auto-fixed")
        
        return summary
    
    def _print_quality_results(self, alerts: List[QualityAlert], summary: Dict):
        """Print quality check results"""
        print(f"\n{'='*60}")
        print("QUALITY CONTROL RESULTS")
        print(f"{'='*60}")
        print(f"Total Issues Found: {len(alerts)}")
        
        if summary['by_level']:
            print(f"\n--- Issues by Severity ---")
            for level, count in summary['by_level'].items():
                print(f"{level.upper()}: {count}")
        
        if summary['by_category']:
            print(f"\n--- Issues by Category ---")
            for category, count in summary['by_category'].items():
                print(f"{category}: {count}")
        
        if alerts:
            print(f"\n--- Top Priority Issues ---")
            # Sort by priority (lower number = higher priority)
            sorted_alerts = sorted(alerts, key=lambda x: x.priority)[:10]
            
            for alert in sorted_alerts:
                print(f"[{alert.level.value.upper()}] {alert.title}")
                print(f"  {alert.description}")
                if alert.auto_fixable:
                    print(f"  ✅ Auto-fixable")
                print()
        
        if summary['recommendations']:
            print(f"--- Recommendations ---")
            for rec in summary['recommendations']:
                print(f"• {rec}")
    
    def _attempt_auto_fix(self, alerts: List[QualityAlert]) -> List[str]:
        """Attempt to auto-fix issues"""
        auto_fixed = []
        
        for alert in alerts:
            if not alert.auto_fixable:
                continue
            
            try:
                if alert.alert_id == 'duplicate_leads':
                    # Auto-remove duplicates (keep first occurrence)
                    fixed_count = self._auto_remove_duplicates()
                    if fixed_count > 0:
                        auto_fixed.append(f"Removed {fixed_count} duplicate leads")
                
                elif alert.alert_id == 'high_pending_audits':
                    # Trigger auditor
                    auto_fixed.append("Run Stage B auditor to process pending audits")
                
                elif alert.alert_id == 'email_generation_backlog':
                    # Trigger email generator
                    auto_fixed.append("Run Stage C email generator")
                
                elif alert.alert_id == 'low_scraping_throughput':
                    # Suggest scraper optimization
                    auto_fixed.append("Optimize scraper configuration and retry")
                
            except Exception as e:
                print(f"Auto-fix failed for {alert.alert_id}: {e}")
        
        return auto_fixed
    
    def _auto_remove_duplicates(self) -> int:
        """Auto-remove duplicate leads"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Find and remove duplicates (keep first occurrence)
        cursor.execute('''
        DELETE FROM leads WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM leads
            GROUP BY business_name, website
        )
        ''')
        
        removed_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return removed_count
    
    def get_quality_dashboard(self) -> Dict:
        """Get quality metrics for dashboard"""
        conn = sqlite3.connect('leads.db')
        cursor = conn.cursor()
        
        # Overall metrics
        cursor.execute('SELECT COUNT(*) FROM leads')
        total_leads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM audits')
        total_audits = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM audits WHERE qualified = 1')
        qualified_leads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM email_campaigns')
        total_emails = cursor.fetchone()[0]
        
        # Recent activity (last 24 hours)
        cursor.execute('SELECT COUNT(*) FROM leads WHERE created_at >= datetime("now", "-1 day")')
        recent_leads = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM audits WHERE audit_date >= datetime("now", "-1 day")')
        recent_audits = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM email_campaigns WHERE campaign_date >= datetime("now", "-1 day")')
        recent_emails = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_leads': total_leads,
            'total_audits': total_audits,
            'qualified_leads': qualified_leads,
            'total_emails': total_emails,
            'qualification_rate': qualified_leads / max(total_audits, 1),
            'email_coverage': total_emails / max(qualified_leads, 1),
            'audit_coverage': total_audits / max(total_leads, 1),
            'recent_activity': {
                'leads_24h': recent_leads,
                'audits_24h': recent_audits,
                'emails_24h': recent_emails
            },
            'recent_alerts': len([a for a in self.alert_history if a.timestamp > datetime.now() - timedelta(hours=24)])
        }

if __name__ == '__main__':
    # Demo usage
    qc_agent = QualityControlAgent()
    
    print("Quality Control Agent")
    print("Choose an option:")
    print("1. Run comprehensive quality check")
    print("2. Run quick quality check")
    print("3. Get quality dashboard")
    print("4. View recent alerts")
    
    choice = input("Enter choice (1-4): ").strip()
    
    if choice == '1':
        results = qc_agent.run_quality_check(comprehensive=True)
        print(f"\n✅ Quality check completed: {results['total_alerts']} issues found")
    elif choice == '2':
        results = qc_agent.run_quality_check(comprehensive=False)
        print(f"\n✅ Quick check completed: {results['total_alerts']} issues found")
    elif choice == '3':
        dashboard = qc_agent.get_quality_dashboard()
        print(f"\n=== QUALITY DASHBOARD ===")
        print(f"Total Leads: {dashboard['total_leads']}")
        print(f"Total Audits: {dashboard['total_audits']}")
        print(f"Qualified Leads: {dashboard['qualified_leads']}")
        print(f"Total Emails: {dashboard['total_emails']}")
        print(f"Qualification Rate: {dashboard['qualification_rate']:.1%}")
        print(f"Email Coverage: {dashboard['email_coverage']:.1%}")
        print(f"Audit Coverage: {dashboard['audit_coverage']:.1%}")
        print(f"\nRecent 24h Activity:")
        print(f"  Leads: {dashboard['recent_activity']['leads_24h']}")
        print(f"  Audits: {dashboard['recent_activity']['audits_24h']}")
        print(f"  Emails: {dashboard['recent_activity']['emails_24h']}")
        print(f"Recent Alerts: {dashboard['recent_alerts']}")
    elif choice == '4':
        recent_alerts = [a for a in qc_agent.alert_history if a.timestamp > datetime.now() - timedelta(hours=24)]
        if recent_alerts:
            print(f"\n=== RECENT ALERTS (24h) ===")
            for alert in recent_alerts[-10:]:  # Last 10 alerts
                print(f"[{alert.level.value.upper()}] {alert.title}")
                print(f"  {alert.description}")
                print(f"  {alert.timestamp.strftime('%Y-%m-%d %H:%M')}")
                print()
        else:
            print("No recent alerts found")
    else:
        print("Invalid choice")
