"""
Tests for PlanProof AI UI Redesign, Brand Color Tokens, Responsive Layouts, and Accessibility.
"""

from fastapi.testclient import TestClient
from app.main import create_app


def test_brand_color_tokens_and_stylesheet_rules() -> None:
    """Verify that style.css contains the exact brand palette tokens, media queries, and responsive rules."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/style.css")
        assert res.status_code == 200
        css = res.text

        # 1. Exact Required Brand Colors
        assert "--color-cosmic-latte: #B7A89A;" in css, "Missing Cosmic Latte (#B7A89A)"
        assert "--color-mocha-cream: #E8DCC6;" in css, "Missing Mocha Cream (#E8DCC6)"
        assert "--color-deep-burgundy: #722F37;" in css, "Missing Deep Burgundy (#722F37)"

        # 2. Supporting Editorial Tokens
        assert "--color-page: #F7F2EA;" in css, "Missing page background token"
        assert "--color-surface: #FFFCF7;" in css, "Missing surface token"
        assert "--color-surface-muted: #F0E6D7;" in css, "Missing surface muted token"
        assert "--color-text: #302622;" in css, "Missing text token"
        assert "--color-text-muted: #70645C;" in css, "Missing text muted token"
        assert "--color-border: #D8C8B5;" in css, "Missing border token"
        assert "--color-primary: var(--color-deep-burgundy);" in css, "Primary must reference Deep Burgundy"
        assert "--color-primary-hover: #5D252D;" in css, "Missing primary hover token"
        assert "--color-focus: #722F37;" in css, "Missing focus token"

        # 3. Accessibility & Responsive Rules
        assert "prefers-reduced-motion" in css
        assert ":focus-visible" in css
        assert "@media (max-width: 1024px)" in css
        assert "@media (max-width: 768px)" in css
        assert "@media (max-width: 480px)" in css

        # 4. Mobile Drawer & Backdrop Rules
        assert ".sidebar-backdrop" in css
        assert ".sidebar.open" in css
        assert ".btn-sidebar-close" in css
        assert ".btn-menu-toggle" in css

        # 5. Backward Compatibility Tokens (Required by existing test suite)
        assert "#050505" in css
        assert "#3B0A6B" in css
        assert "#00E5FF" in css


def test_index_html_responsive_structure_and_views() -> None:
    """Verify that index.html contains responsive elements and all 11 view containers."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        html = res.text

        # 1. Viewport Meta Tag
        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html

        # 2. Responsive Mobile Drawer Elements
        assert 'id="sidebar-backdrop"' in html
        assert 'id="btn-sidebar-toggle"' in html
        assert 'id="btn-sidebar-close"' in html

        # 3. All 11 View Sections
        expected_views = [
            "view-overview",
            "view-event-details",
            "view-budget",
            "view-timeline",
            "view-vendors",
            "view-ideas",
            "view-risks",
            "view-council",
            "view-crisis",
            "view-recovery-history",
            "view-readiness",
        ]
        for v in expected_views:
            assert f'id="{v}"' in html, f"Missing view section {v} in index.html"

        # 4. Modals
        assert 'id="modal-create-event"' in html
        assert 'id="modal-edit-vendor"' in html
        assert 'id="modal-save-recovery"' in html

        # 5. Toast Container
        assert 'id="toast-container"' in html


def test_app_js_mobile_interactions_and_endpoints() -> None:
    """Verify that app.js includes mobile sidebar toggle, backdrop dismiss, Escape key handling, and API connections."""
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/static/app.js")
        assert res.status_code == 200
        js = res.text

        # 1. Mobile Sidebar Toggle & Backdrop Handling
        assert "sidebar-backdrop" in js
        assert "btn-sidebar-toggle" in js
        assert "btn-sidebar-close" in js
        assert "Escape" in js

        # 2. Endpoints
        endpoints = [
            "/api/v1/events",
            "/budget",
            "/budget/rebalance",
            "/timeline",
            "/timeline/milestones",
            "/vendors/checklist",
            "/ideas",
            "/risks",
            "/family-council",
            "/api/v1/crisis/types",
            "/crisis/evaluate",
            "/api/v1/ai/status",
        ]
        for ep in endpoints:
            assert ep in js, f"Missing endpoint {ep} in app.js"
