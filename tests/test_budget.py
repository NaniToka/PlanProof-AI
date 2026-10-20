"""Unit tests for the PlanProof AI deterministic budget engine.

Validates exact integer INR calculations, largest-remainder rounding,
canonical category ordering, prioritized rebalancing, and domain constraints.
"""

import pytest

from app.schemas import (
    CANONICAL_BUDGET_CATEGORIES,
    BudgetCalculationResponse,
    BudgetRebalanceResponse,
    CityTier,
    EventType,
)
from app.services.budget import (
    TIER_1_DISCRETIONARY,
    TIER_2_FLEXIBLE,
    TIER_3_PROTECTED,
    BudgetConstraintError,
    BudgetValidationError,
    calculate_initial_budget,
    largest_remainder_allocation,
    rebalance_budget,
    validate_budget_categories,
)

# ==============================================================================
# 1. Largest-Remainder (Hamilton-Hare) Allocation Tests
# ==============================================================================


def test_largest_remainder_exact_integer_sum() -> None:
    """Verify that allocations sum exactly to the requested total down to 1 rupee."""
    total = 10001
    weights = {
        "venue": 26,
        "catering": 30,
        "decor": 11,
        "photo_video": 9,
        "attire_beauty": 10,
        "entertainment": 5,
        "logistics": 3,
        "buffer": 6,
    }
    allocations = largest_remainder_allocation(total, weights, CANONICAL_BUDGET_CATEGORIES)
    assert sum(allocations.values()) == total
    assert all(isinstance(v, int) for v in allocations.values())
    assert all(v >= 0 for v in allocations.values())
    # Catering has largest remainder (30), so it should receive the extra 1 rupee (3000 + 1 = 3001)
    assert allocations["catering"] == 3001
    assert allocations["venue"] == 2600


def test_largest_remainder_deterministic_tie_breaking() -> None:
    """Verify that ties in remainder are broken consistently using canonical category order."""
    # Total of 3 with equal weights of 1 across 4 categories:
    # 3 * 1 // 4 = 0 for all, remainder 3 for all 4 categories.
    # The first 3 categories in canonical order must receive 1 rupee each; the 4th gets 0.
    total = 3
    order = ("venue", "catering", "decor", "buffer")
    weights = {"venue": 1, "catering": 1, "decor": 1, "buffer": 1}

    allocations = largest_remainder_allocation(total, weights, category_order=order)
    assert sum(allocations.values()) == 3
    assert allocations["venue"] == 1
    assert allocations["catering"] == 1
    assert allocations["decor"] == 1
    assert allocations["buffer"] == 0


def test_largest_remainder_rejects_negative_or_zero_weights() -> None:
    """Verify largest-remainder rejects negative totals or zero weight sums."""
    with pytest.raises(BudgetConstraintError, match="cannot be negative"):
        largest_remainder_allocation(-100, {"venue": 50, "catering": 50})

    with pytest.raises(BudgetConstraintError, match="must be positive"):
        largest_remainder_allocation(1000, {"venue": 0, "catering": 0})


# ==============================================================================
# 2. Initial Budget Calculation Tests
# ==============================================================================


@pytest.mark.parametrize("event_type", list(EventType))
@pytest.mark.parametrize("city_tier", list(CityTier))
def test_initial_budget_all_nine_combinations(event_type: EventType, city_tier: CityTier) -> None:
    """Verify all 9 event_type and city_tier combinations calculate correctly."""
    budget = 1_500_000
    res = calculate_initial_budget(
        event_type=event_type,
        city_tier=city_tier,
        total_budget_inr=budget,
    )
    assert isinstance(res, BudgetCalculationResponse)
    assert res.event_type == event_type
    assert res.city_tier == city_tier
    assert res.total_budget_inr == budget

    # Verify all 8 categories are present and sum exactly to budget
    alloc = res.allocations.model_dump()
    for cat in CANONICAL_BUDGET_CATEGORIES:
        assert cat in alloc
        assert isinstance(alloc[cat], int)
        assert alloc[cat] >= 0

    assert sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES) == budget
    assert alloc["total_budget_inr"] == budget


def test_initial_budget_min_and_max_bounds() -> None:
    """Verify calculations at boundary budgets ₹10,000 and ₹50,000,000."""
    res_min = calculate_initial_budget("wedding", "metro", 10_000)
    assert sum(getattr(res_min.allocations, c) for c in CANONICAL_BUDGET_CATEGORIES) == 10_000

    res_max = calculate_initial_budget("wedding", "metro", 50_000_000)
    assert sum(getattr(res_max.allocations, c) for c in CANONICAL_BUDGET_CATEGORIES) == 50_000_000


@pytest.mark.parametrize("odd_budget", [10_001, 15_555, 99_999, 123_456, 1_999_999, 7_777_777])
def test_initial_budget_odd_values_exact_sum(odd_budget: int) -> None:
    """Verify that fractional remainder budgets always sum to the exact rupee."""
    res = calculate_initial_budget("birthday", "tier2", odd_budget)
    alloc = res.allocations.model_dump()
    category_sum = sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES)
    assert category_sum == odd_budget
    assert alloc["total_budget_inr"] == odd_budget


