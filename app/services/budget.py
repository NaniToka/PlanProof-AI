"""Deterministic budget engine and INR rebalancing service for PlanProof AI.

Critical Invariant:
All budget calculations are strictly computed in Python using deterministic integer
arithmetic. Gemini or other LLMs must NEVER decide, calculate, or modify numerical
budget allocations.
"""

import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.data_loader import load_budget_splits
from app.schemas import (
    CANONICAL_BUDGET_CATEGORIES,
    BudgetCalculationResponse,
    BudgetRebalanceResponse,
    BudgetSplitsDataset,
    CityTier,
    EventBudgetBreakdown,
    EventType,
)

logger = logging.getLogger(__name__)

# Three-tier priority policy for budget reductions:
# Tier 1 (Cut First - Discretionary): Entertainment and decor
TIER_1_DISCRETIONARY: tuple[str, ...] = ("entertainment", "decor")

# Tier 2 (Secondary Cuts - Flexible Operations): Core event logistics & aesthetics
TIER_2_FLEXIBLE: tuple[str, ...] = ("venue", "photo_video", "attire_beauty", "logistics")

# Tier 3 (Protected - Essential Guest Experience & Emergency):
TIER_3_PROTECTED: tuple[str, ...] = ("catering", "buffer")


class BudgetEngineError(Exception):
    """Base exception for all budget engine calculation and validation errors."""


class BudgetValidationError(BudgetEngineError):
    """Raised when category allocations, keys, or types fail validation."""


class BudgetConstraintError(BudgetEngineError):
    """Raised when requested budget or reduction violates domain constraints."""


def validate_budget_categories(allocations: Mapping[str, Any]) -> dict[str, int]:
    """Validate that allocations contain exactly 8 canonical categories with non-negative integers.

    Args:
        allocations: Category rupee values mapping. May include optional 'total_budget_inr'.

    Returns:
        Validated dictionary of category names to integer INR amounts.

    Raises:
        BudgetValidationError: If categories are missing, extra, negative, or not integers.
    """
    provided_keys = set(allocations.keys())
    provided_categories = {k for k in provided_keys if k != "total_budget_inr"}
    required_keys = set(CANONICAL_BUDGET_CATEGORIES)

    missing = required_keys - provided_categories
    if missing:
        sorted_missing = [c for c in CANONICAL_BUDGET_CATEGORIES if c in missing]
        raise BudgetValidationError(
            f"Budget allocations missing required categories: {sorted_missing}"
        )

    extra = provided_categories - required_keys
    if extra:
        raise BudgetValidationError(
            f"Budget allocations contain unrecognized categories: {sorted(extra)}"
        )

    validated: dict[str, int] = {}
    for cat in CANONICAL_BUDGET_CATEGORIES:
        val = allocations[cat]
        if isinstance(val, bool):
            raise BudgetValidationError(
                f"Allocation for '{cat}' must be an integer amount, not a boolean"
            )
        if isinstance(val, float):
            raise BudgetValidationError(
                f"Allocation for '{cat}' must be an integer amount in INR, not a decimal ({val})"
            )
        try:
            val_int = int(val)
        except (ValueError, TypeError) as err:
            raise BudgetValidationError(
                f"Allocation for '{cat}' must be a valid integer amount in INR"
            ) from err

        if val_int < 0:
            raise BudgetValidationError(
                f"Allocation for '{cat}' cannot be negative (got ₹{val_int:,})"
            )
        validated[cat] = val_int

    return validated


