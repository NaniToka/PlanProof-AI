"""FastAPI application entrypoint for PlanProof AI."""

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import AIMode, ConfigurationError, Settings, get_settings
from app.data_loader import DataLoaderError, DatasetRepository
from app.schemas import (
    AIResultEnvelope,
    AIStatusResponse,
    AITask,
    BudgetCalculateRequest,
    BudgetCalculationResponse,
    BudgetRebalanceRequest,
    BudgetRebalanceResponse,
    CrisisEvaluationRequest,
    CrisisTypeMetadata,
    DataStatusResponse,
    EventBudgetPlanResponse,
    EventBudgetRebalanceRequest,
    EventCreateRequest,
    EventCrisisRecoveryResponse,
    EventFamilyCouncilResponse,
    EventIdeasResponse,
    EventListResponse,
    EventMilestone,
    EventPlanRequest,
    EventProfile,
    EventRisksResponse,
    EventTimelineResponse,
    EventTimelineScheduleResponse,
    EventUpdateRequest,
    EventValidationResponse,
    EventVendorChecklistItem,
    EventVendorChecklistResponse,
    HealthResponse,
    IdeaCategory,
    MilestoneStatusUpdateRequest,
    PreMortemRisk,
    StandardErrorResponse,
    VendorChecklistItemUpdateRequest,
)
from app.services.ai_orchestrator import AIOrchestrator
from app.services.crisis_service import SUPPORTED_CRISIS_TYPES
from app.services.event_service import EventService, EventStore
from app.services.budget import (
    BudgetEngineError,
    calculate_initial_budget,
    rebalance_budget,
)
from app.services.gemini_service import (
    GeminiError,
    GeminiInvalidOutputError,
    GeminiNotConfiguredError,
    GeminiProviderError,
    GeminiRateLimitError,
    GeminiService,
    GeminiTimeoutError,
)

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a PlanProof AI FastAPI application instance."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Validate configuration, initialize services and load datasets at startup."""
        # 1. Validate configured AI_MODE at startup
        if app_settings.ai_mode not in (AIMode.AUTO, AIMode.DEMO, AIMode.GEMINI):
            raise ConfigurationError(f"Unsupported AI_MODE: '{app_settings.ai_mode}'")
        logger.info("Initializing PlanProof AI in AI_MODE=%s", app_settings.ai_mode.value)

        # 2. Load datasets
        repo = DatasetRepository()
        logger.info(
            "Initializing datasets from %s, %s, %s",
            app_settings.crisis_dataset_path,
            app_settings.budget_splits_path,
            app_settings.vendor_checklists_path,
        )
        repo.load_all(
            crisis_path=app_settings.crisis_dataset_path,
            budget_path=app_settings.budget_splits_path,
            vendor_path=app_settings.vendor_checklists_path,
        )
        app.state.dataset_repo = repo
        app.state.settings = app_settings

        # 3. Initialize AI services
        gemini_svc = GeminiService(settings=app_settings)
        app.state.gemini_service = gemini_svc
        app.state.ai_orchestrator = AIOrchestrator(
            settings=app_settings, gemini_service=gemini_svc
        )

        # 4. Initialize Event Profile Store & Service
        event_store = EventStore()
        app.state.event_store = event_store
        app.state.event_service = EventService(
            store=event_store,
            dataset_repo=repo,
            settings=app_settings,
        )
        yield

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        description="AI-powered event planning and crisis recovery assistant.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    gemini_svc_init = GeminiService(settings=app_settings)
    app.state.gemini_service = gemini_svc_init
    app.state.ai_orchestrator = AIOrchestrator(
        settings=app_settings, gemini_service=gemini_svc_init
    )
    event_store_init = EventStore()
    app.state.event_store = event_store_init
    app.state.event_service = EventService(
        store=event_store_init,
        dataset_repo=None,
        settings=app_settings,
    )
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    cors_origins = (
        app_settings.allowed_cors_origins
        if isinstance(app_settings.allowed_cors_origins, list)
        else [app_settings.allowed_cors_origins]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def sanitize_error_message(message: str) -> str:
        """Sanitize error messages to ensure absolute paths or secrets are never exposed."""
        # Strip absolute Unix or Windows file paths, leaving only filename
        cleaned = re.sub(r"(/[a-zA-Z0-9_\.\-]+)+/([a-zA-Z0-9_\.\-]+)", r"\2", message)
        return re.sub(r"([a-zA-Z]:\\[a-zA-Z0-9_\.\-\\]+)\\([a-zA-Z0-9_\.\-]+)", r"\2", cleaned)

    # --------------------------------------------------------------------------
    # Exception Handlers (Standard Error Format)
    # --------------------------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Format request validation errors into standard error response."""
        formatted_details = [
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": sanitize_error_message(err.get("msg", "")),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": formatted_details,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Format standard HTTP exceptions into standard error response."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "HTTP_ERROR",
                    "message": sanitize_error_message(str(exc.detail)),
                    "details": None,
                }
            },
        )

    @app.exception_handler(DataLoaderError)
    async def data_loader_exception_handler(
        _request: Request, exc: DataLoaderError
    ) -> JSONResponse:
        """Handle data loader exceptions without leaking internal stack traces or paths."""
        logger.error("Dataset loader error encountered: %s", exc, exc_info=True)
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DATASET_ERROR",
                    "message": f"Dataset service error: {safe_msg}",
                    "details": None,
                }
            },
        )

    @app.exception_handler(ConfigurationError)
    async def configuration_exception_handler(
        _request: Request, exc: ConfigurationError
    ) -> JSONResponse:
        """Handle configuration errors without exposing sensitive environment details."""
        logger.error("Configuration error encountered: %s", exc, exc_info=True)
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "CONFIGURATION_ERROR",
                    "message": f"Configuration error: {safe_msg}",
                    "details": None,
                }
            },
        )

    @app.exception_handler(BudgetEngineError)
    async def budget_engine_exception_handler(
        _request: Request, exc: BudgetEngineError
    ) -> JSONResponse:
        """Handle budget engine domain errors without leaking internal stack traces."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "BUDGET_CALCULATION_ERROR",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiNotConfiguredError)
    async def gemini_not_configured_handler(
        _request: Request, exc: GeminiNotConfiguredError
    ) -> JSONResponse:
        """Handle missing Gemini API key configuration."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "AI_NOT_CONFIGURED",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiTimeoutError)
    async def gemini_timeout_handler(_request: Request, exc: GeminiTimeoutError) -> JSONResponse:
        """Handle Gemini request timeouts."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={
                "error": {
                    "code": "AI_TIMEOUT",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiRateLimitError)
    async def gemini_rate_limit_handler(
        _request: Request, exc: GeminiRateLimitError
    ) -> JSONResponse:
        """Handle Gemini API rate limiting."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "AI_RATE_LIMIT",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiInvalidOutputError)
    async def gemini_invalid_output_handler(
        _request: Request, exc: GeminiInvalidOutputError
    ) -> JSONResponse:
        """Handle Gemini returning malformed or schema-incompatible JSON."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": "AI_OUTPUT_VALIDATION_ERROR",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiProviderError)
    async def gemini_provider_handler(_request: Request, exc: GeminiProviderError) -> JSONResponse:
        """Handle upstream Gemini service and network errors."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "code": "AI_PROVIDER_ERROR",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(GeminiError)
    async def gemini_generic_handler(_request: Request, exc: GeminiError) -> JSONResponse:
        """Handle unexpected Gemini service domain errors."""
        safe_msg = sanitize_error_message(str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "AI_SERVICE_ERROR",
                    "message": safe_msg,
                    "details": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        """Catch unhandled errors and return a safe JSON response."""
        logger.error("Unhandled error encountered: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal server error occurred.",
                    "details": None,
                }
            },
        )

    # --------------------------------------------------------------------------
    # API Routes
    # --------------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health(
        request: Request,
        current_settings: Settings = Depends(get_settings),
    ) -> HealthResponse:
        """Health check endpoint confirming service status."""
        active_settings = getattr(request.app.state, "settings", current_settings)
        return HealthResponse(
            status="ok",
            app=active_settings.app_name,
            version=active_settings.version,
            environment=active_settings.environment,
        )

    @app.get(
        "/api/v1/data-status",
        response_model=DataStatusResponse,
        tags=["Datasets"],
        responses={
            503: {"description": "Dataset unavailable or failed validation"},
        },
    )
    async def data_status(request: Request) -> Response:
        """Return safe metadata about loaded crisis and planning datasets."""
        repo: DatasetRepository | None = getattr(request.app.state, "dataset_repo", None)
        if repo is None or not repo.is_loaded:
            summary = (
                repo.get_status_summary() if repo else DatasetRepository().get_status_summary()
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=summary.model_dump(),
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=repo.get_status_summary().model_dump(),
        )

    def get_ai_orchestrator(
        request: Request,
        current_settings: Settings = Depends(get_settings),
    ) -> AIOrchestrator:
        """Dependency resolving application-level AI orchestrator."""
        orchestrator: AIOrchestrator | None = getattr(request.app.state, "ai_orchestrator", None)
        if orchestrator is None:
            active_settings = getattr(request.app.state, "settings", current_settings)
            svc = getattr(request.app.state, "gemini_service", None) or GeminiService(
                settings=active_settings
            )
            orchestrator = AIOrchestrator(settings=active_settings, gemini_service=svc)
            request.app.state.ai_orchestrator = orchestrator
        return orchestrator

    def get_event_service(
        request: Request,
        current_settings: Settings = Depends(get_settings),
    ) -> EventService:
        """Dependency resolving application-level event service."""
        service: EventService | None = getattr(request.app.state, "event_service", None)
        if service is None:
            active_settings = getattr(request.app.state, "settings", current_settings)
            store = getattr(request.app.state, "event_store", None) or EventStore()
            repo = getattr(request.app.state, "dataset_repo", None)
            service = EventService(store=store, dataset_repo=repo, settings=active_settings)
            request.app.state.event_store = store
            request.app.state.event_service = service
        return service

    def get_dataset_repository(request: Request) -> DatasetRepository:
        """Dependency resolving application-level dataset repository."""
        repo: DatasetRepository | None = getattr(request.app.state, "dataset_repo", None)
        if repo is None:
            repo = DatasetRepository()
            request.app.state.dataset_repo = repo
        return repo

    @app.post(
        "/api/v1/events",
        response_model=EventProfile,
        status_code=status.HTTP_201_CREATED,
        responses={
            422: {"model": StandardErrorResponse, "description": "Validation failed"},
        },
        tags=["Events"],
        summary="Create a new event profile with deterministic budget allocation",
    )
    async def create_event(
        request_data: EventCreateRequest,
        service: EventService = Depends(get_event_service),
    ) -> EventProfile:
        """Create a new event profile and calculate its initial 8-category budget."""
        try:
            return await service.create_event(request_data)
        except ValueError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

    @app.get(
        "/api/v1/events/{event_id}",
        response_model=EventProfile,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
        },
        tags=["Events"],
        summary="Retrieve an event profile by event ID",
    )
    async def get_event(
        event_id: str,
        service: EventService = Depends(get_event_service),
    ) -> EventProfile:
        """Retrieve an existing event profile by its server-generated ID."""
        profile = await service.get_event(event_id)
        if profile is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return profile

    @app.patch(
        "/api/v1/events/{event_id}",
        response_model=EventProfile,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation failed"},
        },
        tags=["Events"],
        summary="Update an existing event profile",
    )
    async def update_event(
        event_id: str,
        update_data: EventUpdateRequest,
        service: EventService = Depends(get_event_service),
    ) -> EventProfile:
        """Apply partial updates to an event profile and recalculate budget if necessary."""
        try:
            profile = await service.update_event(event_id, update_data)
        except ValueError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        if profile is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return profile

    @app.get(
        "/api/v1/events",
        response_model=EventListResponse,
        tags=["Events"],
        summary="List active event profiles with pagination",
    )
    async def list_events(
        skip: int = Query(default=0, ge=0, description="Number of events to skip"),
        limit: int = Query(
            default=50, ge=1, le=100, description="Maximum number of events to return"
        ),
        service: EventService = Depends(get_event_service),
    ) -> EventListResponse:
        """List event profiles currently stored in the ephemeral memory repository."""
        events, total = await service.list_events(skip=skip, limit=limit)
        return EventListResponse(
            total=total,
            skip=skip,
            limit=limit,
            events=events,
        )

    @app.get(
        "/api/v1/events/{event_id}/budget",
        response_model=EventBudgetPlanResponse,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
        },
        tags=["Budget", "Events"],
        summary="Retrieve event-specific deterministic budget plan with warnings and explanation",
    )
    async def get_event_budget(
        event_id: str,
        service: EventService = Depends(get_event_service),
    ) -> EventBudgetPlanResponse:
        """Retrieve the deterministic 8-category budget plan for a saved event profile."""
        plan = await service.get_event_budget_plan(event_id)
        if plan is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return plan

    @app.post(
        "/api/v1/events/{event_id}/budget/rebalance",
        response_model=BudgetRebalanceResponse,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation or constraint error"},
        },
        tags=["Budget", "Events"],
        summary="Rebalance a saved event profile's budget protecting essentials",
    )
    async def rebalance_event_budget_endpoint(
        event_id: str,
        request_data: EventBudgetRebalanceRequest,
        service: EventService = Depends(get_event_service),
    ) -> BudgetRebalanceResponse:
        """Rebalance the budget of a saved event profile and persist the updated allocations."""
        result = await service.rebalance_event_budget(
            event_id=event_id,
            new_total_budget_inr=request_data.new_total_budget_inr,
            strict_protect=request_data.strict_protect,
        )
        if result is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return result

    @app.get(
        "/api/v1/events/{event_id}/timeline",
        response_model=EventTimelineScheduleResponse,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
        },
        tags=["Timeline", "Events"],
        summary="Retrieve deterministic timeline and milestone schedule for a saved event",
    )
    async def get_event_timeline(
        event_id: str,
        reference_date: date | None = Query(
            default=None,
            description="Simulated reference date for deterministic deadline calculations (defaults to IST current date)",
        ),
        service: EventService = Depends(get_event_service),
    ) -> EventTimelineScheduleResponse:
        """Retrieve deterministic timeline with milestones and deadline calculations for an event."""
        timeline = await service.get_event_timeline(event_id, reference_date=reference_date)
        if timeline is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return timeline

    @app.patch(
        "/api/v1/events/{event_id}/timeline/milestones/{milestone_id}",
        response_model=EventMilestone,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event or milestone not found"},
            422: {"model": StandardErrorResponse, "description": "Validation or date constraint error"},
        },
        tags=["Timeline", "Events"],
        summary="Update completion status of a timeline milestone",
    )
    async def update_milestone_status(
        event_id: str,
        milestone_id: str,
        request_data: MilestoneStatusUpdateRequest,
        reference_date: date | None = Query(
            default=None,
            description="Simulated reference date for deterministic deadline calculations (defaults to IST current date)",
        ),
        service: EventService = Depends(get_event_service),
    ) -> EventMilestone:
        """Update a milestone's completion status (pending or completed) in ephemeral memory."""
        try:
            milestone = await service.update_milestone_status(
                event_id=event_id,
                milestone_id=milestone_id,
                status=request_data.status,
                reference_date=reference_date,
            )
        except KeyError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc).strip("'"),
            ) from exc
        except ValueError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        if milestone is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return milestone

    @app.get(
        "/api/v1/events/{event_id}/vendors/checklist",
        response_model=EventVendorChecklistResponse,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
        },
        tags=["Vendors", "Events"],
        summary="Retrieve event-specific vendor checklist and coordination summary",
    )
    async def get_event_vendor_checklist(
        event_id: str,
        service: EventService = Depends(get_event_service),
    ) -> EventVendorChecklistResponse:
        """Retrieve or lazily initialize the vendor coordination checklist for an event."""
        checklist = await service.get_event_vendor_checklist(event_id)
        if checklist is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return checklist

    @app.patch(
        "/api/v1/events/{event_id}/vendors/checklist/{item_id}",
        response_model=EventVendorChecklistItem,
        responses={
            404: {"model": StandardErrorResponse, "description": "Event or checklist item not found"},
            422: {"model": StandardErrorResponse, "description": "Validation error"},
        },
        tags=["Vendors", "Events"],
        summary="Update status, notes, priority, or user-provided vendor details on a checklist item",
    )
    async def update_vendor_checklist_item(
        event_id: str,
        item_id: str,
        request_data: VendorChecklistItemUpdateRequest,
        service: EventService = Depends(get_event_service),
    ) -> EventVendorChecklistItem:
        """Update permitted fields (status, notes, priority, vendor_name, booking_status) on a checklist item."""
        try:
            item = await service.update_vendor_checklist_item(
                event_id=event_id,
                item_id=item_id,
                request=request_data,
            )
        except KeyError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc).strip("'"),
            ) from exc
        except ValueError as exc:
            raise StarletteHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        if item is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return item

    @app.get(
        "/api/v1/events/{event_id}/ideas",
        response_model=AIResultEnvelope[EventIdeasResponse],
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation error"},
        },
        tags=["Ideas", "Events"],
        summary="Retrieve personalized, budget-aware recommendations for a saved event",
    )
    async def get_event_ideas(
        event_id: str,
        category: IdeaCategory | None = Query(
            default=None, description="Optional category filter"
        ),
        limit: int = Query(
            default=10, ge=1, le=50, description="Maximum number of recommendations to return"
        ),
        service: EventService = Depends(get_event_service),
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[EventIdeasResponse]:
        """Retrieve personalized, budget-aware recommendations via AI orchestration with deterministic fallback."""
        result = await service.get_event_ideas(
            event_id=event_id,
            orchestrator=orchestrator,
            category=category,
            limit=limit,
        )
        if result is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return result

    @app.get(
        "/api/v1/events/{event_id}/risks",
        response_model=AIResultEnvelope[EventRisksResponse],
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation error"},
        },
        tags=["Risks", "Events"],
        summary="Retrieve pre-mortem operational, budget, and logistical risk analysis for a saved event",
    )
    async def get_event_risks(
        event_id: str,
        reference_date: date | None = Query(
            default=None,
            description="Optional simulated reference date for timeline calculations (defaults to current date)",
        ),
        service: EventService = Depends(get_event_service),
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[EventRisksResponse]:
        """Analyze pre-mortem risks for a saved event profile using deterministic rules and optional AI enrichment."""
        result = await service.get_event_risks(
            event_id=event_id,
            orchestrator=orchestrator,
            reference_date=reference_date,
        )
        if result is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return result

    @app.get(
        "/api/v1/events/{event_id}/family-council",
        response_model=AIResultEnvelope[EventFamilyCouncilResponse],
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation error"},
        },
        tags=["Family Council", "Events"],
        summary="Retrieve four-persona family council review and trade-off analysis for a saved event",
    )
    async def get_event_family_council(
        event_id: str,
        reference_date: date | None = Query(
            default=None,
            description="Optional simulated reference date for timeline calculations (defaults to current date)",
        ),
        service: EventService = Depends(get_event_service),
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[EventFamilyCouncilResponse]:
        """Review an event plan across four distinct family council perspectives with trade-offs and recommendations."""
        result = await service.get_event_family_council(
            event_id=event_id,
            orchestrator=orchestrator,
            reference_date=reference_date,
        )
        if result is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return result

    @app.get(
        "/api/v1/crisis/types",
        response_model=list[CrisisTypeMetadata],
        tags=["Crisis Recovery"],
        summary="List all supported crisis categories with operational metadata",
    )
    async def get_crisis_types() -> list[CrisisTypeMetadata]:
        """Return canonical list of supported crisis categories with affected area and typical severity."""
        return SUPPORTED_CRISIS_TYPES

    @app.post(
        "/api/v1/events/{event_id}/crisis/evaluate",
        response_model=AIResultEnvelope[EventCrisisRecoveryResponse],
        responses={
            404: {"model": StandardErrorResponse, "description": "Event profile not found"},
            422: {"model": StandardErrorResponse, "description": "Validation error"},
        },
        tags=["Crisis Recovery", "Events"],
        summary="Evaluate an active or potential event crisis and generate a prioritized recovery plan",
    )
    async def evaluate_crisis_for_event(
        event_id: str,
        request_body: CrisisEvaluationRequest,
        service: EventService = Depends(get_event_service),
        dataset_repo: DatasetRepository = Depends(get_dataset_repository),
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[EventCrisisRecoveryResponse]:
        """Generate a deterministic, structured recovery plan grounded in validated crisis scenarios."""
        result = await service.evaluate_crisis(
            event_id=event_id,
            request=request_body,
            dataset_repo=dataset_repo,
            orchestrator=orchestrator,
        )
        if result is None:
            raise StarletteHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Event profile '{event_id}' not found.",
            )
        return result

    @app.get(
        "/api/v1/ai/status",
        response_model=AIStatusResponse,
        tags=["AI"],
        summary="Check Gemini AI service configuration status",
    )
    async def ai_status(
        request: Request,
        current_settings: Settings = Depends(get_settings),
    ) -> AIStatusResponse:
        """Return safe configuration status of Gemini AI without exposing sensitive keys."""
        active_settings = getattr(request.app.state, "settings", current_settings)
        svc: GeminiService | None = getattr(request.app.state, "gemini_service", None)
        is_configured = svc.is_configured if svc else bool(active_settings.gemini_api_key)
        active_mode = getattr(active_settings, "ai_mode", AIMode.AUTO)
        mode_val = active_mode.value if isinstance(active_mode, AIMode) else str(active_mode)
        return AIStatusResponse(
            configured=is_configured,
            model=active_settings.gemini_model,
            timeout_seconds=active_settings.gemini_timeout_seconds,
            max_retries=active_settings.gemini_max_retries,
            mode=mode_val,
        )

    @app.post(
        "/api/v1/validate-event",
        response_model=EventValidationResponse,
        responses={
            422: {"model": StandardErrorResponse, "description": "Validation failed"},
        },
        tags=["Planning"],
    )
    async def validate_event(request_data: EventPlanRequest) -> EventValidationResponse:
        """Validate event planning parameters according to strict domain rules."""
        return EventValidationResponse(
            valid=True,
            message="Event plan request validated successfully.",
            validated_request=request_data,
        )

    @app.post(
        "/api/v1/plan/timeline",
        response_model=AIResultEnvelope[EventTimelineResponse],
        tags=["Planning"],
        summary="Generate event timeline and run-sheet via AI orchestration with deterministic fallback",
    )
    async def generate_timeline(
        plan_request: EventPlanRequest,
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[EventTimelineResponse]:
        """Generate event planning milestones and day-of run-sheet with fallback support."""
        prompt = (
            f"Generate a detailed planning checklist and day-of run-sheet for a {plan_request.event_type.value} "
            f"in {plan_request.city} ({plan_request.city_tier.value} tier) for {plan_request.guest_count} guests "
            f"with total budget INR {plan_request.total_budget_inr:,}. Preferred language: {plan_request.language.value}. "
            f"Theme notes: {plan_request.theme_notes}."
        )
        return await orchestrator.orchestrate(
            task=AITask.EVENT_TIMELINE,
            response_schema=EventTimelineResponse,
            prompt=prompt,
            request_data=plan_request,
        )

    @app.post(
        "/api/v1/plan/risks",
        response_model=AIResultEnvelope[list[PreMortemRisk]],
        tags=["Planning"],
        summary="Assess event risks via AI orchestration with deterministic fallback",
    )
    async def generate_risks(
        plan_request: EventPlanRequest,
        orchestrator: AIOrchestrator = Depends(get_ai_orchestrator),
    ) -> AIResultEnvelope[list[PreMortemRisk]]:
        """Generate pre-mortem risk assessment with probabilities and concrete mitigations."""
        prompt = (
            f"Assess pre-mortem risks for a {plan_request.event_type.value} in {plan_request.city} "
            f"with {plan_request.guest_count} guests and budget INR {plan_request.total_budget_inr:,}."
        )
        return await orchestrator.orchestrate(
            task=AITask.EVENT_RISKS,
            response_schema=list[PreMortemRisk],
            prompt=prompt,
            request_data=plan_request,
        )

    @app.post(
        "/api/v1/budget/calculate",
        response_model=BudgetCalculationResponse,
        responses={
            422: {"model": StandardErrorResponse, "description": "Validation or calculation error"},
        },
        tags=["Budget"],
    )
    async def calculate_budget(
        request: Request,
        calc_request: BudgetCalculateRequest,
    ) -> BudgetCalculationResponse:
        """Calculate deterministic 8-category budget allocation via Hamilton-Hare method."""
        repo: DatasetRepository | None = getattr(request.app.state, "dataset_repo", None)
        splits = repo.budget_splits if repo else None
        return calculate_initial_budget(
            event_type=calc_request.event_type,
            city_tier=calc_request.city_tier,
            total_budget_inr=calc_request.total_budget_inr,
            splits_dataset=splits,
        )

    @app.post(
        "/api/v1/budget/rebalance",
        response_model=BudgetRebalanceResponse,
        responses={
            422: {
                "model": StandardErrorResponse,
                "description": "Validation or rebalance constraint error",
            },
        },
        tags=["Budget"],
    )
    async def rebalance_budget_endpoint(
        rebalance_request: BudgetRebalanceRequest,
    ) -> BudgetRebalanceResponse:
        """Rebalance 8-category budget allocation deterministically protecting essentials."""
        return rebalance_budget(
            current_allocations=rebalance_request.current_allocations,
            new_total_budget_inr=rebalance_request.new_total_budget_inr,
        )

    # Static assets and index landing page
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def root() -> FileResponse:
            index_path = static_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise StarletteHTTPException(status_code=404, detail="Index not found")

    return app


app = create_app()
