# PlanProof AI — Event Planning & Crisis Recovery Assistant

PlanProof AI is an AI-powered assistant designed for Indian weddings, birthdays, and community gatherings. It combines deterministic budget planning in INR, multi-perspective family council pre-mortems, and instant event-day crisis recovery playbooks with ready-to-copy WhatsApp messages.

---

## Current Status: Milestone 1 Complete

- **Dataset Audit & Ingestion:** Discovered and verified 5,000 crisis scenarios with 0 missing fields and 100% schema match.
- **Data Validation:** Strict Pydantic v2 data models for crisis scenarios, 100% sum validation for budget splits, and vendor checklist schemas.
- **FastAPI Core:** Python 3.11+ application with startup lifespan preloading and error-isolated health and status endpoints.
- **Automated Tests:** 15 deterministic unit and integration tests passing with 100% clean linting and formatting.
- **Interactive UI:** Responsive dashboard displaying live service health and crisis scenario taxonomy.

---

## Repository Structure

```text
planproof-ai/
├── app/
│   ├── __init__.py           # Application package & version
│   ├── config.py             # Pydantic Settings & environment config
│   ├── data_loader.py        # Safe CSV/JSON loader, validation, & repository
│   ├── main.py               # FastAPI entrypoint, lifespan & routes
│   ├── schemas.py            # Pydantic v2 domain schemas
│   ├── services/
│   │   └── __init__.py       # Service package placeholder
│   └── static/
│       ├── app.js            # Dashboard client JavaScript
│       ├── index.html        # Modern dashboard HTML
│       └── style.css         # Responsive glassmorphism styling
├── data/
│   ├── budget_splits.json    # Category allocations by event & city tier
│   ├── crisis_scenarios.csv  # 5,000 preloaded crisis recovery scenarios
│   ├── generate_dataset.py   # Seed dataset generator (synthetic assumptions)
│   └── vendor_checklists.json# Booking lead times & interview questions
├── docs/
│   ├── ARCHITECTURE.md       # High-level architecture & roadmap
│   └── EVALUATION.md         # Dataset audit findings & evaluation framework
├── tests/
│   ├── conftest.py           # Shared test fixtures & TestClient setup
│   ├── test_api.py           # API integration tests (/health, /api/v1/data-status)
│   └── test_data_loader.py   # Loader, schema, & validation unit tests
├── .env.example              # Example environment configuration (no secrets)
├── .gitignore                # Git ignore rules for Python, caches, & secrets
├── dataset.csv               # Original root dataset file (preserved)
├── LICENSE                   # MIT License
├── pyproject.toml            # Project metadata, pytest, & ruff configuration
├── README.md                 # Project documentation
├── render.yaml               # Render web service deployment blueprint
└── requirements.txt          # Python dependencies
```

---

## Quickstart

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Setup Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration

```bash
cp .env.example .env
# Optional: add GEMINI_API_KEY when integrating AI features in Milestone 2
```

### 4. Run Automated Tests & Quality Checks

```bash
# Run test suite
python3 -m pytest

# Run linter and formatting checks
uvx ruff check .
uvx ruff format --check .
```

### 5. Start Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser to view the interactive dashboard, or visit [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger documentation.

---

## AI Operation Modes (`AI_MODE`)

PlanProof AI supports three explicit AI operation modes controlled by the `AI_MODE` environment variable:

- **`auto` (default)**: Uses Google Gemini AI when configured and available; automatically switches to feature-specific deterministic fallbacks when offline or unconfigured.
- **`demo`**: Never makes live calls to Gemini; returns deterministic, synthetic illustrative demonstration fixtures with clear disclaimers.
- **`gemini`**: Strictly requires Gemini AI for AI-dependent operations; returns controlled errors (`AI_NOT_CONFIGURED` or `AIResultStatus.UNAVAILABLE`) when unconfigured or failing. Never silently falls back.

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Responsive system dashboard |
| `GET` | `/health` | Application liveness and version check |
| `GET` | `/api/v1/data-status` | Safe metadata regarding loaded crisis scenarios & catalogs |
| `GET` | `/api/v1/ai/status` | Gemini AI integration configuration and operation mode status |
| `POST` | `/api/v1/events` | Create event profile with automatic deterministic budget allocation |
| `GET` | `/api/v1/events/{event_id}` | Retrieve event profile by server-generated ID |
| `PATCH` | `/api/v1/events/{event_id}` | Partially update event profile with automatic budget recomputation |
| `GET` | `/api/v1/events` | List active event profiles with pagination |
| `GET` | `/api/v1/events/{event_id}/budget` | Retrieve event-specific deterministic budget plan with warnings & explanation |
| `POST` | `/api/v1/events/{event_id}/budget/rebalance` | Rebalance saved event's budget preserving essential categories |
| `POST` | `/api/v1/validate-event` | Strict domain validation for event planning requests |
| `POST` | `/api/v1/budget/calculate` | Deterministic 8-category budget allocation (Hamilton-Hare method) |
| `POST` | `/api/v1/budget/rebalance` | Budget rebalancing with essential category preservation |
| `POST` | `/api/v1/plan/timeline` | AI-orchestrated event planning checklist and run-sheet with fallback |
| `POST` | `/api/v1/plan/risks` | AI-orchestrated pre-mortem risk assessment with deterministic fallback |
| `GET` | `/docs` | OpenAPI / Swagger interactive documentation |