def test_initial_budget_input_validation() -> None:
    """Verify rejection of invalid event types, city tiers, and budget bounds."""
    with pytest.raises(BudgetValidationError, match="Unsupported event type"):
        calculate_initial_budget("invalid_event", "metro", 100_000)

    with pytest.raises(BudgetValidationError, match="Unsupported city tier"):
        calculate_initial_budget("wedding", "tier4", 100_000)

    with pytest.raises(BudgetConstraintError, match="must be between"):
        calculate_initial_budget("wedding", "metro", 9_999)  # Below 10,000

    with pytest.raises(BudgetConstraintError, match="must be between"):
        calculate_initial_budget("wedding", "metro", 50_000_001)  # Above 50,000,000

    with pytest.raises(BudgetValidationError, match="must be an integer, not a boolean"):
        calculate_initial_budget("wedding", "metro", True)  # type: ignore[arg-type]

    with pytest.raises(BudgetValidationError, match="must be an integer amount, not a decimal"):
        calculate_initial_budget("wedding", "metro", 150000.50)  # type: ignore[arg-type]


# ==============================================================================
# 3. Category Validation Tests
# ==============================================================================


def test_validate_budget_categories_success() -> None:
    """Verify validation passes for exact 8 canonical categories."""
    valid_data = {
        "venue": 260_000,
        "catering": 300_000,
        "decor": 110_000,
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
    }
    validated = validate_budget_categories(valid_data)
    assert len(validated) == 8
    assert validated["venue"] == 260_000


def test_validate_budget_categories_missing_category() -> None:
    """Verify error when a canonical category is missing."""
    data = {
        "venue": 260_000,
        "catering": 300_000,
        # missing decor
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
    }
    with pytest.raises(BudgetValidationError, match="missing required categories"):
        validate_budget_categories(data)


def test_validate_budget_categories_extra_category() -> None:
    """Verify error when an unrecognized category is present."""
    data = {c: 10_000 for c in CANONICAL_BUDGET_CATEGORIES}
    data["extra_vip_gifts"] = 5_000
    with pytest.raises(BudgetValidationError, match="unrecognized categories"):
        validate_budget_categories(data)


def test_validate_budget_categories_negative_or_invalid_type() -> None:
    """Verify rejection of negative amounts, booleans, and floats."""
    data = {c: 10_000 for c in CANONICAL_BUDGET_CATEGORIES}
    data["decor"] = -500
    with pytest.raises(BudgetValidationError, match="cannot be negative"):
        validate_budget_categories(data)

    data["decor"] = True
    with pytest.raises(BudgetValidationError, match="not a boolean"):
        validate_budget_categories(data)

    data["decor"] = 1000.75
    with pytest.raises(BudgetValidationError, match="not a decimal"):
        validate_budget_categories(data)


# ==============================================================================
# 4. Budget Rebalancing Tests
# ==============================================================================


@pytest.fixture
def baseline_wedding_metro_1m() -> dict[str, int]:
    """Sample baseline allocation for ₹1,000,000 wedding in metro."""
    return {
        "venue": 260_000,
        "catering": 300_000,
        "decor": 110_000,
        "photo_video": 90_000,
        "attire_beauty": 100_000,
        "entertainment": 50_000,
        "logistics": 30_000,
        "buffer": 60_000,
    }


def test_rebalance_unchanged_budget(baseline_wedding_metro_1m: dict[str, int]) -> None:
    """Verify rebalance when total is identical returns 0 differences and preserved status."""
    res = rebalance_budget(baseline_wedding_metro_1m, 1_000_000)
    assert res.previous_total_inr == 1_000_000
    assert res.new_total_inr == 1_000_000
    assert all(d == 0 for d in res.differences.values())
    assert res.protected_preserved is True
    assert res.categories_reduced_first == []


def test_rebalance_budget_increase(baseline_wedding_metro_1m: dict[str, int]) -> None:
    """Verify budget increase scales categories proportionally, protecting catering and buffer."""
    new_total = 1_250_000
    res = rebalance_budget(baseline_wedding_metro_1m, new_total)

    assert isinstance(res, BudgetRebalanceResponse)
    assert res.previous_total_inr == 1_000_000
    assert res.new_total_inr == new_total
    assert sum(res.differences.values()) == 250_000
    assert all(d >= 0 for d in res.differences.values())

    # Catering and buffer must grow and remain protected
    alloc = res.allocations.model_dump()
    assert alloc["catering"] > baseline_wedding_metro_1m["catering"]
    assert alloc["buffer"] > baseline_wedding_metro_1m["buffer"]
    assert res.protected_preserved is True
    assert sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES) == new_total


