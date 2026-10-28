"""Application configuration for PlanProof AI using Pydantic Settings."""

import ipaddress
import json
import re
import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROCESS_GUEST_SECRET: bytes = secrets.token_bytes(32)


class ConfigurationError(Exception):
    """Raised when an application setting or feature configuration is invalid or missing."""


class AIMode(StrEnum):
    """Supported operational modes for AI-dependent capabilities.

    Modes:
    - auto: Use Gemini when configured and available; otherwise use permitted deterministic fallbacks.
    - demo: Do not call Gemini; use deterministic demo content only.
    - gemini: Require Gemini for AI-dependent operations and return a clear, controlled error when unconfigured.
    """

    AUTO = "auto"
    DEMO = "demo"
    GEMINI = "gemini"


class Settings(BaseSettings):
    """Application settings loaded from environment variables and optional .env file."""

    # Application metadata
    app_name: str = Field(default="PlanProof AI", description="Application name")
    app_env: str = Field(
        default="development",
        validation_alias=AliasChoices("app_env", "environment"),
        description="Environment mode: development, test, production",
    )
    version: str = Field(default="0.1.0", description="Application semantic version")
    app_host: str = Field(default="0.0.0.0", description="HTTP server bind host")
    app_port: int = Field(default=8000, ge=1, le=65535, description="HTTP server bind port")

    # AI Operation Mode
    ai_mode: AIMode = Field(
        default=AIMode.AUTO,
        description=(
            "AI operation mode: 'auto' (use Gemini if available else deterministic fallback), "
            "'demo' (deterministic demo fixtures only), or 'gemini' (strict Gemini required)"
        ),
    )

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

    # Supabase & PostgreSQL Configuration (optional)
    supabase_url: str | None = Field(
        default=None,
        description="Supabase project URL (e.g. https://xyzcompany.supabase.co)",
    )
    supabase_anon_key: SecretStr | None = Field(
        default=None,
        description="Supabase anonymous public API key (client-safe)",
    )
    supabase_jwt_secret: SecretStr | None = Field(
        default=None,
        description="Supabase JWT secret for backend token signature verification",
    )
    supabase_jwt_audience: str = Field(
        default="authenticated",
        description="Expected JWT aud claim for Supabase access tokens",
    )
    supabase_jwt_algorithms: list[str] | str = Field(
        default=["HS256", "RS256", "ES256"],
        description="Allowed JWT signing algorithms (explicit allowlist; 'none' is rejected)",
    )
    supabase_jwt_public_key: SecretStr | None = Field(
        default=None,
        description="Optional PEM-formatted public key for asymmetric JWT verification",
    )
    supabase_jwks_url: str | None = Field(
        default=None,
        description="Explicit JWKS endpoint URL for asymmetric JWT verification",
    )
    supabase_jwt_issuer: str | None = Field(
        default=None,
        description="Expected JWT iss claim (e.g. https://<project>.supabase.co/auth/v1)",
    )
    allow_guest_mode: bool = Field(
        default=True,
        description="Allow unauthenticated guest access for ephemeral in-memory sessions",
    )
    guest_session_secret: SecretStr | None = Field(
        default=None,
        description="Optional secret key for signing ephemeral guest session tokens",
    )
    guest_session_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        description="TTL for ephemeral guest session tokens in seconds (default 24h)",
    )
    database_url: SecretStr | None = Field(
        default=None,
        description="PostgreSQL database connection URL (e.g. Supabase connection pooler)",
    )
    storage_backend: str = Field(
        default="memory",
        description="Event storage repository backend: 'memory' (default) or 'postgres'",
    )
    database_pool_min_size: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Minimum PostgreSQL connection pool size",
    )
    database_pool_max_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum PostgreSQL connection pool size",
    )
    database_connection_timeout: float = Field(
        default=10.0,
        gt=0.0,
        description="Timeout in seconds for establishing PostgreSQL connections",
    )

    # CORS origins (typed as list[str] | str to avoid premature json.loads in pydantic-settings)
    allowed_cors_origins: list[str] | str = Field(
        default=["*"],
        description="List of allowed CORS origin URLs or wildcard",
    )
    trusted_proxies: list[str] | str = Field(
        default=["127.0.0.1", "::1", "localhost", "testclient"],
        description="List of trusted reverse proxy IP addresses or hostnames",
    )
    secure_cookies: bool | None = Field(
        default=None,
        description="Explicit override for Secure attribute on cookies. Defaults to True in production.",
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

    @property
    def is_supabase_configured(self) -> bool:
        """Return True if Supabase project URL and anon key are both configured."""
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def is_database_configured(self) -> bool:
        """Return True if PostgreSQL database URL is configured."""
        return bool(self.database_url)

    @property
    def is_auth_configured(self) -> bool:
        """Return True if any JWT verification method (secret, public key, JWKS, or URL) is set."""
        return bool(
            self.supabase_jwt_secret
            or self.supabase_jwt_public_key
            or self.supabase_jwks_url
            or self.supabase_url
        )

    @property
    def resolved_jwks_url(self) -> str | None:
        """Derive the JWKS endpoint URL from explicit override or supabase_url."""
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        return None

    @property
    def resolved_jwt_issuer(self) -> str | None:
        """Derive expected JWT issuer from explicit override or supabase_url."""
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1"
        return None

    def get_gemini_api_key_value(self) -> str | None:
        """Safely expose the raw API key without leaking it in repr/str."""
        if not self.gemini_api_key:
            return None
        return (
            self.gemini_api_key.get_secret_value()
            if isinstance(self.gemini_api_key, SecretStr)
            else str(self.gemini_api_key)
        )

    def get_supabase_anon_key_value(self) -> str | None:
        """Safely expose raw Supabase anon key without leaking in repr/str."""
        if not self.supabase_anon_key:
            return None
        return (
            self.supabase_anon_key.get_secret_value()
            if isinstance(self.supabase_anon_key, SecretStr)
            else str(self.supabase_anon_key)
        )

    def get_supabase_jwt_secret_value(self) -> str | None:
        """Safely expose raw Supabase JWT secret without leaking in repr/str."""
        if not self.supabase_jwt_secret:
            return None
        return (
            self.supabase_jwt_secret.get_secret_value()
            if isinstance(self.supabase_jwt_secret, SecretStr)
            else str(self.supabase_jwt_secret)
        )

    def get_supabase_jwt_public_key_value(self) -> str | None:
        """Safely expose raw Supabase JWT public key PEM without leaking in repr/str."""
        if not self.supabase_jwt_public_key:
            return None
        return (
            self.supabase_jwt_public_key.get_secret_value()
            if isinstance(self.supabase_jwt_public_key, SecretStr)
            else str(self.supabase_jwt_public_key)
        )

    def get_database_url_value(self) -> str | None:
        """Safely expose raw Database URL without leaking in repr/str."""
        if not self.database_url:
            return None
        return (
            self.database_url.get_secret_value()
            if isinstance(self.database_url, SecretStr)
            else str(self.database_url)
        )

    def get_guest_session_secret_bytes(self) -> bytes:
        """Derive signing key for guest sessions from guest_session_secret, supabase_jwt_secret, or process key."""
        if self.guest_session_secret:
            val = (
                self.guest_session_secret.get_secret_value()
                if isinstance(self.guest_session_secret, SecretStr)
                else str(self.guest_session_secret)
            )
            return val.encode("utf-8")
        if self.supabase_jwt_secret:
            val = (
                self.supabase_jwt_secret.get_secret_value()
                if isinstance(self.supabase_jwt_secret, SecretStr)
                else str(self.supabase_jwt_secret)
            )
            return val.encode("utf-8")
        if self.app_env == "production" or self.storage_backend == "postgres":
            raise ConfigurationError(
                "Ephemeral guest session signing secret is strictly forbidden in production "
                "or PostgreSQL deployments. A stable GUEST_SESSION_SECRET must be configured."
            )
        return _PROCESS_GUEST_SECRET

    @field_validator(
        "gemini_api_key",
        "supabase_url",
        "supabase_anon_key",
        "supabase_jwt_secret",
        "supabase_jwt_public_key",
        "supabase_jwks_url",
        "supabase_jwt_issuer",
        "guest_session_secret",
        "database_url",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        """Convert empty strings, whitespace, and template placeholders to None for optional credentials."""
        if isinstance(value, str):
            val = value.strip()
            if not val:
                return None
            val_lower = val.lower()
            if (
                val_lower in ("your_gemini_api_key_here", "your-gemini-api-key")
                or (val.startswith("<") and val.endswith(">"))
                or val_lower.startswith("your-")
                or val_lower.startswith("your_")
                or "your-project-ref" in val_lower
                or "your-db-password" in val_lower
            ):
                return None
        return value

    @field_validator("supabase_jwt_algorithms", mode="before")
    @classmethod
    def validate_jwt_algorithms(cls, value: Any) -> list[str]:
        """Validate explicit JWT algorithm allowlist, strictly rejecting 'none'."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        value = parsed
                except json.JSONDecodeError as err:
                    raise ValueError(f"Malformed JSON in JWT algorithms: {err}") from err
            else:
                value = [item.strip() for item in stripped.split(",") if item.strip()]

        if not isinstance(value, list) or not value:
            raise ValueError("SUPABASE_JWT_ALGORITHMS must be a non-empty list or comma-separated string")

        validated: list[str] = []
        for alg in value:
            if not isinstance(alg, str) or not alg.strip():
                raise ValueError("JWT algorithm entries cannot be empty or non-string")
            normalized = alg.strip().upper()
            if normalized == "NONE":
                raise ValueError("Unsigned JWT algorithm 'none' is strictly forbidden")
            if normalized not in ("HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"):
                raise ValueError(f"Unsupported JWT signing algorithm: '{normalized}'")
            if normalized not in validated:
                validated.append(normalized)

        return validated

    @field_validator("supabase_url", "supabase_jwks_url")
    @classmethod
    def validate_supabase_url(cls, value: str | None) -> str | None:
        """Validate that Supabase URL starts with http:// or https:// if provided."""
        if value is None:
            return None
        s = value.strip().rstrip("/")
        if not s:
            return None
        parsed = urlparse(s)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid SUPABASE_URL '{s}'. Must start with 'http://' or 'https://'")
        return s

    @field_validator("ai_mode", mode="before")
    @classmethod
    def validate_ai_mode(cls, value: Any) -> AIMode:
        """Validate and normalize AI operation mode ('auto', 'demo', 'gemini')."""
        if isinstance(value, AIMode):
            return value
        if isinstance(value, str):
            cleaned = value.strip().lower()
            try:
                return AIMode(cleaned)
            except ValueError:
                valid_modes = [m.value for m in AIMode]
                raise ValueError(
                    f"Invalid AI_MODE '{value}'. Must be one of: {', '.join(valid_modes)}"
                )
        raise ValueError(f"Invalid AI_MODE '{value}'. Must be a string")

    @field_validator("storage_backend", mode="before")
    @classmethod
    def validate_storage_backend(cls, value: Any) -> str:
        """Validate and normalize storage backend option ('memory' or 'postgres')."""
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned not in ("memory", "postgres"):
                raise ValueError(
                    f"Invalid STORAGE_BACKEND '{value}'. Must be 'memory' or 'postgres'"
                )
            return cleaned
        raise ValueError(f"Invalid STORAGE_BACKEND '{value}'. Must be a string")

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

    @field_validator("guest_session_secret")
    @classmethod
    def validate_guest_session_secret(cls, value: Any) -> SecretStr | None:
        """Validate guest session signing secret length."""
        if value is None:
            return None
        val_str = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        if len(val_str) < 32:
            raise ValueError(
                "GUEST_SESSION_SECRET must be at least 32 characters long for cryptographic security"
            )
        return value if isinstance(value, SecretStr) else SecretStr(val_str)

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, value: Any) -> list[str]:
        """Parse trusted proxy entries into a clean, validated list of hostnames, IP addresses, or CIDR ranges."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        value = parsed
                except json.JSONDecodeError as err:
                    raise ValueError(f"Malformed JSON in trusted proxies: {err}") from err
            else:
                value = [item.strip() for item in stripped.split(",") if item.strip()]
        if not isinstance(value, list) or not value:
            return ["127.0.0.1", "::1", "localhost", "testclient"]

        validated: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Trusted proxy entries cannot be empty or non-string")
            s = item.strip()
            if s in ("0.0.0.0/0", "::/0"):
                raise ValueError(
                    f"Wildcard proxy entry '{s}' is prohibited in TRUSTED_PROXIES for security."
                )

            # 1. Check if entry is a valid IP address or CIDR network
            try:
                ipaddress.ip_network(s, strict=False)
                if s not in validated:
                    validated.append(s)
                continue
            except ValueError:
                pass

            # If it contained slashes or colons, or all parts are digits, it was meant to be an IP/CIDR
            if "/" in s or ":" in s or all(part.isdigit() for part in s.split(".")):
                raise ValueError(
                    f"Invalid IP address or CIDR range in TRUSTED_PROXIES: '{s}'"
                )

            # 2. Check if entry is a valid hostname (e.g. localhost, testclient)
            if re.match(
                r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$",
                s,
            ):
                parts = s.split(".")
                if len(parts) > 1 and parts[-1].isdigit():
                    raise ValueError(f"Invalid hostname with numeric TLD in TRUSTED_PROXIES: '{s}'")
                if s not in validated:
                    validated.append(s)
                continue

            raise ValueError(
                f"Invalid trusted proxy entry: '{s}'. Must be a valid IP address, CIDR range, or hostname."
            )

        return validated

    @model_validator(mode="after")
    def validate_budget_and_paths(self) -> "Settings":
        """Validate budget ranges, production security requirements, and dataset paths."""
        if self.min_event_budget_inr >= self.max_event_budget_inr:
            raise ValueError(
                f"MIN_EVENT_BUDGET_INR ({self.min_event_budget_inr}) must be strictly less than "
                f"MAX_EVENT_BUDGET_INR ({self.max_event_budget_inr})"
            )

        # Production security policy enforcement
        if self.app_env == "production":
            if self.secure_cookies is False:
                raise ValueError("Insecure cookies (secure_cookies=False) are strictly forbidden in production")
            if self.allow_guest_mode and not self.guest_session_secret:
                raise ValueError(
                    "Production deployments with guest mode enabled require an explicit, stable "
                    "GUEST_SESSION_SECRET of at least 32 characters to support multi-worker environments."
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
