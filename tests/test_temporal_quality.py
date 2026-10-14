from app.orchestration.quality import decide_review


def baseline(**changes):
    state = {
        "insight_present": True, "generated_sql": True,
        "verified": True, "confidence": "High",
        "pii_columns": 0, "errors": False,
        "fallback_sql": False, "grounding_issues": False,
        "clarification_question": None,
    }
    state.update(changes)
    return state


def test_verified_sql_is_approved():
    assert decide_review(baseline())["outcome"] == "approved"


def test_unverified_or_sensitive_outputs_require_human():
    for change in (
        {"verified": False}, {"pii_columns": 1},
        {"confidence": "Low"}, {"fallback_sql": True},
        {"grounding_issues": True},
    ):
        result = decide_review(baseline(**change))
        assert result["outcome"] == "needs_approval"
        assert result["reasons"]


def test_execution_failures_are_rejected():
    assert decide_review(baseline(errors=True))["outcome"] == "rejected"
    assert decide_review(baseline(insight_present=False))["outcome"] == "rejected"


def test_ambiguity_is_not_reported_as_success():
    result = decide_review(baseline(clarification_question="Which revenue column?"))
    assert result["outcome"] == "needs_clarification"


def test_dataset_overview_does_not_require_sql_verification():
    assert decide_review(baseline(generated_sql=False, verified=False))["outcome"] == "approved"

def test_inaccurate_numbers_require_review():
    assert decide_review(baseline(number_check_valid=False))["outcome"] == "needs_approval"


def test_missing_catalog_requires_review():
    result = decide_review(baseline(catalog_present=False))
    assert result["outcome"] == "needs_approval"