def test_rebalance_minor_decrease_tier_1_only(baseline_wedding_metro_1m: dict[str, int]) -> None:
    """Verify minor decrease trims entertainment and decor first, preserving catering and buffer."""
    # Tier 1 total: decor (110,000) + entertainment (50,000) = 160,000
    # Reduction: ₹100,000 (< 160,000)
    new_total = 900_000
    res = rebalance_budget(baseline_wedding_metro_1m, new_total)

    alloc = res.allocations.model_dump()
    assert sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES) == new_total
    assert res.protected_preserved is True

    # Catering, buffer, and all Tier 2 categories must remain 100% UNCHANGED
    for c in TIER_3_PROTECTED:
        assert alloc[c] == baseline_wedding_metro_1m[c]
        assert res.differences[c] == 0

    for c in TIER_2_FLEXIBLE:
        assert alloc[c] == baseline_wedding_metro_1m[c]
        assert res.differences[c] == 0

    # Reductions must come exclusively from Tier 1
    assert alloc["decor"] < baseline_wedding_metro_1m["decor"]
    assert alloc["entertainment"] < baseline_wedding_metro_1m["entertainment"]
    assert res.differences["decor"] + res.differences["entertainment"] == -100_000
    assert set(res.categories_reduced_first) == {"decor", "entertainment"}


def test_rebalance_moderate_decrease_tier_2_cuts(
    baseline_wedding_metro_1m: dict[str, int],
) -> None:
    """Verify moderate decrease exhausts Tier 1, cuts Tier 2, and preserves catering/buffer."""
    # Tier 1: 160,000. Tier 2: 480,000.
    # Reduction: ₹400,000 (Tier 1 exhausted by 160k, remaining 240k from Tier 2).
    new_total = 600_000
    res = rebalance_budget(baseline_wedding_metro_1m, new_total)

    alloc = res.allocations.model_dump()
    assert sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES) == new_total
    assert res.protected_preserved is True

    # Tier 1 must be zeroed out
    assert alloc["entertainment"] == 0
    assert alloc["decor"] == 0

    # Tier 2 categories must be reduced
    for c in TIER_2_FLEXIBLE:
        assert alloc[c] < baseline_wedding_metro_1m[c]

    # Catering and buffer must still be 100% PRESERVED
    assert alloc["catering"] == baseline_wedding_metro_1m["catering"]
    assert alloc["buffer"] == baseline_wedding_metro_1m["buffer"]
    assert res.differences["catering"] == 0
    assert res.differences["buffer"] == 0


def test_rebalance_severe_decrease_into_tier_3(baseline_wedding_metro_1m: dict[str, int]) -> None:
    """Verify deep decrease cuts into Tier 3 and flags protected_preserved=False."""
    # Tier 1 (160k) + Tier 2 (480k) = 640k total non-protected.
    # Total catering + buffer = 360k.
    # Request new budget of ₹200,000 (reduction of ₹800,000).
    new_total = 200_000
    res = rebalance_budget(baseline_wedding_metro_1m, new_total, strict_protect=False)

    alloc = res.allocations.model_dump()
    assert sum(alloc[c] for c in CANONICAL_BUDGET_CATEGORIES) == new_total
    assert res.protected_preserved is False

    # Tier 1 and Tier 2 must be 0
    for c in TIER_1_DISCRETIONARY:
        assert alloc[c] == 0
    for c in TIER_2_FLEXIBLE:
        assert alloc[c] == 0

    # Catering and buffer absorb the remaining ₹200,000
    assert alloc["catering"] > 0
    assert alloc["buffer"] > 0
    assert alloc["catering"] + alloc["buffer"] == new_total
    assert "mathematically impossible" in res.explanation


def test_rebalance_severe_decrease_strict_protect_raises(
    baseline_wedding_metro_1m: dict[str, int],
) -> None:
    """Verify strict_protect=True raises error when cuts affect protected categories."""
    new_total = 200_000  # Requires cutting into catering/buffer
    with pytest.raises(BudgetConstraintError, match="Protection constraint violated"):
        rebalance_budget(baseline_wedding_metro_1m, new_total, strict_protect=True)


def test_rebalance_extreme_decrease_below_min_raises(
    baseline_wedding_metro_1m: dict[str, int],
) -> None:
    """Verify reduction below min_event_budget_inr (₹10,000) raises BudgetConstraintError."""
    with pytest.raises(BudgetConstraintError, match="new_total_budget_inr must be between"):
        rebalance_budget(baseline_wedding_metro_1m, 5_000)

    with pytest.raises(BudgetConstraintError, match="new_total_budget_inr must be between"):
        rebalance_budget(baseline_wedding_metro_1m, 0)


def test_rebalance_reproducibility_and_determinism(
    baseline_wedding_metro_1m: dict[str, int],
) -> None:
    """Verify that repeating the rebalance operation 50 times yields strictly identical results."""
    res_first = rebalance_budget(baseline_wedding_metro_1m, 750_000)
    for _ in range(50):
        res_subsequent = rebalance_budget(baseline_wedding_metro_1m, 750_000)
        assert res_subsequent.model_dump() == res_first.model_dump()
