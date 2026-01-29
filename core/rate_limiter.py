"""
Rate Limiting and Robots.txt Respect Module
Provides centralized rate limiting and ethical scraping practices
"""

import time
import random
import requests
import re
from urllib.parse import urljoin, urlparse
from typing import Dict, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_second: float
    requests_per_minute: int
    requests_per_hour: int
    burst_allowance: int = 5

class RobotsTxtParser:
    """Parser for robots.txt files"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(hours=1)
    
    def can_scrape(self, url: str, user_agent: str = "*") -> bool:
        """Check if scraping is allowed for the given URL"""
        domain = urlparse(url).netloc
        
        # Check cache first
        if domain in self.cache:
            cached_data, timestamp = self.cache[domain]
            if datetime.now() - timestamp < self.cache_duration:
                return self._check_path_allowed(cached_data, url, user_agent)
        
        # Fetch fresh robots.txt
        robots_url = f"https://{domain}/robots.txt"
        
        try:
            response = requests.get(robots_url, timeout=10)
            if response.status_code == 200:
                robots_content = response.text
                parsed_data = self._parse_robots_txt(robots_content)
                self.cache[domain] = (parsed_data, datetime.now())
                return self._check_path_allowed(parsed_data, url, user_agent)
        except Exception as e:
            print(f"Could not fetch robots.txt for {domain}: {e}")
        
        # Default to allow if robots.txt is not accessible
        return True
    
    def _parse_robots_txt(self, content: str) -> Dict:
        """Parse robots.txt content"""
        parsed = {
            'user_agents': {},
            'global_disallow': [],
            'global_allow': []
        }
        
        current_user_agent = None
        
        for line in content.split('\n'):
            line = line.strip().lower()
            
            if not line or line.startswith('#'):
                continue
            
            if line.startswith('user-agent:'):
                agent = line.split(':', 1)[1].strip()
                if agent == '*':
                    current_user_agent = '*'
                else:
                    current_user_agent = agent
                
                if current_user_agent not in parsed['user_agents']:
                    parsed['user_agents'][current_user_agent] = {
                        'disallow': [],
                        'allow': [],
                        'crawl_delay': None
                    }
            
            elif line.startswith('disallow:'):
                path = line.split(':', 1)[1].strip()
                if current_user_agent:
                    parsed['user_agents'][current_user_agent]['disallow'].append(path)
                else:
                    parsed['global_disallow'].append(path)
            
            elif line.startswith('allow:'):
                path = line.split(':', 1)[1].strip()
                if current_user_agent:
                    parsed['user_agents'][current_user_agent]['allow'].append(path)
                else:
                    parsed['global_allow'].append(path)
            
            elif line.startswith('crawl-delay:'):
                delay = float(line.split(':', 1)[1].strip())
                if current_user_agent:
                    parsed['user_agents'][current_user_agent]['crawl_delay'] = delay
        
        return parsed
    
    def _check_path_allowed(self, robots_data: Dict, url: str, user_agent: str) -> bool:
        """Check if a specific path is allowed"""
        path = urlparse(url).path
        
        # Check specific user agent rules
        if user_agent in robots_data['user_agents']:
            agent_rules = robots_data['user_agents'][user_agent]
            
            # Check disallow rules
            for disallow_path in agent_rules['disallow']:
                if self._path_matches(path, disallow_path):
                    # Check if there's a more specific allow rule
                    for allow_path in agent_rules['allow']:
                        if self._path_matches(path, allow_path) and len(allow_path) > len(disallow_path):
                            return True
                    return False
        
        # Check global rules
        for disallow_path in robots_data['global_disallow']:
            if self._path_matches(path, disallow_path):
                for allow_path in robots_data['global_allow']:
                    if self._path_matches(path, allow_path) and len(allow_path) > len(disallow_path):
                        return True
                return False
        
        return True
    
    def _path_matches(self, path: str, pattern: str) -> bool:
        """Check if path matches robots.txt pattern"""
        if pattern == '/':
            return True
        
        if pattern == '':
            return True
        
        if pattern.endswith('*'):
            return path.startswith(pattern[:-1])
        
        if pattern.startswith('*'):
            return path.endswith(pattern[1:])
        
        if '*' in pattern:
            # Convert to regex
            regex_pattern = pattern.replace('*', '.*')
            return bool(re.match(regex_pattern, path))
        
        return path == pattern

class RateLimiter:
    """Advanced rate limiter with multiple time windows"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.request_times = []
        self.minute_requests = []
        self.hour_requests = []
        self.burst_tokens = config.burst_allowance
        self.last_refill = time.time()
    
    def wait_if_needed(self, user_agent: str = None):
        """Wait if rate limit would be exceeded"""
        current_time = time.time()
        
        # Refill burst tokens
        if current_time - self.last_refill > 1.0:
            self.burst_tokens = min(self.burst_tokens + 1, self.config.burst_allowance)
            self.last_refill = current_time
        
        # Check burst limit
        if self.burst_tokens <= 0:
            sleep_time = 1.0 - (current_time - self.last_refill)
            time.sleep(max(sleep_time, 0.1))
            self.burst_tokens = 1
        
        # Clean old requests
        cutoff_minute = current_time - 60
        cutoff_hour = current_time - 3600
        
        self.minute_requests = [t for t in self.minute_requests if t > cutoff_minute]
        self.hour_requests = [t for t in self.hour_requests if t > cutoff_hour]
        
        # Check minute limit
        if len(self.minute_requests) >= self.config.requests_per_minute:
            oldest_request = min(self.minute_requests)
            sleep_time = 60 - (current_time - oldest_request)
            time.sleep(max(sleep_time, 1))
            return self.wait_if_needed(user_agent)
        
        # Check hour limit
        if len(self.hour_requests) >= self.config.requests_per_hour:
            oldest_request = min(self.hour_requests)
            sleep_time = 3600 - (current_time - oldest_request)
            time.sleep(max(sleep_time, 60))
            return self.wait_if_needed(user_agent)
        
        # Check second limit
        recent_requests = [t for t in self.request_times if current_time - t < 1.0]
        if len(recent_requests) >= self.config.requests_per_second:
            time.sleep(1.0 / self.config.requests_per_second)
        
        # Record this request
        self.request_times.append(current_time)
        self.minute_requests.append(current_time)
        self.hour_requests.append(current_time)
        self.burst_tokens -= 1
        
        # Add random jitter
        jitter = random.uniform(0.1, 0.5)
        time.sleep(jitter)

