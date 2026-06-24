"""Configuration schema using Pydantic models."""

from pydantic import BaseModel, Field


class EmailConfig(BaseModel):
    signature: str = "\n\nBest regards,\nWeb Contractor"
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587


class TimeoutsConfig(BaseModel):
    http_request_seconds: int = 15
    page_fetch_seconds: int = 15
    email_scrape_seconds: int = 10


class OllamaConfig(BaseModel):
    model: str = "llama3.2:latest"
    base_url: str = "http://localhost:11434"


class LmStudioConfig(BaseModel):
    model: str = "local-model"
    base_url: str = "http://localhost:1234/v1"
    api_key: str = ""


class VllmConfig(BaseModel):
    model: str = "auto"
    host: str = "localhost"
    port: int = 8000
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.8
    tensor_parallel: int = 1
    enable_auto_tool_choice: bool = True
    tool_call_parser: str | None = None


class LLMConfig(BaseModel):
    provider: str = "vllm"
    timeout_seconds: int = 30
    max_retries: int = 3
    ollama: OllamaConfig = OllamaConfig()
    lm_studio: LmStudioConfig = LmStudioConfig()
    vllm: VllmConfig = VllmConfig()


class ScraperConfig(BaseModel):
    headless: bool = True
    verify_ssl: bool = True
    page_load_timeout_ms: int = 5000
    search_wait_timeout_ms: int = 10000
    result_click_delay_ms: int = 2000
    user_agents: list[str] = Field(
        default_factory=lambda: [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]
    )


class QueryManagementConfig(BaseModel):
    stale_query_threshold: int = 3
    stale_cleanup_days: int = 30


class CityTier(BaseModel):
    tier: str
    cities: list[str]
    priority: int


class GeographicFocusConfig(BaseModel):
    tier_1_metros: CityTier = CityTier(
        tier="Tier-1",
        cities=["Mumbai", "Delhi", "Bangalore", "Chennai", "Kolkata", "Hyderabad", "Pune"],
        priority=1,
    )
    tier_2_cities: CityTier = CityTier(
        tier="Tier-2",
        cities=["Ahmedabad", "Jaipur", "Lucknow", "Indore", "Surat", "Nagpur", "Bhopal"],
        priority=2,
    )
    gujarat_state: CityTier = CityTier(
        tier="State-wide",
        cities=["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar"],
        priority=3,
    )
    business_districts: CityTier = CityTier(
        tier="Business Districts",
        cities=["Bandra-Mumbai", "Connaught Place-Delhi", "MG Road-Bangalore", "Banjara Hills-Hyderabad"],
        priority=1,
    )


class DiscoverySourceConfig(BaseModel):
    enabled: bool = True
    priority: int = 1
    max_results: int = 50
    description: str = ""


class DiscoverySourcesConfig(BaseModel):
    sources: dict[str, DiscoverySourceConfig] = Field(default_factory=dict)


class DiscoveryLimitsConfig(BaseModel):
    max_queries_per_run: int = 500
    max_patterns_per_bucket: int = 30
    max_cities_per_segment: int = 20
    max_results_per_query: int = 50
    max_leads_per_query: int = 20


class ThrottleConfig(BaseModel):
    min_delay_ms: int = 1000
    max_delay_ms: int = 3000
    delay_between_queries_ms: int = 2000


class AntiDetectionConfig(BaseModel):
    enable_throttling: bool = True
    throttle_config: ThrottleConfig = ThrottleConfig()
    enable_captcha_detection: bool = True
    block_patterns: list[str] = Field(
        default_factory=lambda: [
            "captcha",
            "verify you are human",
            "access denied",
            "blocked",
            "unusual traffic",
            "rate limit exceeded",
        ]
    )


class QueryScoringFactors(BaseModel):
    specificity: float = 0.3
    commercial_intent: float = 0.3
    location_specific: float = 0.2
    competition_level: float = 0.2


class QueryScoringConfig(BaseModel):
    enabled: bool = True
    min_score_threshold: float = 0.3
    llm_scoring: bool = True
    historical_weight: float = 0.6
    llm_weight: float = 0.4
    factors: QueryScoringFactors = QueryScoringFactors()


class QueryPerformanceConfig(BaseModel):
    enabled: bool = True
    max_consecutive_failures: int = 3
    auto_disable_stale: bool = True
    review_stale_interval_days: int = 7


class AgentConfig(BaseModel):
    weight: float = 0.3
    system_message: str = ""
    prompt_template: str = ""


class BucketOverride(BaseModel):
    id: str
    type: str
    patterns: list[str]
    description: str
    remediation: str
    severity: str
    score_impact: int


class BusinessAgentConfig(AgentConfig):
    llm_audit: AgentConfig = AgentConfig()
    bucket_overrides: dict[str, list[BucketOverride]] = Field(default_factory=dict)


class PerformanceThresholds(BaseModel):
    max_html_size_kb: int = 100
    max_inline_css_kb: int = 50
    max_inline_js_kb: int = 50
    max_resources: int = 50
    max_response_time_ms: int = 1000


class PerformanceAgentConfig(AgentConfig):
    thresholds: PerformanceThresholds = PerformanceThresholds()


class AgentsConfig(BaseModel):
    execution_order: list[str] = Field(default_factory=lambda: ["content", "business", "technical", "performance"])
    weights: dict[str, float] = Field(default_factory=lambda: {"content": 0.3, "business": 0.3, "technical": 0.25, "performance": 0.15})
    content: AgentConfig = AgentConfig()
    business: BusinessAgentConfig = BusinessAgentConfig()
    technical: AgentConfig = AgentConfig()
    performance: PerformanceAgentConfig = PerformanceAgentConfig()


class EmailGenerationConfig(BaseModel):
    system_message: str = "Write a personalized B2B cold email. Output ONLY valid JSON."
    prompt_template: str = ""


class AppConfig(BaseModel):
    email: EmailConfig = EmailConfig()
    timeouts: TimeoutsConfig = TimeoutsConfig()
    llm: LLMConfig = LLMConfig()
    scraper: ScraperConfig = ScraperConfig()
    query_management: QueryManagementConfig = QueryManagementConfig()
    geographic_focus: GeographicFocusConfig = GeographicFocusConfig()
    discovery_sources: DiscoverySourcesConfig = DiscoverySourcesConfig()
    discovery_limits: DiscoveryLimitsConfig = DiscoveryLimitsConfig()
    anti_detection: AntiDetectionConfig = AntiDetectionConfig()
    query_scoring: QueryScoringConfig = QueryScoringConfig()
    query_performance: QueryPerformanceConfig = QueryPerformanceConfig()
    agents: AgentsConfig = AgentsConfig()
    email_generation: EmailGenerationConfig = EmailGenerationConfig()
