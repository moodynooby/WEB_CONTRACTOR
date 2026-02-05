"""
LinkedIn Company Scraper
B2B focused companies with employee count and industry data
"""

import time
import random
import re
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from scrapers.base_scraper import BaseScraper


class LinkedInCompanyScraper(BaseScraper):
    """LinkedIn company scraper for B2B leads"""

    def __init__(self):
        super().__init__("linkedin_company")
        self.base_url = "https://www.linkedin.com"
        
    def search_companies(
        self, query: str, location: str, max_results: int = 30
    ) -> List[Dict]:
        """Search for companies on LinkedIn"""
        self._init_driver()
        all_results = []
        
        search_query = f"{query} {location}".strip()
        print(f"Searching LinkedIn for: {search_query}")
        
        try:
            # Navigate to LinkedIn company search
            search_url = f"{self.base_url}/search/companies/?keywords={search_query.replace(' ', '%20')}"
            self.driver.get(search_url)
            
            # Wait for search results
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-result, .company-container, .result-item"))
                )
            except TimeoutException:
                print("No results found or timeout occurred")
                return []
            
            # Handle potential login requirements
            if self._check_login_required():
                print("LinkedIn login required. This scraper works best with a LinkedIn account.")
                return []
            
            # Extract company listings
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ".search-result, .company-container, .result-item, .entity-result"
            )[:max_results]
            
            for listing in listings:
                try:
                    company_data = self._parse_linkedin_listing(listing, query, location)
                    if company_data:
                        all_results.append(company_data)
                except Exception as e:
                    print(f"Error parsing LinkedIn listing: {e}")
                    continue
            
            print(f"Found {len(all_results)} companies on LinkedIn")
            return all_results
            
        except Exception as e:
            print(f"LinkedIn search failed: {e}")
            return []
        
        finally:
            if self.driver:
                self.driver.quit()
    
    def _check_login_required(self) -> bool:
        """Check if LinkedIn requires login"""
        try:
            login_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "#login-form, .sign-in-form, .login-required"
            )
            return len(login_elements) > 0
        except:
            return False
    
    def _parse_linkedin_listing(self, listing, query: str, location: str) -> Optional[Dict]:
        """Parse individual LinkedIn company listing"""
        try:
            # Company name
            try:
                name_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    "h3 a, h4 a, .company-name, .entity-name, .result-title a"
                )
                company_name = name_elem.text.strip()
                company_url = name_elem.get_attribute("href")
            except NoSuchElementException:
                return None
            
            # Company description/headline
            try:
                desc_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".company-description, .description, .headline, .subtitle"
                )
                description = desc_elem.text.strip()
            except NoSuchElementException:
                description = ""
            
            # Industry
            try:
                industry_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".industry, .sector, .category"
                )
                industry = industry_elem.text.strip()
            except NoSuchElementException:
                industry = self.determine_category(f"{query} {company_name}")
            
            # Employee count
            try:
                employees_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".employee-count, .employees, .size"
                )
                employees_text = employees_elem.text.strip()
                # Extract numeric value from "51-200 employees" format
                employee_match = re.search(r'(\d+(?:-\d+)?)', employees_text.replace(',', ''))
                employee_count = employee_match.group(1) if employee_match else "Unknown"
            except NoSuchElementException:
                employee_count = "Unknown"
            
            # Company size (extracted from employee count)
            company_size = self._determine_company_size(employee_count)
            
            # Headquarters location
            try:
                location_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".headquarters, .location, .hq"
                )
                headquarters = location_elem.text.strip()
            except NoSuchElementException:
                headquarters = location
            
            # Website
            website = ""
            try:
                website_links = listing.find_elements(
                    By.CSS_SELECTOR, 
                    "a[href^='http']:not([href*='linkedin.com'])"
                )
                if website_links:
                    website = website_links[0].get_attribute("href")
            except:
                pass
            
            # Specialties/Services offered
            try:
                specialties_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".specialties, .services, .keywords"
                )
                specialties = specialties_elem.text.strip()
            except NoSuchElementException:
                specialties = ""
            
            # Founded year
            founded_year = ""
            try:
                founded_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".founded, .established, .year"
                )
                founded_text = founded_elem.text.strip()
                year_match = re.search(r'(\d{4})', founded_text)
                founded_year = year_match.group(1) if year_match else ""
            except NoSuchElementException:
                pass
            
            # Extract city from headquarters
            city = self.extract_city_from_text(headquarters, location)
            
            # Calculate quality score with LinkedIn-specific factors
            quality_score = self.calculate_quality_score({
                "category": industry,
                "location": city,
                "website": website,
            })
            
            # Bonus points for company characteristics
            if company_size in ["Large (1000+)", "Enterprise (5000+)"]:
                quality_score += 0.2
            elif company_size in ["Medium (250-999)", "Large (1000+)"]:
                quality_score += 0.15
            elif company_size == "Small (50-249)":
                quality_score += 0.1
            
            if founded_year and int(founded_year) <= 2010:
                quality_score += 0.05  # Bonus for established companies
            
            if specialties:
                quality_score += 0.05  # Bonus for companies with clear specialties
            
            # Ensure score doesn't exceed 1.0
            quality_score = min(quality_score, 1.0)
            
            # Determine tier based on company size
            if company_size in ["Large (1000+)", "Enterprise (5000+)"]:
                tier = "enterprise"
            elif company_size in ["Medium (250-999)", "Large (1000+)"]:
                tier = "established"
            elif company_size == "Small (50-249)":
                tier = "growing"
            else:
                tier = "startup"
            
            # Determine priority
            if company_size in ["Large (1000+)", "Enterprise (5000+)"]:
                priority = "high"
            elif company_size in ["Medium (250-999)", "Large (1000+)"]:
                priority = "medium"
            else:
                priority = "low"
            
            return {
                "business_name": company_name,
                "phone": "",  # LinkedIn rarely shows phone numbers
                "website": website,
                "address": headquarters,
                "city": city,
                "category": industry,
                "source": "linkedin_company",
                "quality_score": quality_score,
                "employee_count": employee_count,
                "company_size": company_size,
                "founded_year": founded_year,
                "specialties": specialties,
                "description": description,
                "search_query": query,
                "linkedin_url": company_url,
                "bucket": "",
                "tier": tier,
                "priority": priority,
            }
            
        except Exception as e:
            print(f"Error parsing LinkedIn listing: {e}")
            return None
    
    def _determine_company_size(self, employee_count: str) -> str:
        """Determine company size category from employee count"""
        if "Unknown" in employee_count:
            return "Unknown"
        
        # Extract numeric value
        match = re.search(r'(\d+)', employee_count.replace(',', ''))
        if not match:
            return "Unknown"
        
        count = int(match.group(1))
        
        if count >= 5000:
            return "Enterprise (5000+)"
        elif count >= 1000:
            return "Large (1000+)"
        elif count >= 250:
            return "Medium (250-999)"
        elif count >= 50:
            return "Small (50-249)"
        elif count >= 11:
            return "Micro (11-49)"
        else:
            return "Startup (1-10)"
    
    def scrape_by_buckets(self, max_queries_per_bucket: int = 10) -> List[Dict]:
        """Scrape LinkedIn for all bucket queries (limited for B2B focus)"""
        all_leads = []
        queries = self.bucket_manager.get_search_queries()
        
        print(f"Starting LinkedIn Company scraping with {len(queries)} queries...")
        
        for i, query in enumerate(queries):
            city = query.get("city", query.get("location", "Unknown"))
            print(f"\n[{i+1}/{len(queries)}] Searching LinkedIn for: {query['query']} in {city}")
            
            results = self.search_companies(
                query=query["query"], 
                location=city, 
                max_results=15
            )
            
            # Add bucket metadata
            for result in results:
                result["bucket"] = query.get("bucket", "")
                result["tier"] = query.get("tier", "")
                result["priority"] = query.get("priority", "")
                all_leads.append(result)
            
            print(f"  Found {len(results)} LinkedIn companies")
            
            # Save batch to database
            if results:
                self.save_to_database(results)
            
            # Delay between queries (LinkedIn has strict rate limiting)
            if i < len(queries) - 1:
                time.sleep(random.uniform(20, 30))  # Longer delay for LinkedIn
        
        return all_leads