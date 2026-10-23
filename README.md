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

### Interactive Planning Console Navigation

The web frontend at `http://localhost:8000` is an interactive planning console styled in **Jet Black (`#050505`)**, **Royal Amethyst (`#3B0A6B`)**, and **Electric Cyan (`#00E5FF`)**. It connects directly to the backend APIs across ten views:

1. **Overview (`#overview`)**: Quick metric tiles (total budget, headcount, milestone progress %, critical risks count), 8-category budget allocation bar, upcoming milestones, vendor progress, risk alert teaser, and family council summary.
2. **Event Details (`#event-details`)**: Complete event profile breakdown, live profile editor (`PATCH /api/v1/events/{id}`), and list of all stored event profiles.
3. **Budget Planner (`#budget`)**: Visual breakdown of all 8 categories (Venue, Catering, Decor, Photo/Video, Attire/Beauty, Entertainment, Logistics, Contingency Buffer), per-guest cost calculation, buffer health status (≥ 5%), and interactive deterministic budget rebalancer.
4. **Timeline (`#timeline`)**: Chronological milestone checklist with calendar deadlines, lead times (`T-150 days`), overdue alerts, category filters, and one-click completion toggles.
5. **Vendor Checklist (`#vendors`)**: 9-item vendor coordination workflow with status filters, booking progression badges (`not_started`, `researching`, `contacted`, `booked`), and update modal for assigning vendors and notes.
6. **Event Ideas (`#ideas`)**: Personalized, budget-aware creative recommendations with category filters, feasibility fit pills, execution tips, and lower-cost alternatives.
7. **Risk Analysis (`#risks`)**: Pre-mortem failure mode cards with heuristic priority scores (1 to 12), warning signs, preventive measures, contingency plans, and disclaimers.
8. **Family Council (`#council`)**: Simulated deliberation across four distinct personas (*The Budget Guardian*, *The Guest Comfort Advocate*, *The Tradition & Experience Keeper*, *The Logistics & Risk Planner*), creative trade-offs, and executive verdict.
9. **Crisis Recovery Center (`#crisis`)**: Real-time evaluation of event disruptions, severity triage (1 to 5), 3-tier actionable recovery playbooks, ready-to-send bilingual WhatsApp alerts, and plan saving.
10. **Crisis Recovery History & Action Tracker (`#recovery-history`)**: Event-scoped audit trail of evaluated crises, individual recovery drill-down, interactive action item tracking (`pending`, `in_progress`, `completed`), live progress computation, and coordination notes.

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
| `GET` | `/api/v1/events/{event_id}/ideas` | Retrieve personalized, budget-aware recommendations with AI orchestration and fallback |
| `GET` | `/api/v1/events/{event_id}/risks` | Retrieve event pre-mortem failure mode analysis, scoring, and contingency plan |
| `GET` | `/api/v1/events/{event_id}/family-council` | Retrieve four-persona family council deliberation, trade-offs, and recommendations |
| `GET` | `/api/v1/crisis/types` | List available crisis scenario taxonomy types |
| `POST` | `/api/v1/crisis/evaluate` | Evaluate an event-day disruption and generate a 3-tier recovery plan |
| `POST` | `/api/v1/events/{event_id}/crisis/recoveries` | Save a validated recovery plan and track selected action items |
| `GET` | `/api/v1/events/{event_id}/crisis/recoveries` | List recovery history records for an event (newest first) |
| `GET` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}` | Retrieve individual recovery record details and actions |
| `PATCH` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}` | Update recovery record status or situation description |
| `PATCH` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}/actions/{action_id}` | Update action item execution status or coordination notes |
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

## Personalized Event Ideas & Recommendations

PlanProof AI generates personalized, culturally grounded, budget-aware creative recommendations for weddings, birthdays, and community celebrations.

> [!IMPORTANT]
> **Advisory Inspiration Disclaimer:**
> Recommendations, qualitative cost levels (`low`, `medium`, `high`, `unknown`), and budget-fit ratings (`fits`, `possible_with_adjustments`, `unknown`) are relative qualitative planning estimates for creative inspiration. They do **not** constitute real vendor discovery, verified quotes, discounts, or guaranteed prices. Gemini or any external model is **never** permitted to calculate authoritative budget arithmetic.

### 1. Supported Event Types & Categories

Recommendations are strictly tailored to the specific celebration type:
- **`wedding`**: Heritage welcome decor, eco-mandap setup, live regional food counters, sangeet acoustic entertainment, elder hospitality, and food rescue protocols.
- **`birthday`**: Interactive themed adventures, biodegradable balloon installations, interactive snack stations, cooperative treasure quests, puppetry/magic shows, and quiet sensory nooks.
- **`community_event`**: Civic welcome rangoli, reusable modular stage backdrops, token-based community langar/meals, neighborhood cultural open-mic, barrier-free ramps, and 3-bin waste sorting stations.

Ideas span 8 standardized categories:
1. `theme_atmosphere`: Theme and ambience concepts.
2. `decoration`: Stage, venue, and focal backdrop design.
3. `food_refreshments`: Curated menus, live counters, and dietary coordination.
4. `guest_engagement`: Interactive games, photo nooks, and trivia.
5. `entertainment`: Acoustic ensembles, regional troupes, and performers.
6. `invitations_communication`: Digital video/e-invites and logistics communication.
7. `accessibility_inclusivity`: Senior citizen, toddler, and differently-abled accommodation.
8. `sustainable_planning`: Zero single-use plastic, surplus food recovery, and eco-friendly favors.

### 2. Budget Awareness & Qualitative Cost Levels

- **Total Budget & Guest Headcount Context:** The recommendation engine evaluates the event's total budget and per-guest allocation (`total_budget_inr / guest_count`).
- **Cost Levels:** Qualitative indicators (`low`, `medium`, `high`, `unknown`) indicating relative financial weight.
- **Budget Fit:**
  - `fits`: Idea fits comfortably within the current budget profile.
  - `possible_with_adjustments`: Idea may stretch modest budgets; lower-cost alternatives are provided.
  - `unknown`: Feasibility cannot be determined without additional user parameters.
- **Lower-Cost Alternatives:** All medium and high cost ideas include concrete, actionable simpler or DIY alternatives (e.g., local seasonal marigolds instead of imported orchids).

### 3. Provenance & Source Attribution

PlanProof AI explicitly attributes the origin of every recommendation:
- **`rules`** (`source="rules"` on item, `source="deterministic"` on envelope): Deterministic, calibrated rule catalog executed when offline, in fallback mode, or when Gemini is unconfigured.
- **`demo`** (`source="demo"` on item and envelope): Deterministic, synthetic illustrative examples returned in `AI_MODE=demo`.
- **`gemini`** (`source="gemini"` on item and envelope): Structured recommendations generated via Google Gemini AI when configured and in `auto` or `gemini` mode.

### 4. Safety & Untrusted User Notes

User-provided `theme_notes` (e.g. style preferences, cultural traditions) are treated strictly as untrusted text. Prompt injection attempts (e.g., instructions to alter statuses, overwrite budgets, or leak keys) are neutralized and cannot override system behavior or Pydantic validation schemas.

### 5. API Endpoint: `GET /api/v1/events/{event_id}/ideas`

#### Query Parameters
- `category` *(optional)*: Filter by one of the 8 categories (e.g. `?category=food_refreshments`).
- `limit` *(optional, default 10, range 1–50)*: Cap the number of ideas returned.

#### Example Request
```http
GET /api/v1/events/EV-A1B2C3D4/ideas?limit=3 HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response (`AIResultEnvelope[EventIdeasResponse]`)
```json
{
  "status": "success",
  "source": "deterministic",
  "data": {
    "event_id": "EV-A1B2C3D4",
    "event_type": "wedding",
    "total_ideas": 3,
    "ideas": [
      {
        "id": "IDEA-WED-01",
        "category": "theme_atmosphere",
        "title": "Heritage Marigold & Brass Diya Welcome Atmosphere",
        "description": "Create a warm, culturally resonant arrival experience featuring brass urlis filled with floating rose petals and diyas, accented with fragrant local marigold (genda phool) arches.",
        "reason": "Sets a welcoming traditional celebratory mood suitable for all age groups while remaining cost-effective. Suitable for your planned budget of ₹1,500,000 for 300 guests (~₹5,000/guest) in Jaipur.",
        "estimated_cost_level": "medium",
        "budget_fit": "fits",
        "implementation_tips": [
            "Source brass urlis from family collections or rent locally from traditional wedding utensil providers.",
            "Procure seasonal loose marigolds in bulk directly from wholesale flower markets at dawn.",
            "Arrange battery-operated or tea-light floating diyas for child and fabric safety."
        ],
        "alternatives": [
            "Use terracotta bowls painted with gold acrylic instead of heavy brass vessels.",
            "Focus marigold garlands strictly around the entrance arch and use warm fairy lights for secondary pathways."
        ],
        "source": "rules"
      }
    ],
    "budget_context_inr": 1500000,
    "disclaimer": "Recommendations and cost levels are qualitative planning guidance for inspiration. They do not constitute real vendor discovery, verified quotes, or guaranteed prices."
  },
  "message": "Deterministic fallback applied successfully.",
  "warnings": []
}
```

