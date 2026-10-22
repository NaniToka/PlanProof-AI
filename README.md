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
| `GET` | `/api/v1/events/{event_id}/vendors/checklist` | Retrieve event-specific vendor checklist and coordination status summary |
| `PATCH` | `/api/v1/events/{event_id}/vendors/checklist/{item_id}` | Update task status, notes, priority, vendor name, or booking status |
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

## Event Vendor Checklist & Coordination Workflow

PlanProof AI provides a deterministic, event-specific vendor coordination checklist and tracking workflow for weddings, birthdays, and community events.

> **Important Marketplace & Availability Disclaimer:**
> This feature is strictly a **vendor planning, checklist, and coordination tracker**. It is **not** a real vendor marketplace, directory, or commercial reservation platform. PlanProof AI **never** invents real vendor businesses, phone numbers, contact details, pricing quotations, or confirmed reservations. All vendor names, contact statuses, and notes reflect user-recorded information only.

### 1. Supported Event Types & Tailored Templates
Checklist tasks are calibrated to the celebration type, avoiding irrelevant tasks:
- **Wedding (`wedding`)** — 9 comprehensive tasks:
  - `VCL-WED-01` (`venue_permissions`, 150 days prior, High): Hall/lawn reservation & municipal sound curfew permissions.
  - `VCL-WED-02` (`catering_refreshments`, 120 days prior, High): Food tasting, regional live counters, guaranteed guest plate count.
  - `VCL-WED-03` (`photography_videography`, 90 days prior, High): Candid photo/video crew, drone permits, album delivery terms.
  - `VCL-WED-04` (`attire_beauty`, 75 days prior, Medium): Lehenga/sherwani tailoring sessions & bridal makeup artist bookings.
  - `VCL-WED-05` (`decoration_setup`, 60 days prior, Medium): Stage layout, mandap floral installations, entrance arch, backup power.
  - `VCL-WED-06` (`invitations_coordination`, 60 days prior, Medium): Formal wedding card printing, RSVP list setup, digital dispatch.
  - `VCL-WED-07` (`entertainment_equipment`, 45 days prior, Medium): DJ console, sangeet audio setup, traditional dhol/shehnai welcome artists.
  - `VCL-WED-08` (`transport_logistics`, 30 days prior, Medium): Outstation guest hotel room blocks & airport/station shuttles.
  - `VCL-WED-09` (`cleanup_post_event`, 1 day prior, High): Mandap teardown, floral composting, venue deposit settlement.
- **Birthday (`birthday`)** — 8 focused tasks (no wedding-specific attire or mandap):
  - `VCL-BDY-01` (`venue_permissions`, 21 days prior, High): Party hall, restaurant room, or clubhouse booking with cake refrigeration.
  - `VCL-BDY-02` (`invitations_coordination`, 14 days prior, Medium): Digital WhatsApp invitation cards and parent RSVP headcount tracking.
  - `VCL-BDY-03` (`photography_videography`, 14 days prior, Low): Cake cutting highlights and family candid photo coverage.
  - `VCL-BDY-04` (`catering_refreshments`, 12 days prior, High): Custom themed tier birthday cake, kid-friendly buffet finger foods.
  - `VCL-BDY-05` (`entertainment_equipment`, 10 days prior, Medium): Game host, mascot/magician, party music sound speaker.
  - `VCL-BDY-06` (`decoration_setup`, 7 days prior, Medium): Theme balloon arch garland, personalized banner, photo booth frame.
  - `VCL-BDY-07` (`transport_logistics`, 3 days prior, Medium): Procure and assemble age-appropriate return gift favor bags.
  - `VCL-BDY-08` (`cleanup_post_event`, 1 day prior, High): Personal gift packing, balloon teardown, venue cleanup inspection.
- **Community Event (`community_event`)** — 8 civic coordination tasks (no bridal attire; focus on municipal NOCs, crowd safety, PA audio, volunteers):
  - `VCL-COM-01` (`venue_permissions`, 45 days prior, High): Community ground/auditorium, police NOC, sound permit, fire clearance.
  - `VCL-COM-02` (`entertainment_equipment`, 30 days prior, High): Heavy-duty PA audio console, microphones, diesel generator backup.
  - `VCL-COM-03` (`invitations_coordination`, 21 days prior, Medium): Society circulars, WhatsApp broadcasts, neighborhood banner posters.
  - `VCL-COM-04` (`decoration_setup`, 14 days prior, High): Weatherproof shamiana tent canopy, folding chairs, registration counter.
  - `VCL-COM-05` (`transport_logistics`, 14 days prior, Medium): Volunteer marshal badges, traffic/parking lanes, wheelchair/elderly ramp routes.
  - `VCL-COM-06` (`catering_refreshments`, 10 days prior, High): Certified drinking water cans, compostable cups, community meal/prasad.
  - `VCL-COM-07` (`photography_videography`, 7 days prior, Low): Documentation photographer for VIP felicitations, crowd moments, archives.
  - `VCL-COM-08` (`cleanup_post_event`, 1 day prior, High): Eco waste segregation bins, volunteer cleanup squad, grounds restoration.

