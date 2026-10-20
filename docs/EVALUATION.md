# PlanProof AI — Dataset Audit & Evaluation Framework

## 1. Dataset Audit Findings

An exhaustive audit of the existing workspace was conducted prior to code implementation.

### A. Discovery and File Mapping
- **Discovered CSV:** Located at `dataset.csv` in the project root.
- **Expected CSV Name:** `data/crisis_scenarios.csv`.
- **Preservation Action:** `dataset.csv` was preserved intact in the project root. A verified byte-for-byte copy was placed at `data/crisis_scenarios.csv`.
- **SHA-256 Checksum:** `855603b2e04839e0fbff8a7343dcbc869cae5bf2cbf8d3948beda05e0921df03`.

### B. Schema Verification
The actual columns of the discovered dataset were verified against the target schema:

| Column | Actual Type | Missing Values | Expected Schema Match |
| :--- | :--- | :---: | :---: |
| `id` | `str` (e.g. `CR0000001`) | 0 | Yes |
| `event_type` | `str` (`wedding`, `birthday`, `community_event`) | 0 | Yes |
| `city_tier` | `str` (`metro`, `tier2`, `tier3`) | 0 | Yes |
| `guest_count` | `int` (Range: 20 – 600) | 0 | Yes |
| `phase` | `str` (`planning`, `day_before`, `event_day`) | 0 | Yes |
| `crisis_type` | `str` (12 unique crisis types) | 0 | Yes |
| `severity` | `int` (1, 2, 3) | 0 | Yes |
| `description` | `str` (Non-empty) | 0 | Yes |
| `recommended_fix` | `str` (Non-empty) | 0 | Yes |
| `cost_impact_pct_of_budget` | `float` (Range: -6.5% – 22.7%) | 0 | Yes |
| `message_target` | `str` (`family`, `vendor`, `guests`) | 0 | Yes |
| `synthetic` | `bool` (`True`) | 0 | Yes |

- **Total Records:** 5,000 valid data rows (5,001 lines with header).
- **Duplicate IDs:** 0 duplicate identifiers.
- **Missing Values:** 0 across all columns.

### C. Ancillary Datasets Audit
- `budget_splits.json`: Validated against 8 required budget categories (`venue`, `catering`, `decor`, `photo_video`, `attire_beauty`, `entertainment`, `logistics`, `buffer`). All 9 combinations of `(event_type, city_tier)` total **exactly 100%**.
- `vendor_checklists.json`: Validated across 8 core vendor categories with lead times, advance payment percentages, and interview questions.

---

## 2. Synthetic Data Transparency

All numbers in `crisis_scenarios.csv`, `budget_splits.json`, and `vendor_checklists.json` are **explicitly labeled as synthetic assumptions** generated for testing and demonstration. They do not constitute surveyed market data or contractual pricing.

---

## 3. Automated Test Suite Metrics

| Test Area | Scenarios Covered | Status |
| :--- | :--- | :---: |
| **Full Dataset Ingestion** | Real 5,000 rows loaded and validated against Pydantic schema | PASS |
| **Budget Split Integrity** | Every allocation validated to equal 100% | PASS |
| **Missing Column Detection** | Missing required columns produce `DatasetMalformedError` | PASS |
| **Empty File Detection** | Empty files or header-only files produce `DatasetEmptyError` | PASS |
| **Severity Bound Enforcement** | Values $< 1$ or $> 3$ produce `DatasetValidationError` | PASS |
| **Guest Count Bound Enforcement** | Non-positive guest counts produce `DatasetValidationError` | PASS |
| **API Health Liveness** | `GET /health` returns 200 OK | PASS |
| **API Metadata Privacy** | `GET /api/v1/data-status` returns safe summary without full table | PASS |
| **Error Isolation** | Corrupted or missing files return 503 JSON without tracebacks | PASS |

---

## 4. Evaluation Criteria for Next Milestones
- **Deterministic Budget Rebalancing:** Ensure zero negative allocations and exact budget conservation when cost shocks are applied.
- **Offline / Sample Mode:** Ensure the crisis recovery assistant provides functional recovery workflows even when the Gemini API is unreachable.
- **WhatsApp Message Quality:** Verify that generated crisis messages include specific contact targets, timestamp references, and clear action items.
