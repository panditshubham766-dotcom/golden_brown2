"""Provenance validation (Guide §9.1 step 2).

Every model-supplied sid must have been returned by an approved tool in this exact
run and bound document. Forged, stale, cross-document, or unreturned IDs cause
the citation or point to be dropped.
"""
from __future__ import annotations

import logging
from typing import List, Set, Tuple
from backend.app.agent.schema import ModelAnswer, ModelPoint

logger = logging.getLogger("lexiguard.validation.provenance")


def validate_provenance(
    model_answer: ModelAnswer,
    approved_sids: Set[str],
) -> Tuple[List[ModelPoint], List[str]]:
    """
    Validate all points against approved sids returned by tools in the current run.

    Returns:
    - valid_points: list of points that passed provenance checks.
    - dropped_reasons: descriptions of points or sids that were rejected.
    """
    valid_points: List[ModelPoint] = []
    dropped_reasons: List[str] = []

    for point in model_answer.points:
        kind = point.kind.upper()

        if kind == "GENERAL_EXPLANATION":
            # General explanations do not cite document sids
            clean_point = point.model_copy(update={"sids": []})
            valid_points.append(clean_point)
            continue

        # Points requiring citations
        original_sids = point.sids
        filtered_sids = [sid for sid in original_sids if sid in approved_sids]

        # Check for forged or unapproved sids
        forged_sids = set(original_sids) - approved_sids
        if forged_sids:
            dropped_reasons.append(
                f"Point {point.point_id} cited forged/unapproved sids: {sorted(forged_sids)}"
            )

        # If point had sids but none were approved, or if kind requires citations and none remain
        if not filtered_sids:
            dropped_reasons.append(
                f"Point {point.point_id} ({point.kind}) dropped: no approved citations remain."
            )
            continue

        # Conflict points require at least 2 distinct sids
        if kind == "CONFLICT" and len(filtered_sids) < 2:
            dropped_reasons.append(
                f"Point {point.point_id} (CONFLICT) dropped: requires at least 2 approved citations."
            )
            continue

        clean_point = point.model_copy(update={"sids": filtered_sids})
        valid_points.append(clean_point)

    return valid_points, dropped_reasons
