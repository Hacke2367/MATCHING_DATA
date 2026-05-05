from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM keys
    gemini_api_key: str = ""
    anthropic_api_key: str = ""

    # Which LLM provider to use for Tier-2 reasoning ("gemini" | "anthropic")
    llm_provider: str = "gemini"

    # Logging
    log_level: str = "INFO"

    # Scoring thresholds (kept here so they can be overridden via env)
    tier2_lower_bound: float = 0.50
    tier2_upper_bound: float = 0.89
    green_threshold: float = 0.90
    amber_review_lower: float = 0.70
    hard_reject_penalty: float = 100.0
    age_hard_reject_delta: int = 5
    age_full_score_delta: int = 3


settings = Settings()
