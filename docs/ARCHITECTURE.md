# PlanProof AI — System Architecture & Design

## 1. System Overview

**PlanProof AI** is an AI-powered event planning and crisis recovery assistant designed to help planners and families manage weddings, birthdays, and community gatherings across Indian cities (metro, tier 2, and tier 3).

The system addresses three critical phases of event management:
1. **Pre-Event Planning:** Budget-aware milestone planning in Indian Rupees (INR) with deterministic percentage category rebalancing and vendor booking checklists.
2. **Pre-Mortem Risk Evaluation:** Multi-perspective risk assessment incorporating family council dynamics (traditional elder, pragmatic treasurer, modern host, experience architect).
3. **Event-Day Crisis Recovery:** Real-time crisis response playbooks with instant WhatsApp broadcast templates and deterministic budget reallocation.

```
                      ┌────────────────────────────────────────┐
                      │    PlanProof AI Client (Vanilla Web)   │
                      └───────────────────┬────────────────────┘
                                          │ HTTP / JSON
                                          ▼
                      ┌────────────────────────────────────────┐
                      │      FastAPI Application Server        │
                      │   - Lifespan preloading (startup)      │
                      │   - Health & Data-status endpoints     │
                      │   - Safe exception isolation           │
                      └──────────────┬─────────────────────────┘
                                     │
           ┌─────────────────────────┴────────────────────────┐
           ▼                                                  ▼
┌──────────────────────────────┐            ┌──────────────────────────────────┐
│   In-Memory Dataset Store    │            │   AI Service Layer (Milestone 2) │
│ - 5,000 Crisis Scenarios     │            │ - Google Gemini (google-genai)   │
│ - 100% Valid Budget Splits   │            │ - Family Council & Pre-Mortem    │
│ - Vendor Checklists Catalog  │            │ - Fallback Sample/Demo Mode      │
└──────────────────────────────┘            └──────────────────────────────────┘
```

---

## 2. Milestone 1 Architecture

### A. Data Layer (`app/data_loader.py`, `app/schemas.py`)
- **Crisis Scenario Repository:** Loaded once during application startup lifespan. Validates all 5,000 synthetic crisis records.
- **Strict Pydantic v2 Schemas:** Validates row types, severity bounds ($1 \le \text{severity} \le 3$), strictly positive guest counts, and non-empty description strings.
- **Budget Allocations:** Pre-validates that all category allocations for each `(event_type, city_tier)` pair sum to exactly 100%.
- **Zero Silent Drops:** Any malformed row or invalid value raises an actionable `DataLoaderError` rather than silently discarding records.

### B. Application & API Layer (`app/main.py`, `app/config.py`)
- **FastAPI 0.115+** with Python 3.11+ type annotations.
- **Startup Lifespan:** Datasets are parsed and validated during startup and held in `app.state.dataset_repo` for $O(1)$ request access.
- **Endpoints:**
  - `GET /health`: Basic liveness check returning app name, environment, and version.
  - `GET /api/v1/data-status`: Safe status metadata reporting scenario count, unique crisis types, and dataset integrity without leaking entire records.
  - `GET /`: Serves responsive dashboard UI.
- **Exception Sanitization:** Custom exception handlers intercept `DataLoaderError` and unexpected runtime exceptions, ensuring no internal stack traces or environment variables leak into HTTP responses.

### C. Future Extensions
- **Milestone 2 (AI Integration):** Official `google-genai` client integration for risk pre-mortems, family council deliberative generation, and crisis WhatsApp drafts.
- **Milestone 3 (Interactive Frontend):** Rich interactive UI for event budget calculator and crisis recovery workflow.
- **Deployment:** Render containerized web service with zero-downtime health monitoring.