class EthicalScraper:
    """Combines rate limiting and robots.txt respect for ethical scraping"""
    
    def __init__(self, rate_config: RateLimitConfig):
        self.rate_limiter = RateLimiter(rate_config)
        self.robots_parser = RobotsTxtParser()
        self.session = requests.Session()
        
        # Common user agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]
    
    def can_scrape_url(self, url: str) -> bool:
        """Check if URL can be scraped according to robots.txt"""
        return self.robots_parser.can_scrape(url)
    
    def make_request(self, url: str, method: str = 'GET', **kwargs) -> Optional[requests.Response]:
        """Make an HTTP request with rate limiting and ethical considerations"""
        
        # Check robots.txt
        if not self.can_scrape_url(url):
            print(f"Robots.txt disallows scraping: {url}")
            return None
        
        # Apply rate limiting
        self.rate_limiter.wait_if_needed()
        
        # Set headers
        headers = kwargs.get('headers', {})
        if 'User-Agent' not in headers:
            headers['User-Agent'] = random.choice(self.user_agents)
        
        # Add common headers to appear more legitimate
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        kwargs['headers'] = headers
        kwargs['timeout'] = kwargs.get('timeout', 30)
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"Request failed for {url}: {e}")
            return None
    
    def get_session(self) -> requests.Session:
        """Get the configured session"""
        return self.session

# Predefined rate limit configurations for different sources
RATE_LIMIT_CONFIGS = {
    'google_maps': RateLimitConfig(
        requests_per_second=10,
        requests_per_minute=600,
        requests_per_hour=10000,
        burst_allowance=20
    ),
    'yellow_pages': RateLimitConfig(
        requests_per_second=2,
        requests_per_minute=120,
        requests_per_hour=2000,
        burst_allowance=5
    ),
    'general': RateLimitConfig(
        requests_per_second=1,
        requests_per_minute=60,
        requests_per_hour=1000,
        burst_allowance=5
    )
}

def get_scraper(source: str) -> EthicalScraper:
    """Get a configured scraper for a specific source"""
    config = RATE_LIMIT_CONFIGS.get(source, RATE_LIMIT_CONFIGS['general'])
    return EthicalScraper(config)

if __name__ == '__main__':
    # Demo usage
    print("=== RATE LIMITER AND ROBOTS.TXT DEMO ===")
    
    # Test robots.txt parsing
    parser = RobotsTxtParser()
    
    test_urls = [
        "https://www.google.com/search",
        "https://www.facebook.com/pages",
        "https://example.com/allowed"
    ]
    
    for url in test_urls:
        can_scrape = parser.can_scrape(url)
        print(f"Can scrape {url}: {can_scrape}")
    
    # Test rate limiting
    scraper = get_scraper('general')
    
    print("\nTesting rate limiting (will take a few seconds)...")
    start_time = time.time()
    
    for i in range(3):
        print(f"Request {i+1}...")
        scraper.rate_limiter.wait_if_needed()
        print(f"  Completed at {time.time() - start_time:.2f}s")
    
    print(f"\nTotal time: {time.time() - start_time:.2f}s")