def largest_remainder_allocation(
    total_amount: int,
    weights: Mapping[str, int],
    category_order: tuple[str, ...] | None = None,
) -> dict[str, int]:
    """Distribute an integer total using the Hamilton-Hare largest-remainder method.

    Guarantees:
    - Pure integer arithmetic without floating-point drift.
    - Sum of returned category allocations equals total_amount exactly down to the last rupee.
    - All allocations are non-negative.
    - Deterministic tie-breaking using the predefined category order.

    Args:
        total_amount: Total integer rupees to allocate (>= 0).
        weights: Non-negative integer weights (e.g. percentages or rupee allocations).
        category_order: Priority sequence for deterministic tie-breaking. Defaults to canonical.

    Returns:
        Dict mapping each category in weights to its exact integer allocation.

    Raises:
        BudgetConstraintError: If total_amount < 0 or sum of weights <= 0.
    """
    if total_amount < 0:
        raise BudgetConstraintError(
            f"Total allocation amount cannot be negative: ₹{total_amount:,}"
        )

    total_int = int(total_amount)
    int_weights: dict[str, int] = {
        cat: int(round(w)) if isinstance(w, float) else int(w) for cat, w in weights.items()
    }

    total_weight = sum(int_weights.values())
    if total_weight <= 0:
        raise BudgetConstraintError(
            f"Sum of allocation weights must be positive, got {total_weight}"
        )

    order = category_order or CANONICAL_BUDGET_CATEGORIES
    order_index = {cat: idx for idx, cat in enumerate(order)}

    # Step 1 & 2: Integer floor allocation and exact integer remainder
    allocations: dict[str, int] = {}
    remainders: list[tuple[int, int, str]] = []  # (-remainder, order_idx, category)

    floored_sum = 0
    for cat, weight in int_weights.items():
        if weight < 0:
            raise BudgetConstraintError(f"Weight for '{cat}' cannot be negative: {weight}")
        quotient, rem = divmod(total_int * weight, total_weight)
        allocations[cat] = quotient
        floored_sum += quotient
        idx = order_index.get(cat, 999)
        remainders.append((-rem, idx, cat))

    # Step 3: Compute remaining rupees
    leftover = total_int - floored_sum

    # Step 4 & 5: Sort by largest remainder, breaking ties by canonical order index
    remainders.sort()
    for i in range(leftover):
        _, _, cat = remainders[i]
        allocations[cat] += 1

    return allocations


def calculate_initial_budget(
    event_type: EventType | str,
    city_tier: CityTier | str,
    total_budget_inr: int,
    splits_dataset: BudgetSplitsDataset | None = None,
    dataset_path: Path | str | None = None,
) -> BudgetCalculationResponse:
    """Calculate deterministic initial budget allocation for an event type and city tier.

    Args:
        event_type: Event type (wedding, birthday, community_event).
        city_tier: City tier (metro, tier2, tier3).
        total_budget_inr: Total budget in INR (strict integer, ₹10,000 to ₹50,000,000).
        splits_dataset: Optional preloaded BudgetSplitsDataset instance.
        dataset_path: Optional file path to budget_splits.json if loading on-demand.

    Returns:
        BudgetCalculationResponse with exact integer allocations, percentages, and metadata.

    Raises:
        BudgetValidationError: If event_type or city_tier is invalid.
        BudgetConstraintError: If total_budget_inr is out of bounds or percentages invalid.
    """
    settings = get_settings()

    # Enforce strict integer type and bounds
    if isinstance(total_budget_inr, bool):
        raise BudgetValidationError("total_budget_inr must be an integer, not a boolean")
    if isinstance(total_budget_inr, float):
        raise BudgetValidationError("total_budget_inr must be an integer amount, not a decimal")
    if not isinstance(total_budget_inr, int):
        try:
            total_budget_inr = int(total_budget_inr)
        except (ValueError, TypeError) as err:
            raise BudgetValidationError("total_budget_inr must be an integer amount") from err

    if (
        total_budget_inr < settings.min_event_budget_inr
        or total_budget_inr > settings.max_event_budget_inr
    ):
        raise BudgetConstraintError(
            f"total_budget_inr must be between ₹{settings.min_event_budget_inr:,} and "
            f"₹{settings.max_event_budget_inr:,}, got: ₹{total_budget_inr:,}"
        )

    # Validate and resolve enums
    try:
        resolved_event_type = (
            event_type if isinstance(event_type, EventType) else EventType(event_type)
        )
    except ValueError as err:
        raise BudgetValidationError(f"Unsupported event type: '{event_type}'") from err

    try:
        resolved_city_tier = city_tier if isinstance(city_tier, CityTier) else CityTier(city_tier)
    except ValueError as err:
        raise BudgetValidationError(f"Unsupported city tier: '{city_tier}'") from err

    # Load splits dataset if not provided
    if splits_dataset is None:
        target_path = dataset_path or settings.budget_splits_path
        splits_dataset = load_budget_splits(target_path)

    # Retrieve percentages for event_type and city_tier
    if resolved_event_type not in splits_dataset.splits:
        raise BudgetConstraintError(
            f"No budget split data found for event type: {resolved_event_type.value}"
        )

    tier_splits = splits_dataset.splits[resolved_event_type]
    if resolved_city_tier not in tier_splits:
        msg = (
            f"No budget split data found for tier {resolved_city_tier.value} in "
            f"{resolved_event_type.value}"
        )
        raise BudgetConstraintError(msg)

    categories_split = tier_splits[resolved_city_tier]
    percentage_dict: dict[str, int] = {
        cat: int(round(val)) for cat, val in categories_split.model_dump().items()
    }

    # Verify percentages sum to exactly 100
    total_pct = sum(percentage_dict.values())
    if total_pct != 100:
        raise BudgetConstraintError(
            f"Budget split percentages must sum to 100, got {total_pct} for "
            f"{resolved_event_type.value}/{resolved_city_tier.value}"
        )

    # Allocate integer rupees using Hamilton-Hare method
    allocations_dict = largest_remainder_allocation(
        total_amount=total_budget_inr,
        weights=percentage_dict,
        category_order=CANONICAL_BUDGET_CATEGORIES,
    )

    # Display percentages computed after rupee allocation
    display_percentages: dict[str, float] = {
        cat: round((amt / total_budget_inr) * 100.0, 2) for cat, amt in allocations_dict.items()
    }

    breakdown = EventBudgetBreakdown(
        total_budget_inr=total_budget_inr,
        **allocations_dict,
    )

    return BudgetCalculationResponse(
        event_type=resolved_event_type,
        city_tier=resolved_city_tier,
        total_budget_inr=total_budget_inr,
        allocations=breakdown,
        percentages=display_percentages,
        method="largest_remainder_hamilton",
    )


