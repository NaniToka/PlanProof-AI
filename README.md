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
| `POST` | `/api/v1/validate-event` | Strict domain validation for event planning requests |
| `POST` | `/api/v1/budget/calculate` | Deterministic 8-category budget allocation (Hamilton-Hare method) |
| `POST` | `/api/v1/budget/rebalance` | Budget rebalancing with essential category preservation |
| `POST` | `/api/v1/plan/timeline` | AI-orchestrated event planning checklist and run-sheet with fallback |
| `POST` | `/api/v1/plan/risks` | AI-orchestrated pre-mortem risk assessment with deterministic fallback |
| `GET` | `/docs` | OpenAPI / Swagger interactive documentation |

---

## License

This project is licensed under the [MIT License](LICENSE).
