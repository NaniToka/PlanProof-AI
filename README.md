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
| `GET` | `/api/v1/events/{event_id}/timeline` | Retrieve deterministic timeline and milestone checklist with calendar deadlines |
| `PATCH` | `/api/v1/events/{event_id}/timeline/milestones/{milestone_id}` | Update milestone completion status (`pending` or `completed`) |
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

## Event Timeline & Milestone Scheduling

PlanProof AI generates structured, deterministic milestone checklists and date schedules tailored to the saved event profile, event type, and calendar date.

### Core Rule: Deterministic Date Calculations
Date calculations, lead times, and deadline ordering are computed strictly via Python calendar-date arithmetic (`event_date - timedelta(days=days_before_event)`). Gemini or other LLMs are **never** permitted to decide date calculations or orderings.

### 1. Supported Event Types & Templates
Curated, general-purpose milestone templates are implemented for all supported celebration types:
- **Wedding (`wedding`)**: 9 sequential milestones spanning 180 days down to 2 days before the event (venue booking, core vendor lock-in, invitations, decor, guest lodging, menu tasting, accessibility review, final day-of checklist).
- **Birthday (`birthday`)**: 7 focused milestones spanning 30 days down to 1 day before the event (party hall reservation, theme invitations, custom cake ordering, balloon decor, headcount confirmation, return gifts).
- **Community Event (`community_event`)**: 8 milestones spanning 60 days down to 1 day before the event (committee scope, municipal and sound permissions, PA & backup generator rental, notices, volunteer teams, water and catering prasad, crowd safety and fire checks).

### 2. Milestone Attributes & Fields
Each milestone in the schedule contains:
- `milestone_id`: Stable identifier with category prefix (`M-WED-01` through `M-WED-09`, `M-BDY-01` through `M-BDY-07`, `M-COM-01` through `M-COM-08`).
- `title`: Short task name.
- `description`: Actionable task instructions.
- `category`: Functional domain category (`venue`, `catering`, `decor`, `invitations`, `logistics`, `final_checks`).
- `due_date`: Calendar date in ISO 8601 format (`YYYY-MM-DD`).
- `days_before_event`: Non-negative integer days before the event.
- `priority`: Controlled urgency level (`high`, `medium`, `low`).
- `status`: Completion status (`pending` or `completed`).
- `is_overdue`: Derived Boolean status indicating whether the deadline is in the past relative to the current calendar date (IST). Completed milestones are never marked overdue.

### 3. Date Arithmetic & Edge Case Handling
- **Leap Years & Boundaries:** Standard library `datetime.date` arithmetic accurately navigates leap years (e.g. February 29) and transitions across month and year boundaries without floating-point or timezone drift.
- **Timezone Convention:** Evaluated against Indian Standard Time (Asia/Kolkata, UTC+05:30) calendar date boundaries.
- **Missing Event Date:** If an event profile does not have an `event_date`, `GET /timeline` returns HTTP `200` with `milestones: []` and an advisory message explaining that an event date must first be supplied via `PATCH /api/v1/events/{event_id}`. Dates are never fabricated.
- **Compressed Preparation Window:** If an event is scheduled too soon for the standard template lead times, all milestones are retained in their original sequence. Deadlines that have already passed are flagged with `is_overdue: true` and appropriate schedule compression warnings are returned.

### 4. Milestone Completion Updates
- Milestone completion status can be toggled via `PATCH /api/v1/events/{event_id}/timeline/milestones/{milestone_id}`.
- Payload: `{"status": "completed"}` or `{"status": "pending"}`.
- Clients cannot modify calculated deadlines or identifiers.
- State is preserved in memory across profile updates and budget rebalancing, but is reset upon application process restart (ephemeral in-memory store limitation).

### 5. Sample Timeline Response

```json
{
  "event_id": "EV-35D19DF60424",
  "event_date": "2027-11-20",
  "generated_at": "2026-10-22T16:45:00Z",
  "milestones": [
    {
      "milestone_id": "M-WED-01",
      "title": "Set wedding budget & initial guest estimate",
      "description": "Establish total budget allocations in INR and draft the preliminary family guest headcount.",
      "category": "logistics",
      "due_date": "2027-05-24",
      "days_before_event": 180,
      "priority": "high",
      "status": "pending",
      "is_overdue": false
    },
    {
      "milestone_id": "M-WED-02",
      "title": "Shortlist and book wedding venue / mandap",
      "description": "Inspect banquet halls or outdoor lawns, verify booking advances, and reserve auspicious dates.",
      "category": "venue",
      "due_date": "2027-06-23",
      "days_before_event": 150,
      "priority": "high",
      "status": "completed",
      "is_overdue": false
    },
    {
      "milestone_id": "M-WED-09",
      "title": "Complete final rehearsal, vendor contacts & day-of checklist",
      "description": "Verify remaining cash/NEFT balances for vendors, brief the family council, and print run-sheets.",
      "category": "final_checks",
      "due_date": "2027-11-18",
      "days_before_event": 2,
      "priority": "high",
      "status": "pending",
      "is_overdue": false
    }
  ],
  "warnings": []
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).

