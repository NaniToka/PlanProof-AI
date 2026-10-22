"""Automated integration tests for the PlanProof AI frontend console."""

from pathlib import Path
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import Settings, AIMode


def test_root_serves_new_dashboard() -> None:
    """Verify that root / serves the complete event planning console."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        html = res.text

        # Verify brand & title
        assert "PlanProof AI" in html
        assert "Family Council" in html

        # Verify all 8 navigation items are present
        assert 'data-view="overview"' in html
        assert 'data-view="event-details"' in html
        assert 'data-view="budget"' in html
        assert 'data-view="timeline"' in html
        assert 'data-view="vendors"' in html
        assert 'data-view="ideas"' in html
        assert 'data-view="risks"' in html
        assert 'data-view="council"' in html

        # Verify all 8 view containers are present
        assert 'id="view-overview"' in html
        assert 'id="view-event-details"' in html
        assert 'id="view-budget"' in html
        assert 'id="view-timeline"' in html
        assert 'id="view-vendors"' in html
        assert 'id="view-ideas"' in html
        assert 'id="view-risks"' in html
        assert 'id="view-council"' in html

        # Verify modals
        assert 'id="modal-create-event"' in html
        assert 'id="modal-edit-vendor"' in html

        # Verify event creation fields match backend schema
        assert 'id="create-event-type"' in html
        assert 'id="create-guest-count"' in html
        assert 'id="create-budget"' in html
        assert 'id="create-city-tier"' in html


def test_stylesheet_delivers_exact_color_system() -> None:
    """Verify that style.css defines the exact color palette required."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/style.css")
        assert res.status_code == 200
        css = res.text

        # Check required foundational hex colors
        assert "#050505" in css  # Jet Black
        assert "#3B0A6B" in css  # Royal Amethyst
        assert "#00E5FF" in css  # Electric Cyan

        # Check responsive design and accessibility rules
        assert "prefers-reduced-motion" in css
        assert ":focus-visible" in css
        assert "@media (max-width: 768px)" in css


def test_app_js_connects_all_backend_endpoints() -> None:
    """Verify that app.js references all backend endpoints, categories, and council personas."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/app.js")
        assert res.status_code == 200
        js = res.text

        # Verify endpoint routes
        assert "/api/v1/events" in js
        assert "/budget" in js
        assert "/budget/rebalance" in js
        assert "/timeline" in js
        assert "/timeline/milestones" in js
        assert "/vendors/checklist" in js
        assert "/ideas" in js
        assert "/risks" in js
        assert "/family-council" in js
        assert "/api/v1/ai/status" in js

        # Verify all 8 budget categories
        for cat in [
            "venue",
            "catering",
            "decor",
            "photo_video",
            "attire_beauty",
            "entertainment",
            "logistics",
            "buffer",
        ]:
            assert cat in js, f"Missing budget category '{cat}' in app.js"

        # Verify all 4 council personas
        for persona in [
            "budget_guardian",
            "guest_comfort_advocate",
            "tradition_experience_keeper",
            "logistics_risk_planner",
        ]:
            assert persona in js, f"Missing council persona '{persona}' in app.js"

        # Security check: Ensure browser JS never calls external Gemini directly
        assert "generativelanguage.googleapis.com" not in js
        assert "AIStudio" not in js
