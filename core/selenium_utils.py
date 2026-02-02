import random
import time
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from loguru import logger

class SeleniumDriverFactory:
    """Factory for creating standardized Selenium WebDrivers"""
    
    @staticmethod
    def create_driver(headless: bool = True) -> Optional[webdriver.Chrome]:
        """Create a configured Chrome WebDriver"""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--ignore-certificate-errors")
            
            # Use random user agent
            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
            chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
            
            # Suppress logging
            chrome_options.add_argument("--log-level=3")
            
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set default timeouts
            driver.set_page_load_timeout(30)
            
            return driver
        except Exception as e:
            logger.error(f"Failed to create Selenium driver: {e}")
            return None

    @staticmethod
    def safe_close(driver):
        """Safely close a driver instance"""
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logger.warning(f"Error closing driver: {e}")
