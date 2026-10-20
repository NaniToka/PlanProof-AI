"""FastAPI application entrypoint for PlanProof AI."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, get_settings
from app.data_loader import DataLoaderError, DatasetRepository
from app.schemas import (
    DataStatusResponse,
    EventPlanRequest,
    EventValidationResponse,
    HealthResponse,
    StandardErrorResponse,
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
        yield

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.version,
        description="AI-powered event planning and crisis recovery assistant.",
        lifespan=lifespan,
    )

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
                "msg": err.get("msg", ""),
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
                    "message": str(exc.detail),
                    "details": None,
                }
            },
        )

    @app.exception_handler(DataLoaderError)
    async def data_loader_exception_handler(
        _request: Request, exc: DataLoaderError
    ) -> JSONResponse:
        """Handle data loader exceptions without leaking internal stack traces."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DATASET_ERROR",
                    "message": f"Dataset service error: {exc}",
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
        current_settings: Settings = Depends(get_settings),
    ) -> HealthResponse:
        """Health check endpoint confirming service status."""
        return HealthResponse(
            status="ok",
            app=current_settings.app_name,
            version=current_settings.version,
            environment=current_settings.environment,
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
