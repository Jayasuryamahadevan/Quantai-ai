"""Deterministic quality policy; independent of model assertions."""
from __future__ import annotations

from typing import Any


def decide_review(analysis: dict[str, Any]) -> dict[str, Any]:
    """Fail closed for errors; require review when claims cannot be verified."""
    reasons: list[str] = []
    if analysis.get("errors"):
        return {"outcome": "rejected", "reasons": ["The analyst pipeline reported errors."]}
    if analysis.get("clarification_question"):
        return {
            "outcome": "needs_clarification",
            "reasons": [analysis["clarification_question"][:500]],
        }
    if not analysis.get("insight_present"):
        return {"outcome": "rejected", "reasons": ["No analysis result was produced."]}

    if analysis.get("catalog_present") is False:
        reasons.append("The data source has no validated column catalog.")
    if analysis.get("pii_columns", 0):
        reasons.append("The source contains columns marked as personal information.")
    if analysis.get("fallback_sql"):
        reasons.append("Free-form model-generated SQL was used.")
    if analysis.get("grounding_issues"):
        reasons.append("Some values could not be grounded against the source.")
    if analysis.get("number_check_valid") is False:
        reasons.append("The generated narrative failed numerical verification.")
    if analysis.get("confidence") == "Low":
        reasons.append("The analysis has low confidence.")

    # Structural overview and dataset summary don't produce SQL/cross-checks.
    if analysis.get("generated_sql") and not analysis.get("verified"):
        reasons.append("SQL results were not independently verified.")

    return {
        "outcome": "needs_approval" if reasons else "approved",
        "reasons": reasons,
    }