---

## Event-Specific Budget Planning

PlanProof AI implements deterministic, mathematically verified budget planning for Indian celebrations. Gemini or other LLMs are **never** permitted to compute or adjust budget arithmetic.

### 1. Endpoint: `GET /api/v1/events/{event_id}/budget`

Retrieves the 8-category budget plan for a saved event profile:

- **Input:** Path parameter `event_id` (e.g. `EV-A1B2C3D4E5F6`).
- **HTTP Status:** `200 OK` on success, `404 Not Found` if event does not exist.
- **Independence:** Functions 100% deterministically with zero Gemini API calls and in demo mode.

### 2. Allocation Categories

Every event budget is divided across 8 canonical categories:

1. `venue`: Hall rental, lawn leasing, and space charges.
2. `catering`: Multi-meal food, beverages, service, and live counters.
3. `decor`: Floral staging, mandap/backdrop, lighting, and entry installations.
4. `photo_video`: Candid photography, cinematography, drone footage, and albums.
5. `attire_beauty`: Outfits, bridal/groom styling, hair, and makeup artistry.
6. `entertainment`: DJ, live music, sangeet choreographers, sound systems, and MC.
7. `logistics`: Guest transport, room bookings, permissions, and generator backups.
8. `buffer`: Dedicated emergency contingency reserve (protected).

### 3. Rounding & Deterministic Allocation Method

- Allocations are computed using the **Hamilton-Hare Largest Remainder Method**.
- Integer rupee amounts are initially assigned via truncated proportions (`floor(weight * total)`).
- Remaining rupees are distributed one-by-one to categories with the largest fractional remainders, breaking ties deterministically in canonical category order.
- **Guarantee:** All amounts are non-negative integers that sum **exactly** to `total_budget_inr` down to the last rupee (`remaining_budget_inr = 0`).

### 4. Behavior on Event Updates & Recalculation

- When an event profile's `total_budget_inr`, `city_tier`, or `event_type` is modified via `PATCH /api/v1/events/{event_id}`, allocations are immediately recomputed without retaining stale values.
- Alternatively, `POST /api/v1/events/{event_id}/budget/rebalance` allows targeted budget adjustments using our priority-based policy: trimming discretionary categories (`entertainment`, `decor`) first while strictly preserving essential guest hospitality (`catering`, `buffer`).

### 5. Disclaimer

> **Important:** Budget category allocations represent baseline mathematical planning estimates based on historical statistical ratios. They are not binding vendor quotations, commercial proposals, or venue rate guarantees.

### 6. Sample Response

```json
{
  "event_id": "EV-35D19DF60424",
  "total_budget_inr": 2500000,
  "currency": "INR",
  "allocations": {
    "venue": 750000,
    "catering": 600000,
    "decor": 350000,
    "photo_video": 250000,
    "attire_beauty": 200000,
    "entertainment": 150000,
    "logistics": 100000,
    "buffer": 100000,
    "total_budget_inr": 2500000
  },
  "allocation_percentages": {
    "venue": 30.0,
    "catering": 24.0,
    "decor": 14.0,
    "photo_video": 10.0,
    "attire_beauty": 8.0,
    "entertainment": 6.0,
    "logistics": 4.0,
    "buffer": 4.0
  },
  "remaining_budget_inr": 0,
  "warnings": [
    "Emergency contingency buffer is ₹100,000 (4.0% of total budget), which is below the recommended 5% safety margin."
  ],
  "explanation": "The total budget of ₹2,500,000 was allocated across 8 categories for a wedding in metro tier using the Hamilton-Hare largest remainder method. All allocations are exact non-negative integers that sum precisely to ₹2,500,000 with zero unallocated balance. The plan preserves an emergency contingency buffer of ₹100,000 (4.0% of total budget) to absorb unexpected event-day cost increases. Note: These category splits represent baseline mathematical planning estimates based on historical benchmarks, not binding vendor quotations or venue rate guarantees."
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).
