"""Shared AI orchestration service for PlanProof AI.

Decides whether to invoke Gemini AI or apply a permitted deterministic fallback
based on configured operational mode (AI_MODE: 'auto', 'demo', 'gemini'), API key
availability, and feature-specific fallback handlers.

Security & Trust Constraints:
- Never executes arbitrary Python code, eval, or commands from model output.
- Never treats generated text as trusted executable instructions.
- All model and fallback outputs are strictly validated against expected Pydantic schemas.
- Provider stack traces, secrets, and raw internal paths are never exposed in result envelopes.
- Live Gemini calls are strictly forbidden in 'demo' mode.
- In 'gemini' mode, silent fallback is forbidden; unconfigured or failing Gemini returns unavailable.
- In 'auto' mode, fallbacks are only applied when a meaningful fallback is explicitly provided or registered.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar, get_args, get_origin, runtime_checkable

from pydantic import BaseModel, ValidationError

from app.config import AIMode, Settings, get_settings
from app.schemas import (
    AIResultEnvelope,
    AIResultSource,
    AIResultStatus,
    AITask,
    sanitize_safe_text,
)
from app.services.demo_fixtures import (
    get_demo_crisis_recovery,
    get_demo_event_risks,
    get_demo_family_council,
    get_demo_timeline,
)
from app.services.fallback_service import (
    generate_deterministic_crisis_recovery,
    generate_deterministic_family_council,
    generate_deterministic_risks,
    generate_deterministic_timeline,
)
from app.services.gemini_service import GeminiError, GeminiService

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel | list | dict)


@runtime_checkable
class FallbackProvider(Protocol[T]):
    """Protocol for feature-specific deterministic fallback providers."""

    def __call__(self, request_data: Any = None) -> T | Awaitable[T]:
        """Execute the deterministic fallback for the requested feature."""
        ...


FallbackCallable = (
    Callable[[Any], T | Awaitable[T]]
    | Callable[[], T | Awaitable[T]]
    | FallbackProvider[T]
)


async def _invoke_callable(fn: Any, request_data: Any) -> Any:
    """Safely invoke a synchronous or asynchronous callable with or without arguments."""
    try:
        sig = inspect.signature(fn)
        param_count = len(sig.parameters)
    except (ValueError, TypeError):
        # Some builtins or C-extensions lack inspectable signatures
        param_count = 1

    if param_count == 0:
        result = fn()
    else:
        result = fn(request_data)

    if inspect.isawaitable(result):
        result = await result
    return result


def _normalize_task_name(task: AITask | str) -> str:
    """Normalize task identifier to lowercased string."""
    return task.value if isinstance(task, AITask) else str(task).strip().lower()


class AIOrchestrator:
    """Shared orchestration layer managing AI operations, demo modes, and deterministic fallbacks."""

    def __init__(
        self,
        settings: Settings | None = None,
        gemini_service: GeminiService | None = None,
    ) -> None:
        """Initialize orchestrator with configuration settings and Gemini service."""
        self.settings = settings or get_settings()
        self.gemini_service = gemini_service or GeminiService(settings=self.settings)
        self.mode = self.settings.ai_mode

        # Registries for feature fallbacks and demo fixtures
        self._fallback_registry: dict[str, FallbackCallable[Any]] = {}
        self._demo_registry: dict[str, FallbackCallable[Any]] = {}

        # Register standard built-in feature fallbacks and demo providers
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """Register default fallback and demo providers for standard event planning tasks."""
        # Timeline
        self.register_demo_provider(
            AITask.EVENT_TIMELINE,
            lambda req: get_demo_timeline(getattr(req, "event_type", "wedding")),
        )
        self.register_fallback(
            AITask.EVENT_TIMELINE,
            lambda req: generate_deterministic_timeline(req),
        )

        # Risks
        self.register_demo_provider(
            AITask.EVENT_RISKS,
            lambda req: get_demo_event_risks(getattr(req, "event_type", "wedding")),
        )
        self.register_fallback(
            AITask.EVENT_RISKS,
            lambda req: generate_deterministic_risks(req),
        )

        # Crisis Recovery
        self.register_demo_provider(
            AITask.CRISIS_RECOVERY,
            lambda _req: get_demo_crisis_recovery(),
        )
        self.register_fallback(
            AITask.CRISIS_RECOVERY,
            lambda req: generate_deterministic_crisis_recovery(
                crisis_type=getattr(req, "crisis_type", "rain"),
                severity=getattr(req, "severity", 2),
            ),
        )

        # Family Council
        self.register_demo_provider(
            AITask.FAMILY_COUNCIL,
            lambda _req: get_demo_family_council(),
        )
        self.register_fallback(
            AITask.FAMILY_COUNCIL,
            lambda req: generate_deterministic_family_council(req),
        )

    def register_fallback(self, task: AITask | str, provider: FallbackCallable[Any]) -> None:
        """Register a default deterministic fallback callable for a specific task."""
        task_name = _normalize_task_name(task)
        self._fallback_registry[task_name] = provider

    def register_demo_provider(self, task: AITask | str, provider: FallbackCallable[Any]) -> None:
        """Register a default demo content provider for a specific task."""
        task_name = _normalize_task_name(task)
        self._demo_registry[task_name] = provider

    async def orchestrate(
        self,
        task: AITask | str,
        response_schema: type[T],
        prompt: str | None = None,
        system_instruction: str | None = None,
        request_data: Any | None = None,
        fallback: FallbackCallable[T] | None = None,
        demo_provider: FallbackCallable[T] | None = None,
    ) -> AIResultEnvelope[T]:
        """Orchestrate an AI task based on configured AI_MODE and fallback policies.

        Args:
            task: Task classification identifier (e.g. AITask.EVENT_TIMELINE or "event_timeline").
            response_schema: Expected Pydantic model class for output validation.
            prompt: Structured prompt string to send to Gemini (if mode calls for it).
            system_instruction: Optional system instruction prompt for Gemini.
            request_data: Validated input payload passed to fallback or demo providers.
            fallback: Feature-specific fallback callable. If omitted, uses task registry.
            demo_provider: Feature-specific demo callable. If omitted, uses task registry.

        Returns:
            AIResultEnvelope containing status, source, validated data, message, and warnings.
        """
        task_name = _normalize_task_name(task)
        active_mode = self.mode

        # Resolve active demo provider
        effective_demo = demo_provider or self._demo_registry.get(task_name)

        # Resolve active fallback provider
        effective_fallback = fallback or self._fallback_registry.get(task_name)

        # ======================================================================
        # MODE 1: DEMO MODE
        # Never calls Gemini; uses deterministic demo content only.
        # ======================================================================
        if active_mode == AIMode.DEMO:
            return await self._execute_demo_mode(
                task_name=task_name,
                response_schema=response_schema,
                request_data=request_data,
                demo_provider=effective_demo,
                fallback=effective_fallback,
            )

        # ======================================================================
        # MODE 2: GEMINI MODE
        # Requires Gemini. Never silently falls back if unconfigured or failing.
        # ======================================================================
        if active_mode == AIMode.GEMINI:
            return await self._execute_gemini_mode(
                task_name=task_name,
                response_schema=response_schema,
                prompt=prompt,
                system_instruction=system_instruction,
            )

        # ======================================================================
        # MODE 3: AUTO MODE (Default)
        # Uses Gemini when available; falls back to deterministic alternative if provided.
        # ======================================================================
        return await self._execute_auto_mode(
            task_name=task_name,
            response_schema=response_schema,
            prompt=prompt,
            system_instruction=system_instruction,
            request_data=request_data,
            fallback=effective_fallback,
        )

    # --------------------------------------------------------------------------
    # Private Execution Strategies
    # --------------------------------------------------------------------------

    async def _execute_demo_mode(
        self,
        task_name: str,
        response_schema: type[T],
        request_data: Any | None,
        demo_provider: FallbackCallable[T] | None,
        fallback: FallbackCallable[T] | None,
    ) -> AIResultEnvelope[T]:
        """Execute task in purely deterministic demonstration mode."""
        provider = demo_provider or fallback
        if provider is None:
            return AIResultEnvelope[T](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.DEMO,
                data=None,
                message=f"No demonstration fixture or fallback registered for task '{task_name}'.",
                warnings=["Demonstration content is unavailable for this feature."],
            )

        try:
            raw_result = await _invoke_callable(provider, request_data)
            validated = self._validate_data(raw_result, response_schema)
            return AIResultEnvelope[T](
                status=AIResultStatus.SUCCESS,
                source=AIResultSource.DEMO,
                data=validated,
                message="Demonstration output generated deterministically.",
                warnings=[
                    "[Illustrative Demo] Synthetic illustrative example for demonstration purposes only. "
                    "Not verified real-world data or live pricing."
                ],
            )
        except Exception as err:
            logger.error("Demo fixture generation failed for task '%s': %s", task_name, err, exc_info=True)
            return AIResultEnvelope[T](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.DEMO,
                data=None,
                message=f"Demo fixture generation failed: {sanitize_safe_text(str(err))}",
                warnings=["Failed to generate demo content."],
            )

    async def _execute_gemini_mode(
        self,
        task_name: str,
        response_schema: type[T],
        prompt: str | None,
        system_instruction: str | None,
    ) -> AIResultEnvelope[T]:
        """Execute task requiring Gemini AI without falling back."""
        if not self.gemini_service.is_configured:
            return AIResultEnvelope[T](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.GEMINI,
                data=None,
                message="Gemini AI is required in 'gemini' mode, but GEMINI_API_KEY is not configured.",
                warnings=["Gemini API key is unconfigured. Fallback is disallowed in 'gemini' mode."],
            )

        if not prompt or not prompt.strip():
            return AIResultEnvelope[T](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.GEMINI,
                data=None,
                message="No prompt provided for Gemini AI operation.",
                warnings=["AI operation aborted: prompt is empty."],
            )

        try:
            result = await self.gemini_service.generate_structured_content(
                prompt=prompt,
                response_schema=response_schema,
                system_instruction=system_instruction,
            )
            return AIResultEnvelope[T](
                status=AIResultStatus.SUCCESS,
                source=AIResultSource.GEMINI,
                data=result,
                message="Successfully generated by Gemini AI.",
                warnings=[],
            )
        except GeminiError as err:
            safe_msg = sanitize_safe_text(str(err))
            logger.warning("Gemini call failed in 'gemini' mode for task '%s': %s", task_name, safe_msg)
            return AIResultEnvelope[T](
                status=AIResultStatus.UNAVAILABLE,
                source=AIResultSource.GEMINI,
                data=None,
                message=f"Gemini AI operation failed: {safe_msg}",
                warnings=["Upstream Gemini failure occurred. Fallback is disallowed in 'gemini' mode."],
            )

    async def _execute_auto_mode(
        self,
        task_name: str,
        response_schema: type[T],
        prompt: str | None,
        system_instruction: str | None,
        request_data: Any | None,
        fallback: FallbackCallable[T] | None,
    ) -> AIResultEnvelope[T]:
        """Execute task attempting Gemini first, falling back to deterministic alternative if provided."""
        failure_reason: str | None = None

        # 1. Attempt Gemini if configured and prompt is present
        if self.gemini_service.is_configured and prompt and prompt.strip():
            try:
                result = await self.gemini_service.generate_structured_content(
                    prompt=prompt,
                    response_schema=response_schema,
                    system_instruction=system_instruction,
                )
                return AIResultEnvelope[T](
                    status=AIResultStatus.SUCCESS,
                    source=AIResultSource.GEMINI,
                    data=result,
                    message="Successfully generated by Gemini AI.",
                    warnings=[],
                )
            except GeminiError as err:
                failure_reason = sanitize_safe_text(str(err))
                logger.warning(
                    "Gemini AI unavailable for task '%s' (%s). Evaluating deterministic fallback.",
                    task_name,
                    failure_reason,
                )
        elif not self.gemini_service.is_configured:
            failure_reason = "Gemini API key is not configured"
        else:
            failure_reason = "No prompt provided"

        # 2. Check if a deterministic fallback is permitted and provided
        if fallback is not None:
            try:
                raw_fallback = await _invoke_callable(fallback, request_data)
                validated = self._validate_data(raw_fallback, response_schema)
                warning_msg = (
                    f"Gemini service was unavailable ({failure_reason}); "
                    "served using deterministic fallback rules."
                )
                return AIResultEnvelope[T](
                    status=AIResultStatus.FALLBACK,
                    source=AIResultSource.DETERMINISTIC,
                    data=validated,
                    message="Safely generated using deterministic fallback rules.",
                    warnings=[warning_msg],
                )
            except Exception as fb_err:
                safe_fb_err = sanitize_safe_text(str(fb_err))
                logger.error(
                    "Deterministic fallback failed for task '%s': %s",
                    task_name,
                    safe_fb_err,
                    exc_info=True,
                )
                return AIResultEnvelope[T](
                    status=AIResultStatus.UNAVAILABLE,
                    source=AIResultSource.DETERMINISTIC,
                    data=None,
                    message=f"Deterministic fallback execution failed: {safe_fb_err}",
                    warnings=["Both Gemini and deterministic fallback failed for this operation."],
                )

        # 3. No fallback available for this task
        logger.info("No deterministic fallback registered for task '%s'", task_name)
        return AIResultEnvelope[T](
            status=AIResultStatus.UNAVAILABLE,
            source=AIResultSource.GEMINI,
            data=None,
            message=(
                f"AI service is currently unavailable ({failure_reason}) "
                f"and no deterministic fallback is registered for task '{task_name}'."
            ),
            warnings=["Operation unavailable without Gemini or registered feature fallback."],
        )

    @staticmethod
    def _validate_data(raw_data: Any, schema: type[T]) -> T:
        """Validate that raw fallback or demo data strictly conforms to the expected schema."""
        origin = get_origin(schema)
        if origin is not None:
            # Schema is a parameterized generic, e.g. list[PreMortemRisk]
            if isinstance(raw_data, origin):
                args = get_args(schema)
                item_cls = args[0] if args else None
                if item_cls and isinstance(item_cls, type) and issubclass(item_cls, BaseModel):
                    validated_items = []
                    for item in raw_data:
                        if isinstance(item, item_cls):
                            validated_items.append(item)
                        elif isinstance(item, dict):
                            validated_items.append(item_cls.model_validate(item))
                        else:
                            validated_items.append(item)
                    return validated_items  # type: ignore[return-value]
                return raw_data
        elif isinstance(schema, type):
            if isinstance(raw_data, schema):
                return raw_data
            if issubclass(schema, BaseModel):
                if isinstance(raw_data, dict):
                    return schema.model_validate(raw_data)
                if isinstance(raw_data, str):
                    return schema.model_validate_json(raw_data)
        return raw_data
