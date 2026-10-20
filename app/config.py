"""Application configuration for PlanProof AI using Pydantic Settings."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optional .env file."""

    # Application metadata
    app_name: str = Field(default="PlanProof AI", description="Application name")
    app_env: str = Field(
        default="development", description="Environment mode: development, test, production"
    )
    version: str = Field(default="0.1.0", description="Application semantic version")
    app_host: str = Field(default="0.0.0.0", description="HTTP server bind host")
    app_port: int = Field(default=8000, ge=1, le=65535, description="HTTP server bind port")

    # Google Gemini API configuration
    # Note: Verify exact current model identifier in Google AI Studio (e.g. gemini-2.5-flash)
    gemini_api_key: SecretStr | None = Field(
        default=None,
        description="Gemini API Key (optional during local testing and development)",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Google Gemini model identifier (verify current availability in AI Studio)",
    )
    gemini_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="Timeout in seconds for Gemini API calls",
    )
    gemini_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for transient Gemini API errors (capped at 10)",
    )

    # Dataset paths and storage
    data_dir: Path = Field(
        default=Path("data"),
        description="Root directory for dataset files",
    )
    crisis_dataset_path: Path | None = Field(
        default=None,
        description="Explicit path override for crisis scenarios CSV",
    )
    budget_splits_path: Path | None = Field(
        default=None,
        description="Explicit path override for budget splits JSON",
    )
    vendor_checklists_path: Path | None = Field(
        default=None,
        description="Explicit path override for vendor checklists JSON",
    )

    # Operational limits & caching
    cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="Cache lifetime in seconds for generated plans and responses",
    )
    max_guest_count: int = Field(
        default=2000,
        ge=1,
        description="Maximum supported guest count for events",
    )
    min_event_budget_inr: int = Field(
        default=10000,
        ge=1000,
        description="Minimum event budget in Indian Rupees (INR)",
    )
    max_event_budget_inr: int = Field(
        default=50000000,
        description="Maximum event budget in Indian Rupees (INR) (default: 5 Crore)",
    )
    max_user_text_length: int = Field(
        default=1000,
        ge=10,
        le=10000,
        description="Maximum character length for free-text inputs",
    )

    # CORS origins (typed as list[str] | str to avoid premature json.loads in pydantic-settings)
    allowed_cors_origins: list[str] | str = Field(
        default=["*"],
        description="List of allowed CORS origin URLs or wildcard",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def environment(self) -> str:
        """Backward-compatible alias for app_env."""
        return self.app_env

    def get_gemini_api_key_value(self) -> str | None:
        """Safely expose the raw API key without leaking it in repr/str."""
        return self.gemini_api_key.get_secret_value() if self.gemini_api_key else None

    @field_validator("allowed_cors_origins")
    @classmethod
    def parse_and_validate_cors_origins(cls, value: Any) -> list[str]:
        """Parse comma-separated or JSON list of CORS origins and validate syntax."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        value = parsed
                except json.JSONDecodeError as err:
                    raise ValueError(f"Malformed JSON in CORS origins: {err}") from err
            else:
                value = [item.strip() for item in stripped.split(",") if item.strip()]

        if not isinstance(value, list) or not value:
            raise ValueError(
                "ALLOWED_CORS_ORIGINS must be a non-empty list or comma-separated string"
            )

        validated: list[str] = []
        for origin in value:
            if not isinstance(origin, str) or not origin.strip():
                raise ValueError("CORS origin entries cannot be empty or non-string")
            s = origin.strip()
            if s == "*":
                validated.append("*")
                continue
            parsed_url = urlparse(s)
            if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                raise ValueError(
                    f"Invalid CORS origin '{s}'. Must be '*' or start with 'http://' or 'https://'"
                )
            validated.append(s)

        return validated

    @model_validator(mode="after")
    def validate_budget_and_paths(self) -> "Settings":
        """Validate budget ranges and resolve dataset paths from data_dir."""
        if self.min_event_budget_inr >= self.max_event_budget_inr:
            raise ValueError(
                f"MIN_EVENT_BUDGET_INR ({self.min_event_budget_inr}) must be strictly less than "
                f"MAX_EVENT_BUDGET_INR ({self.max_event_budget_inr})"
            )

        # Resolve dataset paths if not explicitly configured
        if self.crisis_dataset_path is None:
            self.crisis_dataset_path = self.data_dir / "crisis_scenarios.csv"
        if self.budget_splits_path is None:
            self.budget_splits_path = self.data_dir / "budget_splits.json"
        if self.vendor_checklists_path is None:
            self.vendor_checklists_path = self.data_dir / "vendor_checklists.json"

        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
