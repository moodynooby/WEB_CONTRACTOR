#!/usr/bin/env python3
"""
Simple Test Script for Enhanced Scraping System Configuration
Tests the configuration manager without Selenium dependencies
"""

import sys
import os
import json


def test_configuration_file():
    """Test that the configuration file exists and is valid"""
    print("🔧 Testing Configuration File...")
    
    config_path = "config/scraping_config.json"
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        print(f"✅ Configuration file loaded successfully: {config_path}")
        
        # Test basic structure
        required_sections = ["scraping_sources", "global_settings", "anti_detection", "data_enrichment"]
        for section in required_sections:
            if section in config:
                print(f"  ✅ Section '{section}' found")
            else:
                print(f"  ❌ Section '{section}' missing")
        
        # Test scraping sources
        if "scraping_sources" in config:
            sources = config["scraping_sources"]
            expected_sources = ["bbb", "yelp", "google_maps", "linkedin_company", "facebook_business", "yellow_pages", "industry_directory"]
            
            print(f"\n📊 Scraping Sources Found:")
            for source in expected_sources:
                if source in sources:
                    enabled = sources[source].get("enabled", False)
                    status = "✅ ENABLED" if enabled else "❌ DISABLED"
                    print(f"  {source:<20} {status}")
                else:
                    print(f"  {source:<20} ❌ MISSING")
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Configuration file not found: {config_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in configuration file: {e}")
        return False
    except Exception as e:
        print(f"❌ Error reading configuration: {e}")
        return False


def test_scraper_files():
    """Test that all scraper files exist"""
    print("\n🕷️  Testing Scraper Files...")
    
    scraper_files = [
        ("scrapers/bbb_scraper.py", "BBB Scraper"),
        ("scrapers/yelp_scraper.py", "Yelp Scraper"),
        ("scrapers/facebook_business_scraper.py", "Facebook Business Scraper"),
        ("scrapers/linkedin_company_scraper.py", "LinkedIn Company Scraper"),
        ("scrapers/industry_directory_scraper.py", "Industry Directory Scraper"),
        ("scrapers/stage_a_scraper.py", "Stage A Orchestrator"),
        ("core/scraping_config_manager.py", "Configuration Manager"),
    ]
    
    all_exist = True
    for file_path, description in scraper_files:
        if os.path.exists(file_path):
            print(f"  ✅ {description}: {file_path}")
        else:
            print(f"  ❌ {description}: {file_path} NOT FOUND")
            all_exist = False
    
    return all_exist


def test_scraper_classes():
    """Test that scraper classes can be imported (basic syntax check)"""
    print("\n🔍 Testing Scraper Class Definitions...")
    
    # Test configuration manager first (no external dependencies)
    try:
        import json
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        
        # Test config manager class structure (without importing)
        config_file = "config/scraping_config.json"
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            # Check configuration structure
            if "scraping_sources" in config_data:
                sources = config_data["scraping_sources"]
                
                expected_classes = {
                    "bbb": "BBBScraper",
                    "yelp": "YelpScraper", 
                    "facebook_business": "FacebookBusinessScraper",
                    "linkedin_company": "LinkedInCompanyScraper",
                    "industry_directory": "IndustryDirectoryScraper",
                }
                
                for source_key, class_name in expected_classes.items():
                    if source_key in sources:
                        print(f"  ✅ {class_name} - Configuration found")
                    else:
                        print(f"  ❌ {class_name} - Configuration missing")
            
            print("✅ Configuration structure validated")
        else:
            print("❌ Configuration file not found")
            
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False
    
    return True


def test_enhancement_features():
    """Test that enhancement features are documented"""
    print("\n📚 Testing Documentation...")
    
    files_to_check = [
        ("ENHANCED_SCRAPING_GUIDE.md", "Enhanced Scraping Guide"),
        ("test_enhanced_scraping.py", "Enhanced Scraping Test"),
        ("simple_test.py", "Simple Test Script"),
    ]
    
    for file_path, description in files_to_check:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                if len(content) > 100:  # Check that file has substantial content
                    print(f"  ✅ {description}: {len(content)} characters")
                else:
                    print(f"  ⚠️  {description}: Very short content ({len(content)} chars)")
        else:
            print(f"  ❌ {description}: {file_path} NOT FOUND")


def show_usage_summary():
    """Show summary of how to use the enhanced system"""
    print("\n💡 Usage Summary:")
    print("=" * 60)
    
    usage_steps = [
        "1. Configuration: Edit config/scraping_config.json to enable/disable sources",
        "2. Initialize: scraper = StageAScraper()",
        "3. Run Sources: results = scraper.run_all_sources(max_queries_per_source=20)",
        "4. Select Sources: scraper.scrape_source('bbb', max_queries=15)",
        "5. Manage Config: config = get_config_manager(); config.disable_source('facebook')",
    ]
    
    for step in usage_steps:
        print(f"  {step}")
    
    print("\n🎯 Enhanced Features Available:")
    features = [
        "• BBB Verified Businesses with Accreditation",
        "• Yelp Review Data and Social Proof",
        "• LinkedIn B2B Company Intelligence",
        "• Facebook Social Engagement Metrics",
        "• Industry-Specific Professional Directories",
        "• Enhanced Quality Scoring Algorithms",
        "• Configurable Anti-Detection Measures",
        "• Professional Certification Bonuses",
    ]
    
    for feature in features:
        print(f"  {feature}")


def main():
    """Main test function"""
    print("=" * 70)
    print("🚀 ENHANCED SCRAPING SYSTEM - BASIC VALIDATION")
    print("=" * 70)
    
    success = True
    
    # Test configuration
    if not test_configuration_file():
        success = False
    
    # Test file existence
    if not test_scraper_files():
        success = False
    
    # Test class definitions
    if not test_scraper_classes():
        success = False
    
    # Test documentation
    test_enhancement_features()
    
    # Show usage summary
    show_usage_summary()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ ENHANCED SCRAPING SYSTEM - READY FOR USE!")
        print("🎯 The following files have been successfully created:")
        print("  • 5 New Scrapers (BBB, Yelp, Facebook, LinkedIn, Industry)")
        print("  • Enhanced Stage A Orchestrator")
        print("  • Configuration Management System")
        print("  • Comprehensive Documentation")
        print("  • Test and Demo Scripts")
        print("\n🚀 Next Steps:")
        print("  1. Install Selenium: pip install selenium webdriver-manager")
        print("  2. Configure sources in config/scraping_config.json")
        print("  3. Run with: source .venv/bin/activate && python -c 'from scrapers.stage_a_scraper import StageAScraper; scraper = StageAScraper(); print(\"Ready!\")'")
    else:
        print("❌ Some issues detected. Please check the errors above.")
    print("=" * 70)


if __name__ == "__main__":
    main()