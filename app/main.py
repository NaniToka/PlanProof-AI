"""FastAPI application entrypoint for PlanProof AI."""

import logging
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ConfigurationError, Settings, get_settings
from app.data_loader import DataLoaderError, DatasetRepository
from app.schemas import (
    AIStatusResponse,
    BudgetCalculateRequest,
    BudgetCalculationResponse,
    BudgetRebalanceRequest,
    BudgetRebalanceResponse,
    DataStatusResponse,
    EventPlanRequest,
    EventValidationResponse,
    HealthResponse,
    StandardErrorResponse,
)
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
        """Load datasets into application state at startup."""
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
        app.state.gemini_service = GeminiService(settings=app_settings)
        yield

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        description="AI-powered event planning and crisis recovery assistant.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.gemini_service = GeminiService(settings=app_settings)
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
        return AIStatusResponse(
            configured=is_configured,
            model=active_settings.gemini_model,
            timeout_seconds=active_settings.gemini_timeout_seconds,
            max_retries=active_settings.gemini_max_retries,
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
