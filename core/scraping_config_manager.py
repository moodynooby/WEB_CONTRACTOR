"""
Scraping Configuration Manager
Handles loading and managing configuration for enhanced scraping sources
"""

import json
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ScrapingSourceConfig:
    """Configuration for individual scraping sources"""
    enabled: bool
    priority: int
    max_queries_per_bucket: int
    description: str
    anti_bot_level: str
    rate_limit_delay: Dict[str, int]
    quality_bonus: Dict[str, float]


@dataclass
class GlobalSettings:
    """Global scraping settings"""
    max_concurrent_scrapers: int
    database_batch_size: int
    enable_error_recovery: bool
    retry_failed_queries: bool
    max_retries: int
    deduplication_enabled: bool
    quality_score_weighting: Dict[str, float]


@dataclass
class AntiDetectionSettings:
    """Anti-detection and stealth configuration"""
    user_agent_rotation: bool
    proxy_rotation: bool
    stealth_mode: bool
    random_delays: bool
    human_like_scrolling: bool
    captcha_handling: Dict[str, bool]


@dataclass
class DataEnrichmentSettings:
    """Data enrichment features"""
    email_extraction: bool
    social_media_links: bool
    business_hours: bool
    employee_count: bool
    revenue_estimates: bool
    technology_stack: bool


class ScrapingConfigManager:
    """Manager for scraping configuration and settings"""
    
    def __init__(self, config_path: str = "config/scraping_config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        
    def _load_config(self) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Config file {self.config_path} not found. Using defaults.")
            return self._get_default_config()
        except json.JSONDecodeError:
            print(f"Invalid JSON in config file {self.config_path}. Using defaults.")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Return default configuration"""
        return {
            "scraping_sources": {},
            "global_settings": {
                "max_concurrent_scrapers": 1,
                "database_batch_size": 50,
                "enable_error_recovery": True,
                "retry_failed_queries": True,
                "max_retries": 3,
                "deduplication_enabled": True,
                "quality_score_weighting": {
                    "source_reliability": 0.4,
                    "business_verification": 0.3,
                    "contact_completeness": 0.2,
                    "social_proof": 0.1
                }
            },
            "anti_detection": {
                "user_agent_rotation": True,
                "proxy_rotation": False,
                "stealth_mode": True,
                "random_delays": True,
                "human_like_scrolling": True,
                "captcha_handling": {
                    "auto_solve": False,
                    "notify_user": True
                }
            },
            "data_enrichment": {
                "email_extraction": True,
                "social_media_links": True,
                "business_hours": True,
                "employee_count": True,
                "revenue_estimates": False,
                "technology_stack": False
            }
        }
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to {self.config_path}")
        except Exception as e:
            print(f"Error saving configuration: {e}")
    
    def get_enabled_sources(self) -> List[str]:
        """Get list of enabled scraping sources in priority order"""
        sources = []
        if "scraping_sources" not in self.config:
            return sources
            
        for source_name, source_config in self.config["scraping_sources"].items():
            if source_config.get("enabled", False):
                sources.append((source_name, source_config.get("priority", 999)))
        
        # Sort by priority
        sources.sort(key=lambda x: x[1])
        return [source[0] for source in sources]
    
    def get_source_config(self, source_name: str) -> Optional[ScrapingSourceConfig]:
        """Get configuration for a specific source"""
        if "scraping_sources" not in self.config:
            return None
            
        source_config = self.config["scraping_sources"].get(source_name)
        if not source_config:
            return None
            
        return ScrapingSourceConfig(**source_config)
    
    def get_global_settings(self) -> GlobalSettings:
        """Get global scraping settings"""
        return GlobalSettings(**self.config.get("global_settings", {}))
    
    def get_anti_detection_settings(self) -> AntiDetectionSettings:
        """Get anti-detection settings"""
        return AntiDetectionSettings(**self.config.get("anti_detection", {}))
    
    def get_data_enrichment_settings(self) -> DataEnrichmentSettings:
        """Get data enrichment settings"""
        return DataEnrichmentSettings(**self.config.get("data_enrichment", {}))
    
    def enable_source(self, source_name: str):
        """Enable a scraping source"""
        if source_name in self.config.get("scraping_sources", {}):
            self.config["scraping_sources"][source_name]["enabled"] = True
            print(f"Enabled source: {source_name}")
    
    def disable_source(self, source_name: str):
        """Disable a scraping source"""
        if source_name in self.config.get("scraping_sources", {}):
            self.config["scraping_sources"][source_name]["enabled"] = False
            print(f"Disabled source: {source_name}")
    
    def update_source_settings(self, source_name: str, settings: Dict):
        """Update settings for a specific source"""
        if source_name not in self.config.get("scraping_sources", {}):
            print(f"Source {source_name} not found in configuration")
            return
            
        self.config["scraping_sources"][source_name].update(settings)
        print(f"Updated settings for source: {source_name}")
    
    def get_source_delay_range(self, source_name: str) -> tuple:
        """Get delay range for a specific source"""
        source_config = self.get_source_config(source_name)
        if not source_config or not source_config.rate_limit_delay:
            return (5, 10)  # Default delay
            
        delay_config = source_config.rate_limit_delay
        return (delay_config.get("min_seconds", 5), delay_config.get("max_seconds", 10))
    
    def get_quality_bonus(self, source_name: str) -> Dict[str, float]:
        """Get quality bonus configuration for a source"""
        source_config = self.get_source_config(source_name)
        return source_config.quality_bonus if source_config else {}
    
    def print_config_summary(self):
        """Print a summary of the current configuration"""
        print(f"\n{'=' * 60}")
        print("ENHANCED SCRAPING CONFIGURATION SUMMARY")
        print(f"{'=' * 60}")
        
        # Sources summary
        print(f"\n📊 SCRAPING SOURCES:")
        enabled_sources = self.get_enabled_sources()
        for i, source in enumerate(enabled_sources, 1):
            config = self.get_source_config(source)
            if config:
                print(f"  {i}. {source.replace('_', ' ').title()}")
                print(f"     Priority: {config.priority}")
                print(f"     Queries/Bucket: {config.max_queries_per_bucket}")
                print(f"     Anti-bot Level: {config.anti_bot_level}")
                print(f"     {config.description}")
                print()
        
        # Global settings summary
        global_settings = self.get_global_settings()
        print(f"⚙️  GLOBAL SETTINGS:")
        print(f"  Max Concurrent: {global_settings.max_concurrent_scrapers}")
        print(f"  Batch Size: {global_settings.database_batch_size}")
        print(f"  Error Recovery: {global_settings.enable_error_recovery}")
        print(f"  Deduplication: {global_settings.deduplication_enabled}")
        
        print(f"{'=' * 60}")
        print(f"Total Enabled Sources: {len(enabled_sources)}")
        print(f"{'=' * 60}")


# Global instance for easy access
config_manager = ScrapingConfigManager()


def get_config_manager() -> ScrapingConfigManager:
    """Get the global configuration manager instance"""
    return config_manager


def get_enabled_scraping_sources() -> List[str]:
    """Get list of enabled scraping sources"""
    return config_manager.get_enabled_sources()


def get_scraping_config(source_name: str) -> Optional[ScrapingSourceConfig]:
    """Get configuration for a specific scraping source"""
    return config_manager.get_source_config(source_name)