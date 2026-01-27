"""
Lead Bucket Definitions for Stage 0: Lead Discovery & Bucket Definition
Defines geographic and industry segments with highest conversion probability
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple
import json

@dataclass
class GeographicSegment:
    """Defines geographic targeting parameters"""
    tier: str  # Tier-1, Tier-2, State-wide
    cities: List[str]
    priority: int  # 1=highest, 5=lowest

@dataclass
class LeadBucket:
    """Defines a lead bucket with industry and geographic focus"""
    name: str
    categories: List[str]
    search_patterns: List[str]  # Search query patterns
    geographic_segments: List[GeographicSegment]
    intent_profile: str  # Description of typical pain points
    conversion_probability: float  # 0.0 to 1.0
    monthly_target: int  # Target leads per month

class LeadBucketManager:
    """Manages lead bucket definitions and targeting strategies"""
    
    def __init__(self):
        self.geographic_focus = self._define_geographic_focus()
        self.buckets = self._define_buckets()
    
    def _define_geographic_focus(self) -> Dict[str, GeographicSegment]:
        """Define Indian geographic segments by priority"""
        return {
            "tier_1_metros": GeographicSegment(
                tier="Tier-1",
                cities=["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune"],
                priority=1
            ),
            "tier_2_cities": GeographicSegment(
                tier="Tier-2", 
                cities=["Ahmedabad", "Jaipur", "Lucknow", "Indore", "Surat", "Nagpur", "Bhopal"],
                priority=2
            ),
            "gujarat_state": GeographicSegment(
                tier="State-wide",
                cities=["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"],
                priority=3
            ),
            "business_districts": GeographicSegment(
                tier="Business Districts",
                cities=["Bandra-Mumbai", "Connaught Place-Delhi", "MG Road-Bangalore", "Banjara Hills-Hyderabad"],
                priority=1
            )
        }
    
    def _define_buckets(self) -> List[LeadBucket]:
        """Define primary lead buckets with targeting parameters"""
        return [
            LeadBucket(
                name="Interior Designers & Architects",
                categories=["Interior Designer", "Architect", "Interior Design Studio", "Architecture Firm"],
                search_patterns=[
                    "Interior Designers {city}",
                    "Interior Design Studio {city}", 
                    "Architects {city}",
                    "Architecture firms {city}",
                    "Home interior designers {city}"
                ],
                geographic_segments=[
                    self.geographic_focus["tier_1_metros"],
                    self.geographic_focus["tier_2_cities"]
                ],
                intent_profile="Many rely on offline portfolio; weak online presence typical; high-value projects",
                conversion_probability=0.75,
                monthly_target=500
            ),
            
            LeadBucket(
                name="Local Service Providers",
                categories=["Plumber", "Electrician", "HVAC Service", "Pest Control", "Cleaning Service"],
                search_patterns=[
                    "Plumbers in {city}",
                    "Electricians {city}",
                    "HVAC services {city}",
                    "Pest control {city}",
                    "Cleaning services {city}",
                    "Home repair services {city}"
                ],
                geographic_segments=[
                    self.geographic_focus["gujarat_state"],
                    self.geographic_focus["tier_2_cities"]
                ],
                intent_profile="Budget-conscious; don't prioritize web; high pain from poor online visibility",
                conversion_probability=0.65,
                monthly_target=2000
            ),
            
            LeadBucket(
                name="Small B2B Agencies", 
                categories=["Event Management", "Photography Studio", "Marketing Consultant", "Graphics Designer"],
                search_patterns=[
                    "Event management companies {city}",
                    "Photography studios {city}",
                    "Marketing consultants {city}",
                    "Graphic designers {city}",
                    "Digital marketing agencies {city}"
                ],
                geographic_segments=[
                    self.geographic_focus["tier_1_metros"],
                    self.geographic_focus["business_districts"]
                ],
                intent_profile="Technical skills vary; often have outdated/poorly maintained sites; need professional image",
                conversion_probability=0.70,
                monthly_target=800
            ),
            
            LeadBucket(
                name="Niche Professional Services",
                categories=["Accountant", "Tax Consultant", "Notary", "Legal Services"],
                search_patterns=[
                    "Chartered accountants {city}",
                    "Tax consultants {city}",
                    "Law firms {city}",
                    "Legal services {city}",
                    "Notary services {city}"
                ],
                geographic_segments=[
                    self.geographic_focus["tier_1_metros"],
                    self.geographic_focus["business_districts"]
                ],
                intent_profile="Conservative but aware of credibility gaps; trust and reputation critical",
                conversion_probability=0.60,
                monthly_target=300
            )
        ]
    
    def get_search_queries(self, bucket_name: str = None) -> List[Dict]:
        """Generate all search queries for targeted scraping"""
        queries = []
        
        buckets_to_search = self.buckets if not bucket_name else [b for b in self.buckets if b.name == bucket_name]
        
        for bucket in buckets_to_search:
            for geo_segment in bucket.geographic_segments:
                for city in geo_segment.cities:
                    for pattern in bucket.search_patterns:
                        query = {
                            "bucket": bucket.name,
                            "category": bucket.categories[0],  # Primary category
                            "query": pattern.format(city=city),
                            "city": city,
                            "tier": geo_segment.tier,
                            "priority": geo_segment.priority,
                            "conversion_probability": bucket.conversion_probability
                        }
                        queries.append(query)
        
        # Sort by priority and conversion probability
        queries.sort(key=lambda x: (x["priority"], -x["conversion_probability"]))
        return queries
    
    def get_bucket_by_category(self, category: str) -> LeadBucket:
        """Find bucket by category name"""
        for bucket in self.buckets:
            if category.lower() in [c.lower() for c in bucket.categories]:
                return bucket
        return None
    
    def calculate_lead_quality_score(self, lead_data: Dict) -> float:
        """Calculate lead quality score based on bucket characteristics"""
        category = lead_data.get('category', '')
        city = lead_data.get('location', '')
        has_website = bool(lead_data.get('website'))
        has_phone = bool(lead_data.get('phone'))
        
        bucket = self.get_bucket_by_category(category)
        if not bucket:
            return 0.3  # Default low score for uncategorized leads
        
        score = bucket.conversion_probability
        
        # Boost for complete information
        if has_website:
            score += 0.1
        if has_phone:
            score += 0.05
            
        # Geographic boost
        for geo_segment in bucket.geographic_segments:
            if city in geo_segment.cities:
                score += (0.1 * (6 - geo_segment.priority)) / 5  # Higher boost for higher priority
                break
        
        return min(score, 1.0)
    
    def export_config(self, filepath: str):
        """Export bucket configuration to JSON"""
        config = {
            "buckets": [
                {
                    "name": bucket.name,
                    "categories": bucket.categories,
                    "search_patterns": bucket.search_patterns,
                    "intent_profile": bucket.intent_profile,
                    "conversion_probability": bucket.conversion_probability,
                    "monthly_target": bucket.monthly_target
                }
                for bucket in self.buckets
            ],
            "geographic_segments": {
                name: {
                    "tier": seg.tier,
                    "cities": seg.cities,
                    "priority": seg.priority
                }
                for name, seg in self.geographic_focus.items()
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)
    
    def get_monthly_targets(self) -> Dict[str, int]:
        """Get monthly lead targets by bucket"""
        return {bucket.name: bucket.monthly_target for bucket in self.buckets}

if __name__ == '__main__':
    # Demo usage
    manager = LeadBucketManager()
    
    print("=== LEAD BUCKETS DEFINED ===")
    for bucket in manager.buckets:
        print(f"\n{bucket.name}:")
        print(f"  Categories: {', '.join(bucket.categories)}")
        print(f"  Conversion Probability: {bucket.conversion_probability:.0%}")
        print(f"  Monthly Target: {bucket.monthly_target}")
        print(f"  Intent: {bucket.intent_profile}")
    
    print("\n=== SAMPLE SEARCH QUERIES ===")
    queries = manager.get_search_queries()[:10]  # First 10 queries
    for query in queries:
        print(f"{query['bucket']} - {query['query']} (Priority: {query['priority']})")
    
    print("\n=== MONTHLY TARGETS ===")
    targets = manager.get_monthly_targets()
    total = sum(targets.values())
    for bucket, target in targets.items():
        print(f"{bucket}: {target} ({target/total:.1%})")
    print(f"Total Monthly Target: {total}")
