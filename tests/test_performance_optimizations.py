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
async def test_create_three_separate_events_unique_vendor_item_ids() -> None:
    """Regression test: Creating multiple events of the same type must generate

    globally unique vendor checklist item IDs without duplicate key collisions.
    """
    settings = Settings(app_env="testing", storage_backend="memory")
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            all_item_ids: set[str] = set()
            event_ids: list[str] = []

            for i in range(1, 4):
                payload = {
                    "event_type": "wedding",
                    "event_name": f"Wedding {i}",
                    "city": "Mumbai",
                    "city_tier": "metro",
                    "event_date": f"2027-0{i+5}-15",
                    "guest_count": 200 + i * 20,
                    "total_budget_inr": 2000000 + i * 100000,
                    "language": "en",
                }
                resp = await client.post("/api/v1/events", json=payload)
                assert resp.status_code == 201, f"Failed to create event {i}: {resp.text}"
                data = resp.json()
                ev_id = data["event_id"]
                event_ids.append(ev_id)

                # Fetch checklist
                chk_resp = await client.get(f"/api/v1/events/{ev_id}/vendors/checklist")
                assert chk_resp.status_code == 200
                items = chk_resp.json()["items"]
                assert len(items) == 9

                for item in items:
                    item_id = item["id"]
                    assert item_id not in all_item_ids, f"Collision detected for item_id: {item_id}"
                    all_item_ids.add(item_id)

            assert len(event_ids) == 3
            # 3 events * 9 items = 27 unique items
            assert len(all_item_ids) == 27


@pytest.mark.asyncio
async def test_gemini_full_crisis_recovery_prompt_accepts_9078_characters() -> None:
    """Regression test: Verify that a 9,078-character crisis recovery prompt is accepted

    without raising ValueError: Prompt length (9078) exceeds maximum limit of 1000 characters.
    """
    from unittest.mock import AsyncMock, MagicMock
    from pydantic import BaseModel
    from app.services.gemini_service import GeminiService

    class CrisisResponseModel(BaseModel):
        status: str

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = '{"status": "ok"}'
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)

    service = GeminiService(settings=Settings(gemini_api_key="test_key"), client=mock_client)

    # Construct prompt with exactly 9,078 characters
    full_prompt = "Crisis Prompt Header: " + ("A" * (9078 - len("Crisis Prompt Header: ")))
    assert len(full_prompt) == 9078

    result = await service.generate_structured_content(
        prompt=full_prompt,
        response_schema=CrisisResponseModel,
    )
    assert result.status == "ok"


