"""Generate PlanProof seed datasets.

All numbers are SYNTHETIC ASSUMPTIONS for development and testing, not
measured market data. Replace with sourced figures before claiming accuracy.

Usage:
    python generate_dataset.py                 # 5,000 crisis rows
    python generate_dataset.py --rows 100000   # scale as needed
"""
import argparse
import csv
import json
import random
from pathlib import Path

SEED = 42
OUT = Path(__file__).parent / "data"

EVENT_TYPES = ["wedding", "birthday", "community_event"]
CITY_TIERS = ["metro", "tier2", "tier3"]
PHASES = {"planning": 0.5, "day_before": 1.0, "event_day": 1.5}
GUEST_BUCKETS = {"small": (20, 60), "medium": (61, 200), "large": (201, 600)}
TIER_COST_MULT = {"metro": 1.2, "tier2": 1.0, "tier3": 0.85}

# category -> base percent of total budget, per event type (assumptions)
BASE_SPLIT = {
    "wedding": {"venue": 22, "catering": 32, "decor": 12, "photo_video": 9,
                "attire_beauty": 10, "entertainment": 5, "logistics": 4, "buffer": 6},
    "birthday": {"venue": 18, "catering": 35, "decor": 15, "photo_video": 6,
                 "attire_beauty": 3, "entertainment": 13, "logistics": 4, "buffer": 6},
    "community_event": {"venue": 20, "catering": 28, "decor": 8, "photo_video": 4,
                        "attire_beauty": 0, "entertainment": 15, "logistics": 15, "buffer": 10},
}
# percentage-point shifts by city tier (must net to zero per tier)
TIER_SHIFT = {
    "metro": {"venue": 4, "catering": -2, "decor": -1, "logistics": -1},
    "tier2": {},
    "tier3": {"venue": -4, "catering": 2, "decor": 1, "logistics": 1},
}

# key: (description, fix, base_cost_pct_of_budget, who_to_message)
CRISES = {
    "rain": ("Outdoor venue affected by rain", "Switch to the pre-booked indoor hall and re-layout seating", 3.0, "guests"),
    "caterer_late": ("Caterer running about 1 hour late", "Reorder program so cake or music fills the gap; serve snacks first", 0.5, "vendor"),
    "caterer_cancel": ("Caterer cancels at short notice", "Call backup caterer; fall back to a reduced menu", 6.0, "vendor"),
    "guest_surge": ("About 30 extra guests confirmed", "Use buffer menu and add seating; trim a low-priority item", 4.0, "vendor"),
    "guest_dropout": ("Many guests cancel", "Renegotiate headcount with caterer; shrink seating plan", -2.0, "vendor"),
    "venue_double_booked": ("Venue reports a double booking", "Move to backup venue or shift the time slot", 7.0, "family"),
    "power_cut": ("Power cut during the event", "Start generator; shift to acoustic or daylight segments", 1.5, "vendor"),
    "decorator_delay": ("Decorator behind schedule", "Prioritise stage and entrance; defer secondary decor", 1.0, "vendor"),
    "photographer_noshow": ("Photographer does not arrive", "Call backup; assign a friend for key moments; book a re-shoot", 2.5, "vendor"),
    "budget_overrun": ("Spending is over budget", "Rebalance: cut entertainment and decor first, protect catering", 0.0, "family"),
    "key_guest_cancel": ("Chief guest or an elder cannot attend", "Reorder the program; arrange a video call slot", 0.0, "family"),
    "sound_failure": ("Sound system fails", "Swap in backup speakers; keep the MC on a portable mic", 1.0, "vendor"),
}


def budget_splits():
    out = {}
    for event, base in BASE_SPLIT.items():
        assert sum(base.values()) == 100, event
        out[event] = {}
        for tier in CITY_TIERS:
            split = {k: base[k] + TIER_SHIFT[tier].get(k, 0) for k in base}
            assert sum(split.values()) == 100, (event, tier)
            out[event][tier] = split
    return {"_note": "Synthetic assumptions, percent of total budget", "splits": out}


def vendor_checklists():
    v = [
        ("venue", 26, 30, ["Capacity and indoor backup?", "Power backup?", "Cancellation terms?"]),
        ("caterer", 12, 25, ["Menu tasting?", "Headcount change deadline?", "Backup staff?"]),
        ("decorator", 8, 40, ["Setup time needed?", "Teardown included?", "Weather plan?"]),
        ("photographer", 16, 30, ["Backup photographer?", "Delivery timeline?", "Overtime rate?"]),
        ("music_dj", 8, 30, ["Own sound system?", "Backup equipment?", "Playlist control?"]),
        ("makeup_attire", 10, 25, ["Trial session?", "Travel charges?", "Touch-up on day?"]),
        ("transport", 4, 20, ["Number of vehicles?", "Driver contact?", "Fuel and waiting charges?"]),
        ("invitations", 6, 50, ["Print or digital?", "Proof approval?", "Delivery date?"]),
    ]
    return {"_note": "Lead times and advance percent are synthetic assumptions", "vendors": [
        {"type": t, "lead_time_weeks": w, "typical_advance_pct": a, "ask_before_booking": q}
        for t, w, a, q in v]}


def crisis_rows(n, rng):
    keys = list(CRISES)
    combos = [(e, c, s, p, g, t) for e in EVENT_TYPES for c in keys for s in (1, 2, 3)
              for p in PHASES for g in GUEST_BUCKETS for t in CITY_TIERS]
    rng.shuffle(combos)
    for i in range(n):
        e, c, sev, phase, gb, tier = combos[i % len(combos)]
        desc, fix, base, who = CRISES[c]
        lo, hi = GUEST_BUCKETS[gb]
        guests = rng.randint(lo, hi)
        cost = round(base * (0.6 + 0.4 * sev) * PHASES[phase] * TIER_COST_MULT[tier], 1)
        yield {
            "id": f"CR{i + 1:07d}", "event_type": e, "city_tier": tier, "guest_count": guests,
            "phase": phase, "crisis_type": c, "severity": sev,
            "description": f"{desc} ({e.replace('_', ' ')})", "recommended_fix": fix,
            "cost_impact_pct_of_budget": cost, "message_target": who, "synthetic": True,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000)
    n = ap.parse_args().rows
    OUT.mkdir(exist_ok=True)
    (OUT / "budget_splits.json").write_text(json.dumps(budget_splits(), indent=2))
    (OUT / "vendor_checklists.json").write_text(json.dumps(vendor_checklists(), indent=2))
    rng = random.Random(SEED)
    rows = crisis_rows(n, rng)
    first = next(rows)
    with open(OUT / "crisis_scenarios.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(first))
        w.writeheader()
        w.writerow(first)
        w.writerows(rows)
    print(f"wrote {n} crisis rows to {OUT}")


if __name__ == "__main__":
    main()