---

## Event Pre-Mortem Risk Analysis Engine

PlanProof AI includes a dedicated, deterministic **Pre-Mortem Risk Analysis Engine** for weddings, birthdays, and community events. Rather than waiting for a crisis to occur during an event, the pre-mortem engine analyzes the saved event profile parameters, budget allocations, vendor booking progress, timeline runway, and location characteristics to uncover potential vulnerabilities and provide actionable mitigations and contingency playbooks in advance.

### 1. Key Capabilities & Invariants
- **Deterministic Foundation**: Built on pure Python business rules. Does not depend on external AI availability and never crashes when offline.
- **AI Enrichment**: In `auto` mode (with configured `GEMINI_API_KEY`) or `gemini` mode, Gemini AI enriches risks with contextual narrative explanations and tailored playbooks, while strictly respecting deterministic priority scores, bounds, and profile fields.
- **Security & Untrusted User Notes**: User-provided `theme_notes` are sanitized and explicitly treated as untrusted text. Prompt injections attempting to override likelihoods, impacts, or scores are neutralized.
- **Resource Immutability**: Calculating pre-mortem risks is strictly non-mutating and does not alter stored event profiles, budgets, timelines, or checklists.

### 2. Supported Risk Categories
The engine identifies failure modes across 10 core dimensions:
1. `budget_overrun`: Emergency contingency buffer exhaustion (< 5%) or budget allocation deficits.
2. `timeline_delay`: Compressed countdown runway (< 60 days) with pending essential milestones.
3. `vendor_coordination`: Critical foundational vendors (venue, catering, photography, sound) uncontracted.
4. `guest_catering`: Per-guest catering budget stretched below regional baseline or large headcount crowd surge.
5. `weather_exposure`: Outdoor, lawn, terrace, or monsoon season vulnerability without weatherproof cover.
6. `transport_logistics`: Congested metro transit corridors, peak wedding dates, and outstation parking shortages.
7. `safety_accessibility`: Multi-generational guest accessibility, senior mobility, first-aid, and child safety.
8. `permissions_compliance`: Municipal sound curfews, police NOCs, statutory permits, and decibel limits.
9. `supplier_disruption`: Day-of supplier cancellations or single points of failure without standby backup contacts.
10. `communication_gaps`: Uncentralized family coordination, ambiguous vendor points of contact, or unconfirmed RSVPs.

