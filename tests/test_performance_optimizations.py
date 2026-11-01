"""Unit and integration tests for PlanProof AI production performance optimizations.

Covers:
- Request timing middleware (Server-Timing header)
- Batched repository operations
- Deduplication and double-submission protection
"""

from __future__ import annotations

import time
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.mark.asyncio
async def test_server_timing_header_present_on_responses() -> None:
    """Verify that every HTTP response includes a Server-Timing header with duration."""
    settings = Settings(app_env="testing", storage_backend="memory")
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert "Server-Timing" in resp.headers
            timing_val = resp.headers["Server-Timing"]
            assert timing_val.startswith("total;dur=")


@pytest.mark.asyncio
async def test_public_routes_accessible_without_tokens() -> None:
    """Ensure public status routes respond fast without any auth token or guest requirements."""
    settings = Settings(app_env="testing", storage_backend="memory")
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for route in ["/health", "/api/v1/auth/config", "/api/v1/data-status", "/api/v1/ai/status"]:
                t0 = time.perf_counter()
                resp = await client.get(route)
                dur_ms = (time.perf_counter() - t0) * 1000
                assert resp.status_code == 200
                assert dur_ms < 200, f"Route {route} took {dur_ms:.1f}ms, expected < 200ms"
