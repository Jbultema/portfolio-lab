"""Low correlation and malformed flags cannot qualify a specialist."""

import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.specialist_evidence import qualification


def test_low_correlation_does_not_qualify_an_unavailable_event_specialist():
    checked = qualification({"return_correlation": 0.01, "distinct_information": True})
    assert checked["status"] == "research_only"
    assert "point_in_time_universe" in checked["unmet_gates"]
    assert not checked["portfolio_allocation_allowed"]


@pytest.mark.parametrize("evidence", [{"public_data": "true"},
    {"independent_matured_prospective_observations": True},
    {"independent_matured_prospective_observations": float("nan")}])
def test_false_or_malformed_evidence_fails_closed(evidence):
    with pytest.raises(ContractError):
        qualification(evidence)


def test_even_complete_evidence_only_opens_human_review():
    evidence = dict.fromkeys(("public_data", "point_in_time_universe", "original_timestamps",
        "failed_security_treatment", "distinct_information", "risk_matched_incremental_benefit",
        "stress_tests_pass", "selection_adjustment_pass", "frozen_prospective_lineage"), True)
    checked = qualification(evidence | {"independent_matured_prospective_observations": 30})
    assert checked["status"] == "eligible_for_human_review"
    assert checked["action_authorized"] is False
