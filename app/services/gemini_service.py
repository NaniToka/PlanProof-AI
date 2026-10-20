"""Gemini AI service for PlanProof AI using the official google-genai SDK.

Provides a reliable, asynchronous, secure, and testable interface for structured
JSON content generation.

Retry Behavior Documentation:
------------------------------
- SDK-level retries: Disabled (`retry_options=None` in `HttpOptions`).
- Application-level retries: Fully handled by `GeminiService.generate_structured_content`.
  - Transient errors (HTTP 429 rate limits, HTTP 500/502/503/504 server errors, network drops)
    are retried up to `gemini_max_retries` with capped exponential backoff.
  - Permanent errors (HTTP 400 bad request, 401/403 authentication/authorization, 404 not found)
    fail immediately without retry.
  - Validation failures and malformed JSON are never retried.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, TypeVar

from google.genai import Client, errors, types
from pydantic import BaseModel, SecretStr, ValidationError

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ==============================================================================
# Domain Exceptions
# ==============================================================================


class GeminiError(Exception):
    """Base exception for Gemini service operations."""


class GeminiNotConfiguredError(GeminiError):
    """Raised when Gemini API key is missing or unconfigured."""


class GeminiTimeoutError(GeminiError):
    """Raised when a Gemini API request exceeds the configured timeout."""


class GeminiProviderError(GeminiError):
    """Raised when upstream Gemini API encounters a provider or network failure."""


class GeminiRateLimitError(GeminiProviderError):
    """Raised when upstream Gemini API rate limits or quota are exceeded."""


class GeminiInvalidOutputError(GeminiError):
    """Raised when Gemini returns malformed JSON or schema-incompatible output."""


# ==============================================================================
# Helper Functions
# ==============================================================================


def clean_json_markdown(text: str) -> str:
    """Strip optional markdown code block fencing (e.g. ```json ... ```) from model output."""
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", stripped, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return stripped


# ==============================================================================
# Gemini Service
# ==============================================================================


class GeminiService:
    """Asynchronous client service for Google Gemini using the official google-genai SDK."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: Any | None = None,
        retry_backoff_base: float = 0.5,
    ) -> None:
        """Initialize the Gemini service with application settings and an optional mock client."""
        self.settings = settings or get_settings()
        self.model_name = self.settings.gemini_model
        self.timeout_seconds = self.settings.gemini_timeout_seconds
        self.max_retries = self.settings.gemini_max_retries
        self.retry_backoff_base = retry_backoff_base

        if client is not None:
            self._client = client
            self.is_configured = True
        elif self.settings.gemini_api_key is not None:
            raw_key = (
                self.settings.gemini_api_key.get_secret_value()
                if isinstance(self.settings.gemini_api_key, SecretStr)
                else str(self.settings.gemini_api_key)
            )
            if raw_key.strip():
                # Configure official Client with explicit timeout in milliseconds
                http_options = types.HttpOptions(timeout=int(self.timeout_seconds * 1000))
                self._client = Client(api_key=raw_key.strip(), http_options=http_options)
                self.is_configured = True
            else:
                self._client = None
                self.is_configured = False
        else:
            self._client = None
            self.is_configured = False

    async def generate_structured_content(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> T:
        """Request structured JSON output from Gemini and validate against a Pydantic schema."""
        if not self.is_configured or self._client is None:
            raise GeminiNotConfiguredError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in environment or .env file."
            )

        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty or blank.")

        if len(prompt) > self.settings.max_user_text_length:
            raise ValueError(
                f"Prompt length ({len(prompt)}) exceeds maximum limit of "
                f"{self.settings.max_user_text_length} characters."
            )

        if not (isinstance(response_schema, type) and issubclass(response_schema, BaseModel)):
            raise TypeError("response_schema must be a subclass of pydantic.BaseModel.")

        # Build official GenerateContentConfig with structured output
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            system_instruction=system_instruction,
            temperature=0.2,
        )

        attempts = 0
        max_attempts = self.max_retries + 1
        backoff_cap = 4.0
        response = None

        while attempts < max_attempts:
            attempts += 1
            try:
                # Enforce bounded timeout on async call
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self._client.aio.models.generate_content(
                        model=self.model_name,
                        contents=prompt,
                        config=config,
                    )
                break
            except TimeoutError as err:
                if attempts >= max_attempts:
                    logger.error(
                        "Gemini request timed out after %d attempts (timeout=%.1fs)",
                        attempts,
                        self.timeout_seconds,
                    )
                    raise GeminiTimeoutError(
                        f"Gemini request timed out after {self.timeout_seconds} seconds."
                    ) from err
                delay = min(self.retry_backoff_base * (2 ** (attempts - 1)), backoff_cap)
                logger.warning(
                    "Gemini request timed out on attempt %d/%d; retrying in %.2fs",
                    attempts,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
            except errors.APIError as err:
                status_code = getattr(err, "code", None)
                # Non-retriable client errors (400, 401, 403, 404)
                if status_code in (400, 401, 403, 404):
                    logger.error("Non-retryable client error from Gemini API: code %s", status_code)
                    raise GeminiProviderError(
                        f"Gemini API client error (status {status_code})."
                    ) from err

                # Rate limiting (429)
                if status_code == 429:
                    if attempts >= max_attempts:
                        logger.error("Gemini rate limit exceeded after %d attempts", attempts)
                        raise GeminiRateLimitError(
                            "Gemini API rate limit exceeded. Please try again later."
                        ) from err
                    delay = min(self.retry_backoff_base * (2 ** (attempts - 1)), backoff_cap)
                    logger.warning(
                        "Gemini API rate limit (429) on attempt %d/%d; backoff %.2fs",
                        attempts,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Transient server errors (500, 502, 503, 504) or ServerError
                if status_code in (500, 502, 503, 504) or isinstance(err, errors.ServerError):
                    if attempts >= max_attempts:
                        logger.error(
                            "Gemini server error (%s) after %d attempts", status_code, attempts
                        )
                        raise GeminiProviderError(
                            f"Gemini server error ({status_code}) after {attempts} attempts."
                        ) from err
                    delay = min(self.retry_backoff_base * (2 ** (attempts - 1)), backoff_cap)
                    logger.warning(
                        "Gemini server error (%s) on attempt %d/%d; backoff %.2fs",
                        status_code,
                        attempts,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Any other unclassified API error
                raise GeminiProviderError(
                    f"Gemini API request failed with status {status_code}."
                ) from err
            except Exception as err:
                err_name = type(err).__name__
                if any(x in err_name for x in ("Connect", "Transport", "Network")):
                    if attempts >= max_attempts:
                        raise GeminiProviderError(
                            f"Gemini network connection failure after {attempts} attempts."
                        ) from err
                    delay = min(self.retry_backoff_base * (2 ** (attempts - 1)), backoff_cap)
                    await asyncio.sleep(delay)
                    continue
                logger.error("Unexpected error during Gemini call: %s", err, exc_info=True)
                raise GeminiProviderError(
                    "Unexpected failure communicating with Gemini service."
                ) from err

        if response is None:
            raise GeminiProviderError("Failed to receive a valid response from Gemini.")

        # Check if already parsed directly into the expected Pydantic model
        if hasattr(response, "parsed") and isinstance(response.parsed, response_schema):
            return response.parsed

        raw_text = getattr(response, "text", None)
        if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
            raise GeminiInvalidOutputError("Gemini returned empty or blank text.")

        cleaned_text = clean_json_markdown(raw_text)

        try:
            return response_schema.model_validate_json(cleaned_text)
        except (ValidationError, ValueError, json.JSONDecodeError) as err:
            logger.warning(
                "Failed to parse Gemini output against schema %s: %s",
                response_schema.__name__,
                err,
            )
            raise GeminiInvalidOutputError(
                f"Gemini output could not be validated against {response_schema.__name__}: {err}"
            ) from err