### 3. Transparent Deterministic Scoring Formula
Risk priority scores are calculated using transparent integer weights:
- **Likelihood Weights**:
  - `low`: 1
  - `unknown`: 1 *(safely handled as conservative default)*
  - `medium`: 2
  - `high`: 3
- **Impact Weights**:
  - `low`: 1
  - `medium`: 2
  - `high`: 3
  - `critical`: 4

$$\text{priority\_score} = \text{likelihood\_weight} \times \text{impact\_weight}$$

- **Range**: Strictly bounded integer between `1` (minimum) and `12` (maximum).
- **Monotonicity Invariant**: Higher likelihood or impact is mathematically guaranteed never to decrease the priority score.
- **Severity Classification**:
  - `critical`: Priority score $\ge 9$
  - `high`: Priority score $6 \dots 8$
  - `medium`: Priority score $3 \dots 5$
  - `low`: Priority score $< 3$
- **Deduplication & Stable Ordering**: Duplicate risks are eliminated, and items are sorted deterministically by `(-priority_score, id)`.

### 4. Planning Estimates Disclaimer
> **Important Disclaimer:**
> Pre-mortem risk scores and assessments are **qualitative planning estimates** based on deterministic heuristics and current profile parameters. They are **not statistically calibrated actuarial probabilities or guaranteed predictions of future outcomes**.