### 2. Item Fields & Status Tracking
Every checklist item tracks both execution progress and user-recorded vendor booking:
- `status`: Controlled task progress (`pending`, `in_progress`, `completed`, `skipped`). Defaults to `pending`.
- `booking_status`: User-recorded vendor progression (`not_started`, `researching`, `contacted`, `booked`, `cancelled`). Defaults to `not_started`. **Never automatically marked as booked.**
- `vendor_name`: Optional user-entered name (max 100 characters). Defaults to `null`.
- `notes`: Optional user-entered coordination notes (max 500 characters). Defaults to `null`.
- `due_date`: Calendar date derived from `event_date - timedelta(days=days_before_event)`. Set to `null` if the event does not have an `event_date`.
- `priority`: Task urgency level (`low`, `medium`, `high`).
- `created_at` / `updated_at`: Server-managed UTC ISO 8601 timestamps.

### 3. API Endpoints

#### `GET /api/v1/events/{event_id}/vendors/checklist`
Retrieves or lazily initializes the event-specific vendor checklist and summary.
- Returns `200 OK` with checklist items, status summary breakdown, and advisory warnings (e.g. if `event_date` is missing).
- Returns `404 Not Found` if `event_id` is invalid.
- Repeated GET requests return the existing checklist and do not create duplicate items.

#### `PATCH /api/v1/events/{event_id}/vendors/checklist/{item_id}`
Updates permitted fields on an individual checklist item.
- Permitted body fields: `status`, `notes`, `priority`, `vendor_name`, `booking_status`.
- Disallowed fields (`id`, `category`, `due_date`, `created_at`, `updated_at`) are rejected with `422 Unprocessable Entity` (`extra="forbid"`).
- Returns `404 Not Found` if either `event_id` or `item_id` does not exist.

### 4. Due Date Rules & Date Recalculation
- **Fixed Dates**: When `event_date` is known, `due_date` is deterministically computed via standard calendar arithmetic.
- **Missing Event Date**: If `event_date` is omitted, all items receive `due_date: null` with an explanatory advisory warning. No artificial dates are fabricated.
- **Date Updates**: When `event_date` is updated via `PATCH /api/v1/events/{event_id}`, all checklist item due dates are automatically recalculated to align with the new event date, while strictly preserving user notes, vendor names, priorities, and booking statuses.

### 5. Storage & Persistence Limitations
- Stored in ephemeral application memory (`EventStore`).
- Vendor checklist items and their user-edited states are preserved across profile metadata updates and budget rebalancing requests.
- All stored state is lost when the server process terminates or restarts.

### 6. Sample Checklist Response

```json
{
  "event_id": "EV-9F8E7D6C5B4A",
  "event_type": "wedding",
  "event_date": "2027-11-20",
  "generated_at": "2026-10-22T17:00:00Z",
  "summary": {
    "total_items": 9,
    "pending": 8,
    "in_progress": 0,
    "completed": 1,
    "skipped": 0,
    "booking_statuses": {
      "not_started": 8,
      "researching": 0,
      "contacted": 0,
      "booked": 1,
      "cancelled": 0
    }
  },
  "items": [
    {
      "id": "VCL-WED-01",
      "category": "venue_permissions",
      "title": "Reserve wedding banquet hall / lawn & mandap premises",
      "description": "Inspect venue capacity, negotiate dining & mandap zones, verify advance terms, and secure municipal sound permissions.",
      "status": "completed",
      "due_date": "2027-06-23",
      "days_before_event": 150,
      "priority": "high",
      "notes": "Contract signed with Royal Orchid Lawns; 25% booking advance paid.",
      "vendor_name": "Royal Orchid Lawns",
      "booking_status": "booked",
      "created_at": "2026-10-22T17:00:00Z",
      "updated_at": "2026-10-22T17:05:00Z"
    },
    {
      "id": "VCL-WED-02",
      "category": "catering_refreshments",
      "title": "Contract wedding caterer and finalize multi-meal menus",
      "description": "Sample food tastings, lock in regional live counters, guaranteed guest plate count, and service staff ratios.",
      "status": "pending",
      "due_date": "2027-07-23",
      "days_before_event": 120,
      "priority": "high",
      "notes": null,
      "vendor_name": null,
      "booking_status": "not_started",
      "created_at": "2026-10-22T17:00:00Z",
      "updated_at": "2026-10-22T17:00:00Z"
    }
  ],
  "warnings": []
}
```

---

## License

This project is licensed under the [MIT License](LICENSE).


