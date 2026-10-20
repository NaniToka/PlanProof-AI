"""Configuration management for PlanProof AI using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    app_name: str = "PlanProof AI"
    version: str = "0.1.0"
    environment: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Google Gemini API configuration (optional in Milestone 1)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Dataset file paths
    crisis_dataset_path: Path = Path("data/crisis_scenarios.csv")
    budget_splits_path: Path = Path("data/budget_splits.json")
    vendor_checklists_path: Path = Path("data/vendor_checklists.json")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