### 5. Missing Data Handling
When optional event data is missing, the engine gracefully limits its assessment without fabricating details or crashing:
- **Missing Event Date**: Countdown-dependent milestone crunch risks are omitted. An advisory notice is added to `missing_data_warnings`.
- **Missing City**: Transit logistics and local municipal permit checks assume regional defaults with an advisory warning.
- **Empty Vendor Checklist**: Uncontracted vendor progression risks are skipped with an advisory warning.

### 6. API Endpoint: `GET /api/v1/events/{event_id}/risks`

#### Query Parameters
- `reference_date` *(optional ISO date, e.g. `2027-04-15`)*: Simulated reference date for timeline calculations (defaults to current date).

#### Example Request
```http
GET /api/v1/events/EV-35D19DF60424/risks HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response (`AIResultEnvelope[EventRisksResponse]`)
```json
{
  "status": "success",
  "source": "deterministic",
  "data": {
    "event_id": "EV-35D19DF60424",
    "event_type": "wedding",
    "total_risks": 4,
    "summary": {
      "critical_risks": 1,
      "high_risks": 2,
      "medium_risks": 1,
      "low_risks": 0,
      "highest_priority_score": 12
    },
    "risks": [
      {
        "id": "RISK-BUDGET-BUFFER",
        "category": "budget_overrun",
        "title": "Insufficient Emergency Contingency Buffer",
        "description": "Emergency reserve is allocated at ₹0 (0.0% of total budget), which is below the recommended 5–10% safety cushion required to absorb unexpected vendor surcharges or overtime.",
        "likelihood": "high",
        "impact": "critical",
        "priority_score": 12,
        "warning_signs": [
          "Zero or nominal allocation in emergency_buffer category.",
          "No financial margin reserved for last-minute guest headcount additions."
        ],
        "mitigations": [
          "Rebalance budget immediately to protect a strict 5–10% unallocated contingency reserve.",
          "Cap secondary aesthetic decor expenditures until core contracts are signed with locked rates."
        ],
        "contingency_plan": "Identify non-essential aesthetic items that can be cancelled 7 days prior without penalty.",
        "related_budget_category": "buffer",
        "related_milestone_id": null,
        "source": "rules"
      },
      {
        "id": "RISK-VENDOR-UNBOOKED",
        "category": "vendor_coordination",
        "title": "Critical Foundational Vendors Uncontracted",
        "description": "Core foundational vendor items (venue, catering) have not progressed past research phase.",
        "likelihood": "medium",
        "impact": "critical",
        "priority_score": 8,
        "warning_signs": [
          "Venue or catering contracts remain in 'not_started' or 'researching' status."
        ],
        "mitigations": [
          "Execute venue inspection walk-throughs within 72 hours and place earnest deposits."
        ],
        "contingency_plan": "Maintain 2 backup venue/caterer contacts with immediate booking availability on standby.",
        "related_budget_category": "venue",
        "related_milestone_id": null,
        "source": "rules"
      }
    ],
    "missing_data_warnings": [],
    "disclaimer": "Risk scores and assessments are deterministic planning estimates based on current event profile parameters, not statistically calibrated probabilities or guaranteed predictions."
  },
  "message": "Pre-mortem risk analysis completed successfully.",
  "warnings": []
}
```

---

## Four-Persona Family Council

The **Family Council** simulates four clearly differentiated, constructive perspectives reviewing an event plan. Rather than returning a single homogenous review, the council surfaces healthy planning tensions—such as balancing fiscal conservatism against guest hospitality or logistical simplicity against elaborate cultural traditions.

> **Important Disclaimer:**
> The Family Council personas are **simulated heuristic planning perspectives**, not real people, family member accounts, legal guardians, or licensed professional advisors. They do not communicate with third parties, make binding decisions, or replace personal judgment.

### 1. The Four Personas and Their Responsibilities

| Persona | ID | Perspective & Core Focus | Grounded Data Sources |
|---|---|---|---|
| **The Budget Guardian** | `budget_guardian` | Fiscal discipline, emergency buffer protection, cost-per-guest scrutiny, and identifying avoidable overspending. | Total budget, category allocations, emergency buffer %, guest count, vendor estimated costs. |
| **The Guest Comfort Advocate** | `guest_comfort_advocate` | Hospitality, dietary variety, physical comfort, climate readiness, seating adequacy, and accessibility. | Guest count, venue/catering checklist status, weather/season notes, accessibility planning notes. |
| **The Tradition & Experience Keeper** | `tradition_experience_keeper` | Meaningful family moments, theme cohesion, photographic milestones, and honoring explicit preferences. | Explicit `theme_notes`, `custom_notes`, event type, milestone schedule. *(Strictly avoids cultural/religious assumptions).* |
| **The Logistics & Risk Planner** | `logistics_risk_planner` | Timeline feasibility, vendor contract progression, countdown pressures, and pre-mortem risk mitigations. | Milestones, vendor checklist statuses, pre-mortem risks (`RISK-*`). |

### 2. Avoidance of Unsupported Cultural Assumptions

PlanProof AI strictly adheres to **cultural neutrality**:
- **Zero Cultural Assumptions**: The system never infers or assumes religion, caste, sect, ritual practices, or family hierarchy.
- **Explicit Input Only**: Cultural preferences are only incorporated when explicitly supplied by the user in `theme_notes` or planning text.
- **Inclusive Alternatives**: When cultural context is absent, the *Tradition & Experience Keeper* highlights that no specific cultural traditions were specified and offers open-ended suggestions for family dialogue (e.g., interactive guest books, storytelling toasts, or photo walls).
- **Nuanced Accessibility Guidance**: The *Guest Comfort Advocate* notes unverified accessibility details as gentle planning reminders rather than asserting non-compliance.

### 3. Creative Trade-Offs & Disagreement (No False Consensus)

The council recognizes that event planning involves genuine compromises. Rather than forcing a artificial consensus, the summary generates trade-offs between competing priorities:
- **Budget vs. Guest Comfort**: Reallocating decor funds toward climate-controlled seating or premium buffet options.
- **Logistics vs. Tradition**: Simplifying multi-ceremony transitions to avoid guest fatigue and timeline delays.
- **Buffer Protection vs. Vendor Upgrades**: Resisting non-essential vendor add-ons to preserve emergency funds.

### 4. Deterministic Baseline & AI Enrichment

- **Deterministic Baseline (Default)**: All 4 personas evaluate verified event profile attributes, calculated budgets, timelines, checklists, and pre-mortem risks using rule-based heuristics. The council functions completely offline without external API dependencies.
- **Optional Gemini Enrichment**: When enabled, the existing AI orchestrator generates enriched, conversational evaluations. Prompts are sanitized against prompt injection, strictly preventing the AI from modifying authoritative budget numbers, dates, or risk scores.
- **Automatic Fallback**: If Gemini is offline, times out, or returns a schema violation, the system automatically falls back to deterministic evaluations with source attribution in the envelope.

### 5. API Endpoint: `GET /api/v1/events/{event_id}/family-council`

#### Query Parameters
- `reference_date` *(optional ISO date, e.g. `2027-04-15`)*: Simulated reference date for timeline calculations (defaults to current date).

#### Example Request
```http
GET /api/v1/events/EV-35D19DF60424/family-council HTTP/1.1
Host: localhost:8000
Accept: application/json
```

#### Example Response (`AIResultEnvelope[EventFamilyCouncilResponse]`)
```json
{
  "status": "success",
  "source": "deterministic",
  "data": {
    "event_id": "EV-35D19DF60424",
    "event_type": "wedding",
    "council_summary": {
      "overall_verdict": "The event plan shows strong foundational structure with 4 active personas providing balanced oversight.",
      "strongest_aspects": [
        "Core foundational budget structure is established with allocated spending categories.",
        "Clear timeline and milestone scheduling in place."
      ],
      "critical_concerns": [
        "Core foundational vendor items (venue, catering) have not progressed past research phase.",
        "Emergency reserve is allocated at ₹0 (0.0% of total budget), which is below the recommended 5–10% safety cushion."
      ],
      "next_actions": [
        "Rebalance budget immediately to protect a strict 5–10% unallocated contingency reserve.",
        "Finalize and contract the primary venue and catering vendors.",
        "Review accessibility requirements with all elderly guests and the venue management."
      ],
      "trade_offs": [
        {
          "title": "Cost Efficiency vs. Premium Guest Hospitality",
          "perspective_a": "The Budget Guardian",
          "perspective_b": "The Guest Comfort Advocate",
          "description": "The Budget Guardian favors tighter per-guest cost caps, whereas the Guest Comfort Advocate prioritizes extensive catering spreads and hospitality comfort.",
          "suggested_compromise": "Opt for quality over variety in the menu to control costs while ensuring high culinary satisfaction and prompt service."
        }
      ]
    },
    "personas": [
      {
        "persona_id": "budget_guardian",
        "persona_name": "The Budget Guardian",
        "perspective": "Focuses on affordability, budget allocations, emergency buffer protection, and avoidable overspending.",
        "overall_assessment": "Budget requires immediate review: emergency buffer is critically underfunded.",
        "strengths": [
          "Total budget established at ₹1,500,000 for 250 guests (₹6,000 per guest)."
        ],
        "concerns": [
          "Emergency buffer is 0.0% of total budget (₹0), below the recommended 5–10% safety threshold."
        ],
        "recommendations": [
          "Rebalance budget categories to ringfence at least 5% (₹75,000) as an unallocated emergency buffer."
        ],
        "priority": "high",
        "source": "rules"
      },
      {
        "persona_id": "guest_comfort_advocate",
        "persona_name": "The Guest Comfort Advocate",
        "perspective": "Focuses on guest hospitality, catering adequacy, dietary diversity, seating, and inclusive experiences.",
        "overall_assessment": "Planning for 250 guests requires attention to catering capacity and venue amenities.",
        "strengths": [
          "Event scale of 250 guests allows for structured group seating and focused catering management."
        ],
        "concerns": [
          "Accessibility planning for elderly guests or guests with mobility needs is not yet documented."
        ],
        "recommendations": [
          "Inquire with venue management regarding wheelchair ramps, elevator access, and priority seating near restrooms."
        ],
        "priority": "medium",
        "source": "rules"
      },
      {
        "persona_id": "tradition_experience_keeper",
        "persona_name": "The Tradition & Experience Keeper",
        "perspective": "Focuses on meaningful traditions, family preferences, event theme cohesion, and memorable shared experiences.",
        "overall_assessment": "Cultural traditions and family preferences are currently open for definition.",
        "strengths": [
          "Open planning canvas allows families to intentionally choose rituals and traditions that resonate most."
        ],
        "concerns": [
          "Specific family traditions, cultural rituals, or ceremonial priorities have not yet been specified."
        ],
        "recommendations": [
          "Schedule an informal family conversation to identify 1-2 non-negotiable traditions or experiences to incorporate."
        ],
        "priority": "low",
        "source": "rules"
      },
      {
        "persona_id": "logistics_risk_planner",
        "persona_name": "The Logistics & Risk Planner",
        "perspective": "Focuses on timeline feasibility, vendor coordination, preparation gaps, and pre-mortem risk mitigations.",
        "overall_assessment": "1 critical pre-mortem risks and 2 unbooked vendors require immediate logistical focus.",
        "strengths": [
          "Timeline milestones and vendor tracking workflows are active."
        ],
        "concerns": [
          "Critical risk 'RISK-VENDOR-UNBOOKED': Core foundational vendor items (venue, catering) have not progressed past research phase."
        ],
        "recommendations": [
          "Execute venue inspection walk-throughs within 72 hours and place earnest deposits."
        ],
        "priority": "high",
        "source": "rules"
      }
    ],
    "disclaimer": "The Family Council provides simulated planning perspectives for exploration and discussion. It does not replace professional event planning, legal, financial, or family consensus decisions."
  },
  "message": "Family council assessment completed successfully.",
  "warnings": []
}
```

---

## Crisis Recovery History & Action Tracker

PlanProof AI includes an event-scoped **Crisis Recovery History and Action Tracker** allowing planners and families to save recovery playbooks generated during crisis triage, select specific mitigation actions to track, log real-time coordination notes, and monitor completion through to resolution.

### 1. Recovery Records & Endpoints

| Method | Route | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/events/{event_id}/crisis/recoveries` | Save a validated recovery plan to the event with selected actions |
| `GET` | `/api/v1/events/{event_id}/crisis/recoveries` | List all recovery records for the event, ordered newest first |
| `GET` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}` | Retrieve a specific recovery record with its plan snapshot and tracked actions |
| `PATCH` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}` | Update record-level status (`open`, `in_progress`, `resolved`) or description |
| `PATCH` | `/api/v1/events/{event_id}/crisis/recoveries/{recovery_id}/actions/{action_id}` | Update an individual action's status (`pending`, `in_progress`, `completed`) or notes |

