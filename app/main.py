"""FastAPI application entrypoint for PlanProof AI."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.data_loader import DataLoaderError, DatasetRepository
from app.schemas import DataStatusResponse, HealthResponse

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DataLoaderError)
    async def data_loader_exception_handler(
        _request: Request, exc: DataLoaderError
    ) -> JSONResponse:
        """Handle data loader exceptions without leaking internal stack traces."""
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": f"Dataset service error: {exc}"},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
        """Catch unhandled errors and return a safe JSON response."""
        logger.error("Unhandled error encountered: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health() -> HealthResponse:
        """Health check endpoint confirming service status."""
        return HealthResponse(
            status="ok",
            app=app_settings.app_name,
            version=app_settings.version,
            environment=app_settings.environment,
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

    # Static assets and index landing page
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/", include_in_schema=False)
        async def root() -> FileResponse:
            index_path = static_dir / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise HTTPException(status_code=404, detail="Index not found")

    return app


app = create_app()
