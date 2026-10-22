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


def test_end_to_end_user_journey() -> None:
    """Verify complete end-to-end user workflow across all 8 dashboard sections."""
    app = create_app()
    with TestClient(app) as client:
        # 1. Open application
        res_root = client.get("/")
        assert res_root.status_code == 200

        # 2. Create wedding event
        create_payload = {
            "event_type": "wedding",
            "event_name": "Ananya & Arjun's Heritage Wedding",
            "city": "Udaipur",
            "city_tier": "tier2",
            "event_date": "2027-12-15",
            "guest_count": 300,
            "total_budget_inr": 2_000_000,
            "theme_notes": "Royal Rajasthani heritage palace celebration with lakeside dinner and folk music",
        }
        res_create = client.post("/api/v1/events", json=create_payload)
        assert res_create.status_code == 201
        event = res_create.json()
        event_id = event["event_id"]
        assert event_id.startswith("EV-")

        # 3. Retrieve created event profile
        res_get = client.get(f"/api/v1/events/{event_id}")
        assert res_get.status_code == 200
        assert res_get.json()["event_name"] == "Ananya & Arjun's Heritage Wedding"

        # 4. Inspect budget and 8 allocation categories
        res_budget = client.get(f"/api/v1/events/{event_id}/budget")
        assert res_budget.status_code == 200
        budget_data = res_budget.json()
        assert budget_data["total_budget_inr"] == 2_000_000
        allocations = budget_data["allocations"]
        categories = [k for k in allocations if k != "total_budget_inr"]
        assert len(categories) == 8
        for cat in ["venue", "catering", "decor", "photo_video", "attire_beauty", "entertainment", "logistics", "buffer"]:
            assert cat in allocations
            assert allocations[cat] > 0
        assert sum(allocations[k] for k in categories) == 2_000_000

        # 5. View timeline
        res_timeline = client.get(f"/api/v1/events/{event_id}/timeline")
        assert res_timeline.status_code == 200
        timeline_data = res_timeline.json()
        assert len(timeline_data["milestones"]) > 0
        first_mid = timeline_data["milestones"][0]["milestone_id"]

        # 6. Update milestone status
        res_ms_update = client.patch(
            f"/api/v1/events/{event_id}/timeline/milestones/{first_mid}",
            json={"status": "completed"},
        )
        assert res_ms_update.status_code == 200
        assert res_ms_update.json()["status"] == "completed"

        # 7. Update vendor checklist item
        res_vendors = client.get(f"/api/v1/events/{event_id}/vendors/checklist")
        assert res_vendors.status_code == 200
        first_item_id = res_vendors.json()["items"][0]["id"]

        res_v_update = client.patch(
            f"/api/v1/events/{event_id}/vendors/checklist/{first_item_id}",
            json={
                "status": "in_progress",
                "booking_status": "contacted",
                "vendor_name": "Lake Palace Catering & Banquets",
                "notes": "Spoke to banquet manager; site inspection set for Saturday",
            },
        )
        assert res_v_update.status_code == 200
        v_updated = res_v_update.json()
        assert v_updated["status"] == "in_progress"
        assert v_updated["booking_status"] == "contacted"
        assert v_updated["vendor_name"] == "Lake Palace Catering & Banquets"

        # 8. Review personalized ideas
        res_ideas = client.get(f"/api/v1/events/{event_id}/ideas")
        assert res_ideas.status_code == 200
        ideas_data = res_ideas.json()
        assert "data" in ideas_data
        assert len(ideas_data["data"]["ideas"]) > 0

        # 9. Inspect pre-mortem risks
        res_risks = client.get(f"/api/v1/events/{event_id}/risks")
        assert res_risks.status_code == 200
        risks_data = res_risks.json()
        assert "data" in risks_data
        assert len(risks_data["data"]["risks"]) > 0
        assert "disclaimer" in risks_data["data"]

        # 10. Open four-persona family council
        res_council = client.get(f"/api/v1/events/{event_id}/family-council")
        assert res_council.status_code == 200
        council_data = res_council.json()["data"]
        assert len(council_data["personas"]) == 4
        persona_ids = [p["persona_id"] for p in council_data["personas"]]
        assert "budget_guardian" in persona_ids
        assert "guest_comfort_advocate" in persona_ids
        assert "tradition_experience_keeper" in persona_ids
        assert "logistics_risk_planner" in persona_ids
        assert "summary" in council_data

        # 11. Test budget rebalancing
        res_rebalance = client.post(
            f"/api/v1/events/{event_id}/budget/rebalance",
            json={"new_total_budget_inr": 2_500_000, "strict_protect": True},
        )
        assert res_rebalance.status_code == 200
        assert res_rebalance.json()["new_total_inr"] == 2_500_000

        # 12. Verify event persistence & unchanged crisis scenarios dataset
        res_recheck = client.get(f"/api/v1/events/{event_id}")
        assert res_recheck.status_code == 200
        assert res_recheck.json()["budget"]["total_budget_inr"] == 2_500_000