### 2. Data Models & Status Values

#### Recovery Record Status (`RecoveryStatus`)
- `open`: Initial state upon saving. Mitigation actions are awaiting execution.
- `in_progress`: At least one action item has begun execution or is completed while others remain.
- `resolved`: All tracked action items have reached completion, or the host has explicitly marked the crisis resolved.

#### Action Item Status (`RecoveryActionStatus`)
- `pending`: Action is queued for execution.
- `in_progress`: Coordination or mitigation is actively underway.
- `completed`: Mitigation action has been executed successfully.

### 3. Action Tracking & Progress Calculation Rules

When saving a recovery plan, users can select all recommended actions or cherry-pick specific actions relevant to their situation:
- **Stable IDs**: Action items receive deterministic, stable identifiers (e.g., `ACT-A1B2C3D4`) that persist across updates.
- **Source Attribution**: The record truthfully records whether the underlying recovery plan was generated via `rules`, `demo`, or `gemini`.
- **Progress Metrics**: Summary metrics are dynamically recalculated upon every action change:
  - `total_actions`: Total number of tracked actions.
  - `pending_actions`: Count of actions with `pending` status.
  - `in_progress_actions`: Count of actions with `in_progress` status.
  - `completed_actions`: Count of actions with `completed` status.
  - `completion_percentage`: `round((completed_actions / total_actions) * 100, 1)` (or `0.0%` if no actions tracked).
