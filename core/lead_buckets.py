"""
Lead Bucket Definitions for Stage 0: Lead Discovery & Bucket Definition
Defines geographic and industry segments with highest conversion probability
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
import json
import random
import os
from datetime import datetime


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

    def __init__(self, config_file: Optional[str] = None):
        self.config_dir = os.path.join(os.getcwd(), "config")
        self.bucket_config_file = os.path.join(self.config_dir, "buckets.json")

        # Load config
        try:
            with open(self.bucket_config_file, "r") as f:
                self.config_data = json.load(f)
        except FileNotFoundError:
            print(
                f"Warning: Config file not found at {self.bucket_config_file}. Using empty defaults."
            )
            self.config_data = {"geographic_focus": {}, "buckets": []}

        self.config_file = config_file or os.path.join(
            self.config_dir, "dynamic_terms.json"
        )
        self.geographic_focus = self._load_geographic_focus()
        self.buckets = self._load_buckets()
        self.dynamic_search_terms = self._load_dynamic_terms()

    def _load_geographic_focus(self) -> Dict[str, GeographicSegment]:
        """Load geographic segments from config"""
        focus = {}
        for key, data in self.config_data.get("geographic_focus", {}).items():
            focus[key] = GeographicSegment(
                tier=data["tier"], cities=data["cities"], priority=data["priority"]
            )
        return focus

    def _load_buckets(self) -> List[LeadBucket]:
        """Load lead buckets from config"""
        buckets = []
        for data in self.config_data.get("buckets", []):
            # Map geographic segment names to actual objects
            geo_segments = []
            for seg_name in data.get("geographic_segments", []):
                if seg_name in self.geographic_focus:
                    geo_segments.append(self.geographic_focus[seg_name])

            buckets.append(
                LeadBucket(
                    name=data["name"],
                    categories=data["categories"],
                    search_patterns=data["search_patterns"],
                    geographic_segments=geo_segments,
                    intent_profile=data["intent_profile"],
                    conversion_probability=data["conversion_probability"],
                    monthly_target=data["monthly_target"],
                )
            )
        return buckets

    def get_search_queries(
        self, bucket_name: str = None, dynamic: bool = True
    ) -> List[Dict]:
        """Generate search queries with optional dynamic variations and bucket filtering"""
        queries = []

        buckets_to_search = (
            self.buckets
            if not bucket_name
            else [b for b in self.buckets if b.name == bucket_name]
        )

        for bucket in buckets_to_search:
            for geo_segment in bucket.geographic_segments:
                for city in geo_segment.cities:
                    for pattern in bucket.search_patterns:
                        base_query = pattern.format(city=city)

                        if dynamic:
                            # Generate dynamic variations
                            variations = self.generate_dynamic_queries(base_query, city)
                            for var_query in variations:
                                query = {
                                    "bucket": bucket.name,
                                    "category": bucket.categories[0],
                                    "query": var_query,
                                    "city": city,
                                    "tier": geo_segment.tier,
                                    "priority": geo_segment.priority,
                                    "conversion_probability": bucket.conversion_probability,
                                    "is_dynamic": var_query != base_query,
                                }
                                queries.append(query)
                        else:
                            # Original static queries
                            query = {
                                "bucket": bucket.name,
                                "category": bucket.categories[0],
                                "query": base_query,
                                "city": city,
                                "tier": geo_segment.tier,
                                "priority": geo_segment.priority,
                                "conversion_probability": bucket.conversion_probability,
                                "is_dynamic": False,
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
        category = lead_data.get("category", "")
        city = lead_data.get("location", "")
        has_website = bool(lead_data.get("website"))
        has_phone = bool(lead_data.get("phone"))

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
                score += (
                    0.1 * (6 - geo_segment.priority)
                ) / 5  # Higher boost for higher priority
                break

        return min(score, 1.0)

    def _load_dynamic_terms(self) -> Dict[str, List[str]]:
        """Load dynamic search terms from config or generate defaults"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f).get("dynamic_terms", {})
            except Exception as e:
                print(f"Error loading config: {e}")

        # Default dynamic terms
        return {
            "qualifiers": [
                "best",
                "top rated",
                "professional",
                "affordable",
                "expert",
                "local",
                "near me",
                "certified",
                "licensed",
                "experienced",
            ],
            "business_types": [
                "small business",
                "startup",
                "company",
                "firm",
                "agency",
                "service",
                "provider",
                "consultant",
                "specialist",
                "expert",
            ],
            "location_modifiers": [
                "downtown",
                "city center",
                "main street",
                "commercial area",
                "business district",
                "industrial area",
                "tech park",
                "market area",
            ],
        }

    def generate_dynamic_queries(
        self, base_query: str, city: str, max_variations: int = 3
    ) -> List[str]:
        """Generate dynamic variations of search queries"""
        variations = [base_query]

        # Add qualifiers
        if random.random() < 0.7:  # 70% chance to add qualifier
            qualifier = random.choice(self.dynamic_search_terms["qualifiers"])
            variations.append(f"{qualifier} {base_query}")

        # Add business type modifiers
        if random.random() < 0.5:  # 50% chance to add business type
            business_type = random.choice(self.dynamic_search_terms["business_types"])
            variations.append(f"{base_query} {business_type}")

        # Add location modifiers
        if random.random() < 0.3:  # 30% chance to add location modifier
            location_mod = random.choice(
                self.dynamic_search_terms["location_modifiers"]
            )
            variations.append(f"{base_query} {location_mod} {city}")

        return variations[:max_variations]

    def add_dynamic_term(self, category: str, term: str) -> None:
        """Add a new dynamic term to the configuration"""
        if category not in self.dynamic_search_terms:
            self.dynamic_search_terms[category] = []
        if term not in self.dynamic_search_terms[category]:
            self.dynamic_search_terms[category].append(term)
            self._save_config()

    def _save_config(self) -> None:
        """Save current configuration to file"""
        config = {
            "dynamic_terms": self.dynamic_search_terms,
            "last_updated": datetime.now().isoformat(),
        }
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_random_city_sample(self, count: int = 5) -> List[str]:
        """Get random sample of cities for testing"""
        all_cities = []
        for segment in self.geographic_focus.values():
            all_cities.extend(segment.cities)
        return random.sample(all_cities, min(count, len(all_cities)))

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
                    "monthly_target": bucket.monthly_target,
                }
                for bucket in self.buckets
            ],
            "geographic_segments": {
                name: {"tier": seg.tier, "cities": seg.cities, "priority": seg.priority}
                for name, seg in self.geographic_focus.items()
            },
        }

        with open(filepath, "w") as f:
            json.dump(config, f, indent=2)

    def get_monthly_targets(self) -> Dict[str, int]:
        """Get monthly lead targets by bucket"""
        return {bucket.name: bucket.monthly_target for bucket in self.buckets}
