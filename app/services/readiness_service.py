"""Deterministic Event Readiness Assessment Service for PlanProof AI.

Evaluates an event profile across core planning domains:
1. Planning Completeness (15%): Presence of core event details, dates, and locations.
2. Budget Readiness (25%): Valid allocations, non-negative amounts, and emergency buffer health (>= 5%).
3. Timeline Readiness (20%): Milestone completion ratio, timeliness, and overdue penalties.
4. Vendor Coordination (25%): Booking progression, task execution, and core vendor coverage.
5. Risk Preparedness (15%): Pre-mortem failure mode severity and mitigating measures.
6. Crisis Follow-up (15% when active; omitted without penalty when no records exist):
   Unresolved recovery actions and incident statuses.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.schemas import (
    EventProfile,
    EventReadinessResponse,
    MilestonePriority,
    MilestoneStatus,
    ReadinessActionPriority,
    ReadinessCategory,
    ReadinessCategoryScore,
    ReadinessNextAction,
    ReadinessStatus,
    RecoveryActionStatus,
    RecoveryStatus,
    VendorBookingStatus,
    VendorChecklistPriority,
    VendorChecklistStatus,
)
from app.services.risk_service import analyze_event_risks
from app.services.timeline import generate_event_timeline_schedule


class ReadinessService:
    """Evaluates event planning readiness and produces deterministic diagnostics and next actions."""

    BASE_WEIGHTS: dict[ReadinessCategory, float] = {
        ReadinessCategory.PLANNING_COMPLETENESS: 15.0,
        ReadinessCategory.BUDGET_READINESS: 25.0,
        ReadinessCategory.TIMELINE_READINESS: 20.0,
        ReadinessCategory.VENDOR_COORDINATION: 25.0,
        ReadinessCategory.RISK_PREPAREDNESS: 15.0,
        ReadinessCategory.CRISIS_FOLLOWUP: 15.0,
    }

    @classmethod
    def calculate_readiness(
        cls,
        profile: EventProfile,
        reference_date: date | None = None,
    ) -> EventReadinessResponse:
        """Deterministically assess event readiness across all available planning domains.

        Args:
            profile: Target EventProfile containing budget, checklist, timeline, and recovery records.
            reference_date: Optional simulated reference date for timeline deadlines and overdue checks.

        Returns:
            EventReadinessResponse containing overall score, status, category breakdowns, and prioritized next actions.
        """
        now_utc = datetime.now(timezone.utc)
        critical_concerns: list[str] = []
        raw_next_actions: list[ReadinessNextAction] = []
        missing_information: list[str] = []

        total_completed_items = 0
        total_outstanding_items = 0

        # ----------------------------------------------------------------------
        # 1. PLANNING COMPLETENESS
        # ----------------------------------------------------------------------
        planning_score, planning_completed, planning_missing = cls._evaluate_planning_completeness(
            profile, missing_information, raw_next_actions
        )
        total_completed_items += planning_completed
        total_outstanding_items += planning_missing

        planning_cat = ReadinessCategoryScore(
            category=ReadinessCategory.PLANNING_COMPLETENESS,
            name="Planning Completeness",
            score=planning_score,
            weight_percentage=0.0,  # Will be set during normalization
            is_available=True,
            explanation=(
                "All core event parameters, dates, and locations are confirmed."
                if planning_score == 100
                else (
                    "Essential parameters specified; event date is missing, preventing calendar scheduling."
                    if profile.event_date is None
                    else "Core event parameters documented with some optional details pending."
                )
            ),
            supporting_counts={
                "core_fields_present": planning_completed,
                "missing_fields": planning_missing,
                "has_event_date": 1 if profile.event_date is not None else 0,
                "has_city": 1 if profile.city else 0,
                "has_name": 1 if profile.event_name else 0,
            },
        )

        # ----------------------------------------------------------------------
        # 2. BUDGET READINESS
        # ----------------------------------------------------------------------
        budget_cat, budget_completed, budget_outstanding = cls._evaluate_budget_readiness(
            profile, critical_concerns, raw_next_actions, missing_information
        )
        total_completed_items += budget_completed
        total_outstanding_items += budget_outstanding

        # ----------------------------------------------------------------------
        # 3. TIMELINE READINESS
        # ----------------------------------------------------------------------
        timeline_cat, timeline_completed, timeline_outstanding = cls._evaluate_timeline_readiness(
            profile, reference_date, critical_concerns, raw_next_actions
        )
        total_completed_items += timeline_completed
        total_outstanding_items += timeline_outstanding

        # ----------------------------------------------------------------------
        # 4. VENDOR COORDINATION
        # ----------------------------------------------------------------------
        vendor_cat, vendor_completed, vendor_outstanding = cls._evaluate_vendor_coordination(
            profile, critical_concerns, raw_next_actions
        )
        total_completed_items += vendor_completed
        total_outstanding_items += vendor_outstanding

        # ----------------------------------------------------------------------
        # 5. RISK PREPAREDNESS
        # ----------------------------------------------------------------------
        risk_cat = cls._evaluate_risk_preparedness(
            profile, reference_date, critical_concerns, raw_next_actions
        )

        # ----------------------------------------------------------------------
        # 6. CRISIS FOLLOW-UP
        # ----------------------------------------------------------------------
        crisis_cat, crisis_completed, crisis_outstanding = cls._evaluate_crisis_followup(
            profile, critical_concerns, raw_next_actions
        )
        total_completed_items += crisis_completed
        total_outstanding_items += crisis_outstanding

        # ----------------------------------------------------------------------
        # NORMALIZE WEIGHTS & CALCULATE OVERALL SCORE
        # ----------------------------------------------------------------------
        all_categories = [
            planning_cat,
            budget_cat,
            timeline_cat,
            vendor_cat,
            risk_cat,
            crisis_cat,
        ]

        # Determine available categories
        available_cats = [c for c in all_categories if c.is_available and c.score is not None]

        # Check for insufficient data
        is_insufficient = (
            len(available_cats) < 2
            or profile.total_budget_inr <= 0
            or profile.guest_count <= 0
            or (profile.budget is None and not profile.vendor_checklist)
        )

        overall_score: int | None = None
        readiness_status: ReadinessStatus

        if is_insufficient:
            overall_score = None
            readiness_status = ReadinessStatus.INSUFFICIENT_DATA
            if profile.total_budget_inr <= 0:
                missing_information.append("Event total budget is invalid or zero.")
            if profile.guest_count <= 0:
                missing_information.append("Guest count is invalid or zero.")
            if profile.budget is None:
                missing_information.append("Event budget allocations are not available.")
        else:
            total_avail_weight = sum(cls.BASE_WEIGHTS[c.category] for c in available_cats)
            weighted_sum = 0.0

            avail_scored = [c for c in all_categories if c.is_available and c.score is not None and total_avail_weight > 0]
            sum_assigned = 0.0
            for i, cat in enumerate(avail_scored):
                normalized_weight = cls.BASE_WEIGHTS[cat.category] / total_avail_weight
                weighted_sum += normalized_weight * cat.score
                if i == len(avail_scored) - 1:
                    # Final category absorbs rounding difference to guarantee exact 100.0% sum
                    cat.weight_percentage = round(100.0 - sum_assigned, 1)
                else:
                    cat.weight_percentage = round(normalized_weight * 100.0, 1)
                    sum_assigned += cat.weight_percentage

            for cat in all_categories:
                if not (cat.is_available and cat.score is not None and total_avail_weight > 0):
                    cat.weight_percentage = 0.0

            overall_score = max(0, min(100, round(weighted_sum)))

            if overall_score < 40:
                readiness_status = ReadinessStatus.NOT_STARTED
            elif overall_score < 65:
                readiness_status = ReadinessStatus.NEEDS_ATTENTION
            elif overall_score < 85:
                readiness_status = ReadinessStatus.IN_PROGRESS
            else:
                readiness_status = ReadinessStatus.WELL_PREPARED

        # ----------------------------------------------------------------------
        # DEDUPLICATE AND PRIORITIZE NEXT ACTIONS
        # ----------------------------------------------------------------------
        prioritized_actions = cls._prioritize_next_actions(raw_next_actions)

        return EventReadinessResponse(
            event_id=profile.event_id,
            overall_score=overall_score,
            readiness_status=readiness_status,
            category_scores=all_categories,
            completed_items=total_completed_items,
            outstanding_items=total_outstanding_items,
            critical_concerns=critical_concerns,
            recommended_next_actions=prioritized_actions,
            missing_information=missing_information,
            generated_at=now_utc,
        )

    # ==========================================================================
    # HELPER EVALUATION METHODS
    # ==========================================================================

    @classmethod
    def _evaluate_planning_completeness(
        cls,
        profile: EventProfile,
        missing_information: list[str],
        next_actions: list[ReadinessNextAction],
    ) -> tuple[int, int, int]:
        """Assess profile parameters: event type, guest count, budget, date, city, name."""
        score = 0
        completed_fields = 0
        missing_fields = 0

        # Mandatory fields
        if profile.event_type:
            score += 20
            completed_fields += 1
        else:
            missing_fields += 1

        if profile.guest_count > 0:
            score += 20
            completed_fields += 1
        else:
            missing_fields += 1

        if profile.total_budget_inr > 0:
            score += 20
            completed_fields += 1
        else:
            missing_fields += 1

        # Optional/enrichment fields
        if profile.event_date is not None:
            score += 20
            completed_fields += 1
        else:
            missing_fields += 1
            missing_information.append(
                "Event scheduled date is not set; calendar timeline deadlines and overdue tracking are inactive."
            )
            next_actions.append(
                ReadinessNextAction(
                    action_id="ACT-PLAN-CONFIRM-DATE",
                    title="Confirm Scheduled Event Date",
                    description="Set the event date to calculate calendar deadlines, lead times, and overdue warnings.",
                    priority=ReadinessActionPriority.HIGH,
                    category="planning",
                    target_id=None,
                    target_view="event-details",
                )
            )

        if profile.city and len(profile.city.strip()) > 0:
            score += 10
            completed_fields += 1
        else:
            missing_fields += 1
            missing_information.append("Event city location is not set; regional defaults are assumed.")

        if profile.event_name and len(profile.event_name.strip()) > 0:
            score += 10
            completed_fields += 1
        else:
            missing_fields += 1
            missing_information.append("Event title/name is not set.")

        return min(100, max(0, score)), completed_fields, missing_fields

    @classmethod
    def _evaluate_budget_readiness(
        cls,
        profile: EventProfile,
        critical_concerns: list[str],
        next_actions: list[ReadinessNextAction],
        missing_information: list[str],
    ) -> tuple[ReadinessCategoryScore, int, int]:
        """Assess budget allocations, math integrity, and emergency buffer health."""
        if profile.budget is None:
            missing_information.append("Event budget allocations have not been generated.")
            return (
                ReadinessCategoryScore(
                    category=ReadinessCategory.BUDGET_READINESS,
                    name="Budget Readiness",
                    score=None,
                    weight_percentage=0.0,
                    is_available=False,
                    explanation="Budget breakdown has not been calculated or assigned.",
                    supporting_counts={"total_budget_inr": 0, "buffer_inr": 0},
                ),
                0,
                1,
            )

        b = profile.budget
        total = b.total_budget_inr
        buffer_inr = b.buffer
        buffer_pct = (buffer_inr / total * 100.0) if total > 0 else 0.0

        score = 0

        # Allocations validity (sum check)
        category_sum = (
            b.venue
            + b.catering
            + b.decor
            + b.photo_video
            + b.attire_beauty
            + b.entertainment
            + b.logistics
            + b.buffer
        )
        if category_sum == total:
            score += 30

        # Non-negative allocations
        categories = [
            b.venue,
            b.catering,
            b.decor,
            b.photo_video,
            b.attire_beauty,
            b.entertainment,
            b.logistics,
            b.buffer,
        ]
        if all(val >= 0 for val in categories):
            score += 20

        # Emergency buffer evaluation
        if buffer_pct >= 5.0:
            score += 40
        elif buffer_pct > 0.0:
            score += 20
            next_actions.append(
                ReadinessNextAction(
                    action_id="ACT-BUDGET-BUFFER",
                    title="Strengthen Emergency Buffer",
                    description=f"Current buffer is ₹{buffer_inr:,} ({round(buffer_pct, 1)}%). Rebalance to achieve the recommended 5% reserve.",
                    priority=ReadinessActionPriority.MEDIUM,
                    category="budget",
                    target_id=None,
                    target_view="budget",
                )
            )
        else:
            # Buffer == 0
            critical_concerns.append(
                "Emergency contingency buffer is ₹0 (0.0%); budget provides no financial cushion for disruptions."
            )
            next_actions.append(
                ReadinessNextAction(
                    action_id="ACT-BUDGET-BUFFER",
                    title="Ringfence Emergency Buffer",
                    description=f"Rebalance budget to protect at least 5% (₹{int(total * 0.05):,}) in emergency reserve.",
                    priority=ReadinessActionPriority.HIGH,
                    category="budget",
                    target_id=None,
                    target_view="budget",
                )
            )

        # Core foundational categories funded
        if b.venue > 0 and b.catering > 0:
            score += 10

        score = min(100, max(0, score))

        explanation = (
            f"Budget accurately allocated to ₹{total:,} with healthy ₹{buffer_inr:,} ({round(buffer_pct, 1)}%) contingency buffer."
            if buffer_pct >= 5.0
            else (
                f"Budget allocations valid; emergency buffer is ₹{buffer_inr:,} ({round(buffer_pct, 1)}%), below recommended 5%."
                if buffer_pct > 0.0
                else "Budget fully allocated, but emergency buffer is unallocated (₹0); rebalancing recommended."
            )
        )

        return (
            ReadinessCategoryScore(
                category=ReadinessCategory.BUDGET_READINESS,
                name="Budget Readiness",
                score=score,
                weight_percentage=0.0,
                is_available=True,
                explanation=explanation,
                supporting_counts={
                    "total_budget_inr": total,
                    "buffer_inr": buffer_inr,
                    "buffer_percentage": round(buffer_pct, 1),
                },
            ),
            1 if score >= 80 else 0,
            0 if score >= 80 else 1,
        )

    @classmethod
    def _evaluate_timeline_readiness(
        cls,
        profile: EventProfile,
        reference_date: date | None,
        critical_concerns: list[str],
        next_actions: list[ReadinessNextAction],
    ) -> tuple[ReadinessCategoryScore, int, int]:
        """Assess timeline milestones, completion ratio, and overdue tasks."""
        schedule = generate_event_timeline_schedule(
            event_id=profile.event_id,
            event_type=profile.event_type,
            event_date=profile.event_date,
            milestone_statuses=profile.milestone_statuses,
            reference_date=reference_date,
        )

        if not schedule or not schedule.milestones:
            return (
                ReadinessCategoryScore(
                    category=ReadinessCategory.TIMELINE_READINESS,
                    name="Timeline Readiness",
                    score=None,
                    weight_percentage=0.0,
                    is_available=False,
                    explanation="No timeline milestones are configured for this event.",
                    supporting_counts={"total_milestones": 0, "completed_milestones": 0},
                ),
                0,
                0,
            )

        total_m = len(schedule.milestones)
        comp_m = sum(1 for m in schedule.milestones if m.status == MilestoneStatus.COMPLETED)
        over_m = sum(
            1
            for m in schedule.milestones
            if m.is_overdue and m.status != MilestoneStatus.COMPLETED
        )
        pend_m = total_m - comp_m

        # Base completion (up to 70 pts)
        base_completion = (comp_m / total_m) * 70.0
        # Timeliness (up to 30 pts, penalized by overdue milestones)
        timeliness = max(0.0, 30.0 - (over_m * 10.0))
        score = min(100, max(0, round(base_completion + timeliness)))

        if over_m > 0:
            critical_concerns.append(
                f"{over_m} timeline milestone(s) are overdue past their scheduled deadline."
            )

        # Identify top incomplete milestone for action recommendation
        overdue_milestones = [
            m for m in schedule.milestones if m.is_overdue and m.status != MilestoneStatus.COMPLETED
        ]
        pending_milestones = [
            m for m in schedule.milestones if m.status == MilestoneStatus.PENDING and not m.is_overdue
        ]

        if overdue_milestones:
            # Pick earliest overdue milestone
            top_overdue = sorted(
                overdue_milestones,
                key=lambda m: (m.due_date or date.max, m.milestone_id),
            )[0]
            next_actions.append(
                ReadinessNextAction(
                    action_id=f"ACT-TL-{top_overdue.milestone_id}",
                    title=f"Complete Overdue Milestone: {top_overdue.title}",
                    description=f"Task was due on {top_overdue.due_date or 'T-' + str(top_overdue.days_before_event) + ' days'}; mark complete to recover timeline.",
                    priority=ReadinessActionPriority.CRITICAL,
                    category="timeline",
                    target_id=top_overdue.milestone_id,
                    target_view="timeline",
                )
            )
        elif pending_milestones:
            # Pick next upcoming pending milestone
            top_pending = sorted(
                pending_milestones,
                key=lambda m: (m.due_date or date.max, m.milestone_id),
            )[0]
            next_actions.append(
                ReadinessNextAction(
                    action_id=f"ACT-TL-{top_pending.milestone_id}",
                    title=f"Execute Milestone: {top_pending.title}",
                    description=f"Upcoming milestone scheduled for {top_pending.due_date or 'T-' + str(top_pending.days_before_event) + ' days'}.",
                    priority=(
                        ReadinessActionPriority.HIGH
                        if top_pending.priority == MilestonePriority.HIGH
                        else ReadinessActionPriority.MEDIUM
                    ),
                    category="timeline",
                    target_id=top_pending.milestone_id,
                    target_view="timeline",
                )
            )

        explanation = (
            f"{comp_m}/{total_m} milestones completed ({round(comp_m/total_m*100)}%); {over_m} milestone(s) overdue."
            if over_m > 0
            else f"{comp_m}/{total_m} milestones completed ({round(comp_m/total_m*100)}%); all tasks on schedule."
        )

        return (
            ReadinessCategoryScore(
                category=ReadinessCategory.TIMELINE_READINESS,
                name="Timeline Readiness",
                score=score,
                weight_percentage=0.0,
                is_available=True,
                explanation=explanation,
                supporting_counts={
                    "total_milestones": total_m,
                    "completed_milestones": comp_m,
                    "overdue_milestones": over_m,
                    "pending_milestones": pend_m,
                },
            ),
            comp_m,
            pend_m,
        )

    @classmethod
    def _evaluate_vendor_coordination(
        cls,
        profile: EventProfile,
        critical_concerns: list[str],
        next_actions: list[ReadinessNextAction],
    ) -> tuple[ReadinessCategoryScore, int, int]:
        """Assess vendor checklist execution, booking progressions, and foundational coverage."""
        items = profile.vendor_checklist
        if not items:
            return (
                ReadinessCategoryScore(
                    category=ReadinessCategory.VENDOR_COORDINATION,
                    name="Vendor Coordination",
                    score=None,
                    weight_percentage=0.0,
                    is_available=False,
                    explanation="Vendor coordination checklist has not been generated.",
                    supporting_counts={"total_vendors": 0, "completed_vendors": 0},
                ),
                0,
                0,
            )

        active_items = [it for it in items if it.status != VendorChecklistStatus.SKIPPED]
        if not active_items:
            score = 100
        else:
            item_points: list[float] = []
            for it in active_items:
                if it.status == VendorChecklistStatus.COMPLETED:
                    item_points.append(1.0)
                elif it.booking_status == VendorBookingStatus.BOOKED:
                    item_points.append(0.85)
                elif (
                    it.booking_status == VendorBookingStatus.CONTACTED
                    or it.status == VendorChecklistStatus.IN_PROGRESS
                ):
                    item_points.append(0.50)
                elif it.booking_status == VendorBookingStatus.RESEARCHING:
                    item_points.append(0.25)
                else:
                    item_points.append(0.0)

            score = min(100, max(0, round((sum(item_points) / len(active_items)) * 100.0)))

        comp_count = sum(1 for it in items if it.status == VendorChecklistStatus.COMPLETED)
        booked_count = sum(1 for it in items if it.booking_status == VendorBookingStatus.BOOKED)
        pend_count = sum(
            1
            for it in items
            if it.status in (VendorChecklistStatus.PENDING, VendorChecklistStatus.IN_PROGRESS)
        )
        skipped_count = sum(1 for it in items if it.status == VendorChecklistStatus.SKIPPED)

        # Check foundational high-priority vendors (Venue, Catering)
        unstarted_foundational = [
            it
            for it in active_items
            if it.priority == VendorChecklistPriority.HIGH
            and it.booking_status == VendorBookingStatus.NOT_STARTED
        ]
        for it in unstarted_foundational:
            critical_concerns.append(
                f"Essential vendor '{it.title}' ({it.category.value}) is not yet researched or booked."
            )

        # Recommend next incomplete high-priority vendor task
        incomplete_high = [
            it
            for it in active_items
            if it.status != VendorChecklistStatus.COMPLETED
            and it.booking_status != VendorBookingStatus.BOOKED
            and it.priority == VendorChecklistPriority.HIGH
        ]
        incomplete_other = [
            it
            for it in active_items
            if it.status != VendorChecklistStatus.COMPLETED
            and it.booking_status != VendorBookingStatus.BOOKED
            and it.priority != VendorChecklistPriority.HIGH
        ]

        target_vendor = (incomplete_high or incomplete_other)[0] if (incomplete_high or incomplete_other) else None
        if target_vendor:
            next_actions.append(
                ReadinessNextAction(
                    action_id=f"ACT-VEND-{target_vendor.id}",
                    title=f"Book Vendor: {target_vendor.title}",
                    description=f"Progress booking progression from '{target_vendor.booking_status.value.replace('_', ' ')}' for {target_vendor.category.value}.",
                    priority=(
                        ReadinessActionPriority.HIGH
                        if target_vendor.priority == VendorChecklistPriority.HIGH
                        else ReadinessActionPriority.MEDIUM
                    ),
                    category="vendor",
                    target_id=target_vendor.id,
                    target_view="vendors",
                )
            )

        explanation = (
            f"{booked_count}/{len(active_items)} vendors booked, {comp_count} tasks completed."
            if booked_count > 0 or comp_count > 0
            else f"0/{len(active_items)} vendors booked; initial vendor outreach pending."
        )

        return (
            ReadinessCategoryScore(
                category=ReadinessCategory.VENDOR_COORDINATION,
                name="Vendor Coordination",
                score=score,
                weight_percentage=0.0,
                is_available=True,
                explanation=explanation,
                supporting_counts={
                    "total_vendors": len(items),
                    "active_vendors": len(active_items),
                    "booked_vendors": booked_count,
                    "completed_tasks": comp_count,
                    "pending_tasks": pend_count,
                    "skipped_tasks": skipped_count,
                },
            ),
            comp_count,
            pend_count,
        )

    @classmethod
    def _evaluate_risk_preparedness(
        cls,
        profile: EventProfile,
        reference_date: date | None,
        critical_concerns: list[str],
        next_actions: list[ReadinessNextAction],
    ) -> ReadinessCategoryScore:
        """Assess pre-mortem risks and preventive mitigations."""
        risks_res = analyze_event_risks(profile=profile, reference_date=reference_date)

        crit_count = risks_res.summary.critical_risks
        high_count = risks_res.summary.high_risks
        med_count = risks_res.summary.medium_risks

        base = 100
        # Critical risks deduct 15 pts, high deducts 8 pts, medium deducts 3 pts
        deduction = (crit_count * 15) + (high_count * 8) + (med_count * 3)
        score = min(100, max(0, base - deduction))

        # Flag critical risks
        critical_risks = [r for r in risks_res.risks if r.priority_score >= 9]
        for r in critical_risks:
            critical_concerns.append(
                f"Critical Risk [{r.id}]: {r.title} — {r.contingency_plan[:90]}..."
            )

        # Recommend top risk mitigation
        if risks_res.risks:
            top_risk = risks_res.risks[0]
            next_actions.append(
                ReadinessNextAction(
                    action_id=f"ACT-RISK-{top_risk.id}",
                    title=f"Mitigate Risk: {top_risk.title}",
                    description=f"Implement recommended fallback: {top_risk.contingency_plan[:150]}.",
                    priority=(
                        ReadinessActionPriority.HIGH
                        if top_risk.priority_score >= 9
                        else ReadinessActionPriority.MEDIUM
                    ),
                    category="risk",
                    target_id=top_risk.id,
                    target_view="risks",
                )
            )

        explanation = (
            f"{crit_count} critical and {high_count} high-priority risk(s) identified requiring contingency planning."
            if crit_count > 0
            else (
                f"0 critical risks; {high_count} high-priority risk(s) identified with preventive measures."
                if high_count > 0
                else f"Low risk profile; {risks_res.total_risks} minor risks documented with mitigations."
            )
        )

        return ReadinessCategoryScore(
            category=ReadinessCategory.RISK_PREPAREDNESS,
            name="Risk Preparedness",
            score=score,
            weight_percentage=0.0,
            is_available=True,
            explanation=explanation,
            supporting_counts={
                "total_risks": risks_res.total_risks,
                "critical_risks": crit_count,
                "high_risks": high_count,
                "medium_risks": med_count,
                "highest_priority_score": risks_res.summary.highest_priority_score,
            },
        )

    @classmethod
    def _evaluate_crisis_followup(
        cls,
        profile: EventProfile,
        critical_concerns: list[str],
        next_actions: list[ReadinessNextAction],
    ) -> tuple[ReadinessCategoryScore, int, int]:
        """Assess crisis recovery records and unresolved recovery actions."""
        records = profile.recovery_records
        if not records:
            # Mark unavailable; will not count or penalize score
            return (
                ReadinessCategoryScore(
                    category=ReadinessCategory.CRISIS_FOLLOWUP,
                    name="Crisis Follow-up",
                    score=None,
                    weight_percentage=0.0,
                    is_available=False,
                    explanation="No crisis recovery records saved for this event; crisis follow-up is not applicable.",
                    supporting_counts={"total_records": 0, "open_records": 0, "resolved_records": 0},
                ),
                0,
                0,
            )

        total_recs = len(records)
        resolved_recs = sum(1 for r in records if r.status == RecoveryStatus.RESOLVED)
        open_recs = total_recs - resolved_recs

        all_actions = [a for r in records for a in r.actions]
        comp_actions = sum(1 for a in all_actions if a.status == RecoveryActionStatus.COMPLETED)
        pend_actions = len(all_actions) - comp_actions

        if all_actions:
            score = min(100, max(0, round((comp_actions / len(all_actions)) * 100.0)))
        else:
            score = 100 if resolved_recs == total_recs else 50

        # Unresolved records
        unresolved = [r for r in records if r.status != RecoveryStatus.RESOLVED]
        for r in unresolved:
            critical_concerns.append(
                f"Active crisis incident '{r.crisis_type}' (Severity {r.severity}) has incomplete recovery actions."
            )

        # Recommend first pending crisis action
        pending_crisis_actions = [
            (r, a)
            for r in records
            for a in r.actions
            if a.status in (RecoveryActionStatus.PENDING, RecoveryActionStatus.IN_PROGRESS)
        ]
        if pending_crisis_actions:
            rec, act = pending_crisis_actions[0]
            next_actions.append(
                ReadinessNextAction(
                    action_id=f"ACT-CRISIS-{act.action_id}",
                    title=f"Crisis Action: {act.title}",
                    description=f"Execute pending recovery action for incident '{rec.crisis_type}'.",
                    priority=(
                        ReadinessActionPriority.CRITICAL
                        if rec.severity >= 3
                        else ReadinessActionPriority.HIGH
                    ),
                    category="crisis",
                    target_id=act.action_id,
                    target_view="recovery-history",
                )
            )

        explanation = (
            f"All {total_recs} crisis recovery record(s) resolved."
            if open_recs == 0
            else f"{open_recs} active crisis incident(s); {comp_actions}/{len(all_actions)} actions completed."
        )

        return (
            ReadinessCategoryScore(
                category=ReadinessCategory.CRISIS_FOLLOWUP,
                name="Crisis Follow-up",
                score=score,
                weight_percentage=0.0,
                is_available=True,
                explanation=explanation,
                supporting_counts={
                    "total_records": total_recs,
                    "resolved_records": resolved_recs,
                    "open_records": open_recs,
                    "total_actions": len(all_actions),
                    "completed_actions": comp_actions,
                    "pending_actions": pend_actions,
                },
            ),
            comp_actions if all_actions else resolved_recs,
            pend_actions if all_actions else open_recs,
        )

    @classmethod
    def _prioritize_next_actions(
        cls,
        raw_actions: list[ReadinessNextAction],
        limit: int = 5,
    ) -> list[ReadinessNextAction]:
        """Deduplicate actions by (category, target_id) and sort by priority order."""
        priority_weights = {
            ReadinessActionPriority.CRITICAL: 0,
            ReadinessActionPriority.HIGH: 1,
            ReadinessActionPriority.MEDIUM: 2,
            ReadinessActionPriority.LOW: 3,
        }

        seen_keys: set[tuple[str, str | None]] = set()
        deduped: list[ReadinessNextAction] = []

        for act in raw_actions:
            key = (act.category, act.target_id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(act)

        deduped.sort(key=lambda a: priority_weights.get(a.priority, 99))
        return deduped[:limit]