- **Resolution Safeguards**:
  - Generating or saving a recovery plan **never** automatically marks a crisis resolved.
  - As long as actions remain incomplete (`completed_actions < total_actions`), automatic progress recalculation keeps the record status as `in_progress` (or `open`), preventing premature auto-resolution.
  - When all actions reach `completed` (`completed_actions == total_actions > 0`), the record automatically transitions to `resolved`.
  - Planners can also explicitly update the overall status via `PATCH /api/v1/events/{event_id}/crisis/recoveries/{recovery_id}`.
- **Resource Isolation**: Updating recovery records or action items is strictly event-scoped and never mutates the event's budget allocations, timeline schedule, or vendor checklist.

### 4. Persistence Limitations

PlanProof AI currently operates on an **in-memory event store (`EventStore`)** for rapid prototyping and zero-dependency deployments.
- **Ephemeral Storage**: All saved events, recovery records, and action notes reside in process memory.
- **Restart Notice**: If the FastAPI application server restarts or reloads, previously saved records will be reset to initial state.
- **Production Roadmap**: Production deployments will back this domain model with a persistent relational or document store (PostgreSQL/Cloud SQL).

### 5. Using the Recovery History Dashboard

1. **Evaluate a Crisis**: Go to **Crisis Recovery Center (`#crisis`)**, choose a scenario (or custom disruption), and click **Run Crisis Recovery Drill**.
2. **Save & Select Actions**: In the evaluation results, click **Save Plan & Track Actions**. A modal allows editing situation notes and selecting which recommended actions to track.
3. **Track Execution**: Navigate to **Recovery History (`#recovery-history`)** to review all past crises for the active event. Click any record to inspect the complete saved plan, update action status dropdowns (`Pending` → `In Progress` → `Completed`), log contact notes, or adjust the overall recovery status.

---

## License

This project is licensed under the [MIT License](LICENSE).


