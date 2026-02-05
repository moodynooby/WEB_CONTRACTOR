"""
Industry Directory Scraper
Targeted scraping from industry-specific directories
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


class IndustryDirectoryScraper(BaseScraper):
    """Industry-specific directory scraper for targeted leads"""

    def __init__(self):
        super().__init__("industry_directory")
        
        # Industry-specific directory mappings
        self.industry_directories = {
            "interior_design": [
                ("ASID", "https://www.asid.org/find-a-pro"),
                ("Interior Designers of Canada", "https://idcanada.org/find-a-designer"),
                ("Elle Decor Directory", "https://www.elledecor.com/directory"),
                ("Architectural Digest", "https://www.architecturaldigest.com/directory"),
            ],
            "web_agency": [
                ("Awwwards", "https://www.awwwards.com/directory/"),
                ("CSS Design Awards", "https://www.cssdesignawards.com/directory/"),
                ("Dribbble", "https://dribbble.com/designers"),
                ("Behance", "https://www.behance.net/directory/"),
            ],
            "local_service": [
                ("Angi (Angie's List)", "https://www.angi.com/"),
                ("HomeAdvisor", "https://www.homeadvisor.com/"),
                ("Thumbtack", "https://www.thumbtack.com/"),
                ("Nextdoor Business", "https://nextdoor.com/business"),
            ],
            "restaurant": [
                ("OpenTable", "https://www.opentable.com/restaurants"),
                ("TripAdvisor Restaurants", "https://www.tripadvisor.com/Restaurants"),
                ("Zomato", "https://www.zomato.com/"),
                ("Yelp Restaurants", "https://www.yelp.com/"),
            ],
            "healthcare": [
                ("Healthgrades", "https://www.healthgrades.com/"),
                ("Zocdoc", "https://www.zocdoc.com/"),
                ("Vitals", "https://www.vitals.com/"),
                ("WebMD Physician Directory", "https://www.webmd.com/"),
            ],
            "legal": [
                ("Martindale-Hubbell", "https://www.martindale.com/"),
                ("Avvo", "https://www.avvo.com/"),
                ("FindLaw", "https://www.findlaw.com/"),
                ("Lawyers.com", "https://www.lawyers.com/"),
            ],
        }

    def scrape_by_category(self, category: str, query: str, location: str, max_results: int = 20) -> List[Dict]:
        """Scrape industry-specific directories for a category"""
        all_results = []
        
        # Get directories for this category
        directories = self.industry_directories.get(category.lower(), [])
        
        if not directories:
            print(f"No specific directories found for category: {category}")
            return all_results
        
        print(f"Scraping {len(directories)} industry directories for {category}")
        
        for directory_name, directory_url in directories:
            print(f"  Scraping {directory_name}...")
            try:
                results = self._scrape_directory(directory_name, directory_url, query, location, max_results)
                all_results.extend(results)
                print(f"    Found {len(results)} results from {directory_name}")
                
                # Delay between directories
                time.sleep(random.uniform(5, 10))
                
            except Exception as e:
                print(f"    Error scraping {directory_name}: {e}")
                continue
        
        return all_results

    def _scrape_directory(self, directory_name: str, directory_url: str, query: str, location: str, max_results: int) -> List[Dict]:
        """Scrape a specific industry directory"""
        self._init_driver()
        results = []
        
        try:
            # Navigate to directory
            self.driver.get(directory_url)
            
            # Handle search functionality if present
            search_query = f"{query} {location}".strip()
            
            # Wait for directory to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".listing, .result, .professional, .business-card"))
                )
            except TimeoutException:
                print(f"    No listings found in {directory_name}")
                return results
            
            # Extract listings
            listings = self.driver.find_elements(
                By.CSS_SELECTOR, 
                ".listing, .result, .professional, .business-card, .directory-item"
            )[:max_results]
            
            for listing in listings:
                try:
                    result = self._parse_directory_listing(listing, query, location, directory_name)
                    if result:
                        results.append(result)
                except Exception as e:
                    print(f"    Error parsing listing: {e}")
                    continue
            
            return results
            
        except Exception as e:
            print(f"    Error scraping directory {directory_name}: {e}")
            return results
        
        finally:
            self._close_driver()

    def _parse_directory_listing(self, listing, query: str, location: str, directory_name: str) -> Optional[Dict]:
        """Parse individual directory listing"""
        try:
            # Business/Professional name
            try:
                name_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    "h3, h4, .name, .title, .professional-name, .business-name"
                )
                business_name = name_elem.text.strip()
            except NoSuchElementException:
                return None
            
            # Contact information
            phone = ""
            website = ""
            email = ""
            address = ""
            
            # Extract contact details using various selectors
            contact_selectors = [
                ".phone", ".contact-phone", ".telephone", ".contact",
                ".website", ".web", ".url",
                ".email", ".e-mail", ".contact-email",
                ".address", ".location", ".street-address"
            ]
            
            for selector in contact_selectors:
                try:
                    element = listing.find_element(By.CSS_SELECTOR, selector)
                    text = element.text.strip()
                    href = element.get_attribute("href") or ""
                    
                    if any(word in selector.lower() for word in ["phone", "tel"]):
                        phone = re.sub(r'[^\d+()-]', '', text)
                    elif any(word in selector.lower() for word in ["email"]):
                        email = text
                    elif any(word in selector.lower() for word in ["web", "url"]):
                        website = href or text
                    elif any(word in selector.lower() for word in ["address", "location"]):
                        address = text
                except NoSuchElementException:
                    continue
            
            # Specialization/Services
            specialization = ""
            try:
                spec_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".specialization, .services, .expertise, .category"
                )
                specialization = spec_elem.text.strip()
            except NoSuchElementException:
                pass
            
            # Rating/Reviews (if available)
            rating = 0
            review_count = 0
            try:
                rating_elem = listing.find_element(
                    By.CSS_SELECTOR, 
                    ".rating, .score, .review-score"
                )
                rating_text = rating_elem.text.strip()
                rating_match = re.search(r'(\d+\.?\d*)', rating_text)
                rating = float(rating_match.group(1)) if rating_match else 0
            except NoSuchElementException:
                pass
            
            # Determine category
            category = specialization or self.determine_category(f"{query} {business_name}")
            
            # Extract city from address
            city = self.extract_city_from_text(address, location)
            
            # Calculate quality score
            quality_score = self.calculate_quality_score({
                "category": category,
                "location": city,
                "website": website,
                "phone": phone,
            })
            
            # Bonus points for professional directories
            if directory_name in ["ASID", "Martindale-Hubbell", "Healthgrades"]:
                quality_score += 0.2  # Professional licensing bodies
            elif directory_name in ["Awwwards", "CSS Design Awards"]:
                quality_score += 0.15  # Industry recognition
            
            if rating >= 4.0:
                quality_score += 0.1
            
            if website and phone:  # Complete contact info
                quality_score += 0.05
            
            # Ensure score doesn't exceed 1.0
            quality_score = min(quality_score, 1.0)
            
            # Determine tier
            if directory_name in ["ASID", "Martindale-Hubbell", "Healthgrades"]:
                tier = "licensed_professional"
            elif directory_name in ["Awwwards", "CSS Design Awards"]:
                tier = "industry_recognized"
            elif rating >= 4.0:
                tier = "highly_rated"
            else:
                tier = "standard"
            
            # Determine priority
            if directory_name in ["ASID", "Martindale-Hubbell"] or (rating >= 4.5 and review_count >= 10):
                priority = "high"
            elif rating >= 4.0:
                priority = "medium"
            else:
                priority = "low"
            
            return {
                "business_name": business_name,
                "phone": phone,
                "website": website,
                "email": email,
                "address": address,
                "city": city,
                "category": category,
                "source": "industry_directory",
                "quality_score": quality_score,
                "directory_source": directory_name,
                "specialization": specialization,
                "rating": rating,
                "review_count": review_count,
                "search_query": query,
                "bucket": "",
                "tier": tier,
                "priority": priority,
            }
            
        except Exception as e:
            print(f"Error parsing directory listing: {e}")
            return None

    def scrape_by_buckets(self, max_queries_per_bucket: int = 15) -> List[Dict]:
        """Scrape industry directories for all bucket queries"""
        all_leads = []
        queries = self.bucket_manager.get_search_queries()
        
        print(f"Starting Industry Directory scraping with {len(queries)} queries...")
        
        for i, query in enumerate(queries):
            city = query.get("city", query.get("location", "Unknown"))
            category = query.get("category", "")
            
            print(f"\n[{i+1}/{len(queries)}] Searching industry directories for: {query['query']} in {city}")
            
            results = self.scrape_by_category(
                category=category,
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
            
            print(f"  Found {len(results)} leads from industry directories")
            
            # Save batch to database
            if results:
                self.save_to_database(results)
            
            # Delay between queries
            if i < len(queries) - 1:
                time.sleep(random.uniform(8, 15))
        
        return all_leads