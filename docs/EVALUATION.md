# PlanProof AI — Dataset Engineering & Strict Validation (Milestone 2)

## 1. Dataset Audit Findings & Edge Cases

An exhaustive audit of the dataset and domain rules was conducted during Milestone 2.

### A. Discovery and File Mapping
- **Discovered CSV:** Located at `dataset.csv` in the project root.
- **Expected CSV Name:** `data/crisis_scenarios.csv`.
- **Preservation Action:** `dataset.csv` remains preserved in the project root. `data/crisis_scenarios.csv` is maintained as a verified identical copy.
- **SHA-256 Checksum:** `855603b2e04839e0fbff8a7343dcbc869cae5bf2cbf8d3948beda05e0921df03`.

### B. Schema Verification & Critical Finding
The 5,000 crisis records were verified against strict domain schemas:

| Column | Strict Type | Missing Values | Validation Constraints |
| :--- | :--- | :---: | :--- |
| `id` | `str` | 0 | Non-empty string (e.g. `CR0000001`) |
| `event_type` | `EventType` Enum | 0 | `wedding`, `birthday`, `community_event` |
| `city_tier` | `CityTier` Enum | 0 | `metro`, `tier2`, `tier3` |
| `guest_count` | `int` | 0 | Positive integer within supported range ($1 \le g \le 2000$) |
| `phase` | `EventPhase` Enum | 0 | `planning`, `day_before`, `event_day` |
| `crisis_type` | `str` | 0 | 12 standardized crisis incident types |
| `severity` | `int` | 0 | Integer strictly in $\{1, 2, 3\}$ |
| `description` | `str` | 0 | Non-empty, non-blank text |
| `recommended_fix` | `str` | 0 | Non-empty, actionable text |
| `cost_impact_pct_of_budget` | `float` | 0 | Finite float (rejects `NaN`, `inf`). Non-negative for cost additions; negative values permitted **only** for headcount savings (`guest_dropout`) |
| `message_target` | `MessageTarget` Enum | 0 | `vendor`, `guests`, `family` |
| `synthetic` | `bool` | 0 | `True` (synthetic assumptions) |

> [!NOTE]
> **Negative Cost Impact Transparency:**
> In the 5,000-row dataset, exactly 420 records have negative cost impact ($-6.5\%$ to $-0.8\%$). These exclusively correspond to `crisis_type == "guest_dropout"`, where guest cancellations enable catering headcount renegotiations that reduce costs. The schema validator enforces that negative cost impacts are rejected for any crisis other than `guest_dropout`.

---

## 2. Supporting Datasets & Validation Rules

### A. Budget Allocation Allocations (`data/budget_splits.json`)
- Evaluated with `BudgetSplitsDataset` and `BudgetSplitCategories`.
- Enforces presence of all 3 event types (`wedding`, `birthday`, `community_event`) and all 3 city tiers (`metro`, `tier2`, `tier3`).
- Enforces exactly the 8 standard categories (`venue`, `catering`, `decor`, `photo_video`, `attire_beauty`, `entertainment`, `logistics`, `buffer`).
- Disallows missing or extra categories (`extra="forbid"`).
- Rejects allocations where category percentages do not sum to $100.0\%$ (allowing $0.01\%$ float tolerance).

### B. Vendor Booking Checklists (`data/vendor_checklists.json`)
- Evaluated with `VendorChecklistsDataset` and `VendorChecklist`.
- Requires `lead_time_weeks >= 0` integer.
- Requires `typical_advance_pct` finite float in $[0.0, 100.0]$.
- Requires non-empty list of non-empty interview questions.
- Enforces **case-insensitive uniqueness** across vendor category types.

### C. Safe Generator Tooling (`data/generate_dataset.py`)
- Never touches, overwrites, or regenerates `crisis_scenarios.csv` or `dataset.csv`.
- Preserves existing supporting JSON files unless `--overwrite` is explicitly specified.
- Provides `--validate-only` mode for pipeline verification.
- Exits with status 1 on validation failures and 0 on success.

---

## 3. Automated Test Suite Metrics (30 Tests)

| Test Area | Scenarios Covered | Status |
| :--- | :--- | :---: |
| **Real Dataset Ingestion** | Real 5,000 crisis rows loaded and validated | PASS |
| **Enum Representation** | All 3 event types, 3 tiers, 3 phases, 3 targets verified | PASS |
| **Budget Combinations** | All 9 `(event_type, city_tier)` splits verified to sum to 100% | PASS |
| **Vendor Catalog** | All 8 vendors validated with non-negative lead times & advance % | PASS |
| **Missing Column Handling** | Triggers `DatasetMalformedError` | PASS |
| **Empty/Header-Only CSV** | Triggers `DatasetEmptyError` | PASS |
| **Invalid Enum Values** | Invalid event types, city tiers, phases rejected | PASS |
| **Severity Range** | Severity outside 1–3 rejected | PASS |
| **Guest Count Bounds** | Guest count $\le 0$ or $> 2000$ rejected | PASS |
| **Non-Finite Floats** | `NaN`, `+inf`, `-inf` rejected | PASS |
| **Cost Impact Sign** | Negative values rejected for non-dropout, accepted for dropout | PASS |
| **Budget Schema Violations** | Missing/extra categories and totals $\ne 100\%$ rejected | PASS |
| **Vendor Schema Violations** | Duplicate types (case-insensitive) & empty questions rejected | PASS |
| **Generator Safety** | Deterministic output, skip-existing rule, crisis protection verified | PASS |
| **API Endpoints & Metadata** | `/health` 200 OK, `/api/v1/data-status` 200 with safe nested metadata, 503 error isolation | PASS |

---

## 4. Next Milestone Objectives
- **Milestone 3 (Core Event Planner & Deterministic Engine):**
  - Implement `app/services/planner.py` to calculate budget splits in INR based on total event budget.
  - Implement deterministic rebalancing algorithms when unexpected vendor costs or guest changes occur.
  - Generate planning milestone timelines and day-of-event schedules.
