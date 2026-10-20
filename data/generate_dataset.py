"""Synthetic supporting dataset generator and validator for PlanProof AI.

Generates only supporting datasets (budget_splits.json, vendor_checklists.json).
PROTECTS the crisis scenarios dataset: never regenerates, overwrites, or deletes crisis_scenarios.csv.

All figures are SYNTHETIC ASSUMPTIONS for development and testing, NOT measured market data.
"""

import argparse
import json
from pathlib import Path
import sys

from app.data_loader import load_budget_splits, load_vendor_checklists

DEFAULT_DATA_DIR = Path(__file__).resolve().parent

# Base category percentage allocations per event type (sum must be exactly 100)
BASE_BUDGET_SPLITS = {
    "wedding": {
        "venue": 22.0,
        "catering": 32.0,
        "decor": 12.0,
        "photo_video": 9.0,
        "attire_beauty": 10.0,
        "entertainment": 5.0,
        "logistics": 4.0,
        "buffer": 6.0,
    },
    "birthday": {
        "venue": 18.0,
        "catering": 35.0,
        "decor": 15.0,
        "photo_video": 6.0,
        "attire_beauty": 3.0,
        "entertainment": 13.0,
        "logistics": 4.0,
        "buffer": 6.0,
    },
    "community_event": {
        "venue": 20.0,
        "catering": 28.0,
        "decor": 8.0,
        "photo_video": 4.0,
        "attire_beauty": 0.0,
        "entertainment": 15.0,
        "logistics": 15.0,
        "buffer": 10.0,
    },
}

# Percentage point tier shifts (must net to zero per tier)
TIER_SHIFTS = {
    "metro": {"venue": 4.0, "catering": -2.0, "decor": -1.0, "logistics": -1.0},
    "tier2": {},
    "tier3": {"venue": -4.0, "catering": 2.0, "decor": 1.0, "logistics": 1.0},
}

VENDOR_CATALOG = [
    ("venue", 26, 30.0, [
        "Capacity and indoor backup available?",
        "Generator power backup included?",
        "Cancellation and refund timeline terms?",
    ]),
    ("caterer", 12, 25.0, [
        "Menu tasting session provided?",
        "Deadline for final headcount adjustment?",
        "Backup staff and hygiene standards guaranteed?",
    ]),
    ("decorator", 8, 40.0, [
        "Setup duration needed prior to event start?",
        "Post-event teardown included in quote?",
        "Contingency plan for adverse weather conditions?",
    ]),
    ("photographer", 16, 30.0, [
        "Designated backup photographer assigned?",
        "Album and raw file delivery timeline?",
        "Overtime hourly rates beyond contracted hours?",
    ]),
    ("music_dj", 8, 30.0, [
        "Provides own amplified sound system and mixer?",
        "Backup equipment and microphones available on-site?",
        "Client control over curated playlist and do-not-play list?",
    ]),
    ("makeup_attire", 10, 25.0, [
        "Pre-event trial session included?",
        "Are travel and on-location charges extra?",
        "On-day touch-up coverage provided?",
    ]),
    ("transport", 4, 20.0, [
        "Number and capacity of vehicles allocated?",
        "Driver contacts and dispatch manager assigned?",
        "Fuel surcharge and waiting hour charges defined?",
    ]),
    ("invitations", 6, 50.0, [
        "Digital PDF/video or physical offset print?",
        "Digital proof approval workflow?",
        "Guaranteed dispatch date before event?",
    ]),
]


def generate_budget_splits_data() -> dict:
    """Generate deterministic budget allocation assumptions for all event types and tiers."""
    splits = {}
    for event_type, base in BASE_BUDGET_SPLITS.items():
        splits[event_type] = {}
        for tier, shifts in TIER_SHIFTS.items():
            tier_split = {}
            for cat, pct in base.items():
                tier_split[cat] = round(pct + shifts.get(cat, 0.0), 1)
            total = sum(tier_split.values())
            assert abs(total - 100.0) < 1e-4, f"Split for {event_type}.{tier} must sum to 100"
            splits[event_type][tier] = tier_split

    return {
        "_note": "Synthetic assumptions, percent of total budget",
        "splits": splits,
    }


def generate_vendor_checklists_data() -> dict:
    """Generate deterministic vendor checklist and booking timeline assumptions."""
    vendors = [
        {
            "type": v_type,
            "lead_time_weeks": lead_time,
            "typical_advance_pct": advance,
            "ask_before_booking": questions,
        }
        for v_type, lead_time, advance, questions in VENDOR_CATALOG
    ]
    return {
        "_note": "Lead times and advance percent are synthetic assumptions",
        "vendors": vendors,
    }


def run_generator(data_dir: Path, overwrite: bool = False, validate_only: bool = False) -> int:
    """Run generation and validation workflow with explicit file safety.

    Returns:
        0 on success, 1 on validation or write failure.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    budget_file = data_dir / "budget_splits.json"
    vendor_file = data_dir / "vendor_checklists.json"
    crisis_file = data_dir / "crisis_scenarios.csv"

    # Always verify crisis scenarios CSV is protected and untouched
    if crisis_file.exists():
        print(f"[PROTECTED] Crisis scenarios file preserved at {crisis_file}")
    else:
        print(f"[NOTICE] Crisis scenarios file not found at {crisis_file}")

    if validate_only:
        print("[MODE] Validating existing supporting datasets without modification...")
    else:
        # 1. Budget splits
        if budget_file.exists() and not overwrite:
            print(f"[SKIPPED] {budget_file.name} already exists (use --overwrite to replace)")
        else:
            budget_data = generate_budget_splits_data()
            budget_file.write_text(json.dumps(budget_data, indent=2), encoding="utf-8")
            print(f"[CREATED] {budget_file.name} (9 combinations, 100% split totals)")

        # 2. Vendor checklists
        if vendor_file.exists() and not overwrite:
            print(f"[SKIPPED] {vendor_file.name} already exists (use --overwrite to replace)")
        else:
            vendor_data = generate_vendor_checklists_data()
            vendor_file.write_text(json.dumps(vendor_data, indent=2), encoding="utf-8")
            print(f"[CREATED] {vendor_file.name} ({len(VENDOR_CATALOG)} vendor categories)")

    # 3. Validate generated or existing files using strict data loader
    print("[VALIDATING] Verifying dataset integrity against Pydantic v2 schemas...")
    try:
        b_dataset = load_budget_splits(budget_file)
        print(f"[VALID] {budget_file.name} verified: {len(b_dataset.splits)} event types.")

        v_dataset = load_vendor_checklists(vendor_file)
        print(f"[VALID] {vendor_file.name} verified: {len(v_dataset.vendors)} vendor checklists.")
        print("[SUCCESS] All supporting datasets are valid and ready.")
        return 0
    except Exception as err:
        print(f"[ERROR] Validation failed: {err}", file=sys.stderr)
        return 1


def main() -> None:
    """Command-line interface for supporting dataset generation."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic supporting datasets for PlanProof AI."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory to write datasets into (default: data/)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing JSON datasets if they already exist",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing JSON datasets without writing changes",
    )
    args = parser.parse_args()
    code = run_generator(args.output_dir, overwrite=args.overwrite, validate_only=args.validate_only)
    sys.exit(code)


if __name__ == "__main__":
    main()