def rebalance_budget(
    current_allocations: EventBudgetBreakdown | Mapping[str, Any],
    new_total_budget_inr: int,
    strict_protect: bool = False,
    min_budget: int | None = None,
    max_budget: int | None = None,
) -> BudgetRebalanceResponse:
    """Rebalance an existing 8-category budget allocation when the total budget changes.

    Policy:
    1. Budget Increase:
       - Scale all categories proportionally using current allocations as weights.
       - Essential categories (catering and buffer) are 100% preserved and expanded.
    2. Budget Decrease:
       - Tier 1 (Cut First - Discretionary): entertainment and decor are trimmed first.
       - Tier 2 (Secondary Cuts - Flexible Operations): venue, photo_video, attire_beauty,
         and logistics are trimmed next if Tier 1 is exhausted.
       - Tier 3 (Protected - Essential Experience): catering and buffer are protected.
         If reduction exceeds Tier 1 + Tier 2:
         * If strict_protect=True: raises BudgetConstraintError.
         * If strict_protect=False: catering and buffer absorb the remaining cut proportionally,
           and protected_preserved is flagged False with an explicit explanation.

    Args:
        current_allocations: Current valid 8-category allocation.
        new_total_budget_inr: Target new total budget in INR.
        strict_protect: If True, raises error when catering/buffer would be reduced.
        min_budget: Minimum valid budget in INR (defaults to settings).
        max_budget: Maximum valid budget in INR (defaults to settings).

    Returns:
        BudgetRebalanceResponse with updated allocations, differences, and explanations.

    Raises:
        BudgetValidationError: If category set or types are invalid.
        BudgetConstraintError: If budget is outside valid bounds or cannot satisfy constraints.
    """
    settings = get_settings()
    min_b = min_budget if min_budget is not None else settings.min_event_budget_inr
    max_b = max_budget if max_budget is not None else settings.max_event_budget_inr

    # Enforce strict integer type and bounds for new_total_budget_inr
    if isinstance(new_total_budget_inr, bool):
        raise BudgetValidationError("new_total_budget_inr must be an integer, not a boolean")
    if isinstance(new_total_budget_inr, float):
        raise BudgetValidationError("new_total_budget_inr must be an integer amount, not a decimal")
    if not isinstance(new_total_budget_inr, int):
        try:
            new_total_budget_inr = int(new_total_budget_inr)
        except (ValueError, TypeError) as err:
            raise BudgetValidationError("new_total_budget_inr must be an integer amount") from err

    if new_total_budget_inr < min_b or new_total_budget_inr > max_b:
        msg = (
            f"new_total_budget_inr must be between ₹{min_b:,} and ₹{max_b:,}, "
            f"got: ₹{new_total_budget_inr:,}"
        )
        raise BudgetConstraintError(msg)

    # Validate current category allocations
    raw_dict = (
        current_allocations.model_dump()
        if isinstance(current_allocations, EventBudgetBreakdown)
        else dict(current_allocations)
    )
    validated_current = validate_budget_categories(raw_dict)
    previous_total = sum(validated_current.values())

    if previous_total < min_b or previous_total > max_b:
        msg = (
            f"Current budget total of ₹{previous_total:,} is outside valid bounds "
            f"[₹{min_b:,}, ₹{max_b:,}]"
        )
        raise BudgetConstraintError(msg)

    # --------------------------------------------------------------------------
    # Case A: Budget Unchanged
    # --------------------------------------------------------------------------
    if new_total_budget_inr == previous_total:
        display_percentages = {
            cat: round((amt / previous_total) * 100.0, 2) for cat, amt in validated_current.items()
        }
        return BudgetRebalanceResponse(
            previous_total_inr=previous_total,
            new_total_inr=previous_total,
            allocations=EventBudgetBreakdown(
                total_budget_inr=previous_total,
                **validated_current,
            ),
            differences={cat: 0 for cat in CANONICAL_BUDGET_CATEGORIES},
            percentages=display_percentages,
            categories_reduced_first=[],
            protected_categories=list(TIER_3_PROTECTED),
            protected_preserved=True,
            explanation=f"Budget unchanged at ₹{previous_total:,}.",
        )

    # --------------------------------------------------------------------------
    # Case B: Budget Increase
    # --------------------------------------------------------------------------
    if new_total_budget_inr > previous_total:
        diff_inr = new_total_budget_inr - previous_total
        pct_increase = (diff_inr / previous_total) * 100.0

        # Distribute additional funds proportionally based on current allocations
        additions = largest_remainder_allocation(
            total_amount=diff_inr,
            weights=validated_current,
            category_order=CANONICAL_BUDGET_CATEGORIES,
        )

        new_allocations = {
            cat: validated_current[cat] + additions[cat] for cat in CANONICAL_BUDGET_CATEGORIES
        }

        display_percentages = {
            cat: round((amt / new_total_budget_inr) * 100.0, 2)
            for cat, amt in new_allocations.items()
        }

        explanation = (
            f"Budget increased by ₹{diff_inr:,} (+{pct_increase:.1f}%). Additional funds were "
            f"distributed proportionally across all categories based on current weights, "
            f"preserving catering and buffer baselines."
        )

        return BudgetRebalanceResponse(
            previous_total_inr=previous_total,
            new_total_inr=new_total_budget_inr,
            allocations=EventBudgetBreakdown(
                total_budget_inr=new_total_budget_inr,
                **new_allocations,
            ),
            differences={cat: additions[cat] for cat in CANONICAL_BUDGET_CATEGORIES},
            percentages=display_percentages,
            categories_reduced_first=[],
            protected_categories=list(TIER_3_PROTECTED),
            protected_preserved=True,
            explanation=explanation,
        )

    # --------------------------------------------------------------------------
    # Case C: Budget Decrease
    # --------------------------------------------------------------------------
    reduction = previous_total - new_total_budget_inr
    tier1_total = sum(validated_current[c] for c in TIER_1_DISCRETIONARY)
    tier2_total = sum(validated_current[c] for c in TIER_2_FLEXIBLE)

    cuts: dict[str, int] = {cat: 0 for cat in CANONICAL_BUDGET_CATEGORIES}
    reduced_first: list[str] = []
    protected_preserved = True
    explanation = ""

    # Subcase C1: Tier 1 (entertainment + decor) can absorb the entire cut
    if reduction <= tier1_total:
        if tier1_total > 0:
            tier1_weights = {c: validated_current[c] for c in TIER_1_DISCRETIONARY}
            tier1_cuts = largest_remainder_allocation(
                total_amount=reduction,
                weights=tier1_weights,
                category_order=TIER_1_DISCRETIONARY,
            )
            for c, cut_amt in tier1_cuts.items():
                cuts[c] = cut_amt
                if cut_amt > 0:
                    reduced_first.append(c)

        cats_str = ", ".join(reduced_first) if reduced_first else "entertainment, decor"
        explanation = (
            f"Budget reduced by ₹{reduction:,}. The entire reduction was absorbed by discretionary "
            f"categories ({cats_str}), leaving catering, emergency buffer, and core operations "
            f"100% protected."
        )

    # Subcase C2: Tier 1 exhausted; Tier 2 absorbs remaining reduction
    elif reduction <= (tier1_total + tier2_total):
        # Tier 1 cut completely to 0
        for c in TIER_1_DISCRETIONARY:
            cuts[c] = validated_current[c]
            if cuts[c] > 0:
                reduced_first.append(c)

        rem_reduction = reduction - tier1_total
        if tier2_total > 0:
            tier2_weights = {c: validated_current[c] for c in TIER_2_FLEXIBLE}
            tier2_cuts = largest_remainder_allocation(
                total_amount=rem_reduction,
                weights=tier2_weights,
                category_order=TIER_2_FLEXIBLE,
            )
            for c, cut_amt in tier2_cuts.items():
                cuts[c] = cut_amt

        explanation = (
            f"Budget reduced by ₹{reduction:,}. Discretionary categories (entertainment, "
            f"decor) were reduced to zero first. Secondary operational categories were scaled "
            f"down proportionally, while catering and emergency buffer remained 100% protected."
        )

    # Subcase C3: Reduction exceeds non-protected categories (requires cutting Tier 3)
    else:
        if strict_protect:
            msg = (
                f"Protection constraint violated: requested reduction of ₹{reduction:,} requires "
                f"cutting into essential protected categories (catering: "
                f"₹{validated_current['catering']:,}, buffer: ₹{validated_current['buffer']:,}). "
                f"Maximum protected reduction is ₹{tier1_total + tier2_total:,}."
            )
            raise BudgetConstraintError(msg)

        # Check if reduction leaves at least minimal viable funds for protected categories
        if new_total_budget_inr < 2:
            msg = (
                f"Requested budget of ₹{new_total_budget_inr:,} is mathematically impossible to "
                f"allocate across protected categories."
            )
            raise BudgetConstraintError(msg)

        # Tier 1 and Tier 2 both cut to 0
        for c in TIER_1_DISCRETIONARY:
            cuts[c] = validated_current[c]
            if cuts[c] > 0:
                reduced_first.append(c)
        for c in TIER_2_FLEXIBLE:
            cuts[c] = validated_current[c]

        rem_reduction = reduction - (tier1_total + tier2_total)
        tier3_weights = {c: validated_current[c] for c in TIER_3_PROTECTED}
        tier3_cuts = largest_remainder_allocation(
            total_amount=rem_reduction,
            weights=tier3_weights,
            category_order=TIER_3_PROTECTED,
        )
        for c, cut_amt in tier3_cuts.items():
            cuts[c] = cut_amt

        protected_preserved = False
        new_catering = validated_current["catering"] - cuts["catering"]
        new_buffer = validated_current["buffer"] - cuts["buffer"]

        explanation = (
            f"Deep budget reduction of ₹{reduction:,} exceeded available non-essential funds. "
            f"Discretionary and operational categories were reduced to zero, and protected "
            f"categories were reduced proportionally (catering: ₹{new_catering:,}, "
            f"buffer: ₹{new_buffer:,}). Preserving protected allocations was mathematically "
            f"impossible under this total budget."
        )

    new_allocations = {
        cat: validated_current[cat] - cuts[cat] for cat in CANONICAL_BUDGET_CATEGORIES
    }

    display_percentages = {
        cat: round((amt / new_total_budget_inr) * 100.0, 2) for cat, amt in new_allocations.items()
    }

    differences = {cat: -cuts[cat] for cat in CANONICAL_BUDGET_CATEGORIES}

    return BudgetRebalanceResponse(
        previous_total_inr=previous_total,
        new_total_inr=new_total_budget_inr,
        allocations=EventBudgetBreakdown(
            total_budget_inr=new_total_budget_inr,
            **new_allocations,
        ),
        differences=differences,
        percentages=display_percentages,
        categories_reduced_first=reduced_first,
        protected_categories=list(TIER_3_PROTECTED),
        protected_preserved=protected_preserved,
        explanation=explanation,
    )
