import json
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import pytest

import portfolio_lab.audit as audit_module
from portfolio_lab.audit import audit, record_shadow
from portfolio_lab.contracts import ContractError, digest, json_hash

NOW = datetime(2026, 11, 25, 18, tzinfo=UTC)


def report(root):
    root.mkdir()
    for filename in (
        "frozen_selection.json",
        "trial_registry.csv",
        "metrics.csv",
        "returns.parquet",
        "selected_targets.parquet",
        "selected_budgets.parquet",
    ):
        (root / filename).write_bytes(b"integrity-unit-test-placeholder-not-market-data")
    (root / "current_state.json").write_text(
        json.dumps(
            {
                "as_of_close": "2026-11-24",
                "selected_research_policy": "frozen",
                "action": "NO ACTION",
            }
        )
    )
    code_root = Path(audit_module.__file__).parent
    m = {
        "artifacts": {p.name: digest(p) for p in root.iterdir()},
        "policy_source_sha256": json_hash(
            {str(p.relative_to(code_root)): digest(p) for p in sorted(code_root.rglob("*.py"))}
        ),
        "selection": {"selected": "frozen"},
        "metadata": {"bundles": [], "bundle_sha256": []},
        "environment": {"numpy": version("numpy")},
        "authority": "research_only",
        "automatic_promotion_allowed": False,
    }
    (root / "manifest.json").write_text(json.dumps(m))
    return root


def test_valid_integrity_fixture_is_not_trading_approval(tmp_path):
    result = audit(report(tmp_path / "report"), now=NOW)
    assert result["status"] == "passed_research_integrity"
    assert result["action_authorized"] is False


@pytest.mark.parametrize(
    "kind",
    ["artifact_tamper", "source_drift", "dependency_drift", "authority", "selection", "stale"],
)
def test_invalid_or_stale_evidence_fails_closed(kind, tmp_path):
    root = report(tmp_path / "report")
    path = root / "manifest.json"
    m = json.loads(path.read_text())
    now = NOW
    if kind == "artifact_tamper":
        (root / "metrics.csv").write_bytes(b"changed")
    elif kind == "source_drift":
        m["policy_source_sha256"] = "different_code"
    elif kind == "dependency_drift":
        m["environment"]["numpy"] = "0.0.0"
    elif kind == "authority":
        m["automatic_promotion_allowed"] = True
    elif kind == "selection":
        m["selection"]["selected"] = "other"
    else:
        now += timedelta(days=10)
    path.write_text(json.dumps(m))
    result = audit(root, now=now)
    assert result["status"] == "failed_closed"
    assert result["errors"]


def test_shadow_record_is_immutable_and_idempotent(tmp_path):
    root = report(tmp_path / "report")
    a = record_shadow(root, tmp_path / "journal", now=NOW)
    before = a.read_bytes()
    b = record_shadow(root, tmp_path / "journal", now=NOW + timedelta(hours=1))
    assert a == b
    assert a.read_bytes() == before
    assert json.loads(before)["performance_eligible"] is False


def test_corrupt_existing_shadow_cannot_be_silently_replaced(tmp_path):
    root = report(tmp_path / "report")
    path = record_shadow(root, tmp_path / "journal", now=NOW)
    record = json.loads(path.read_text())
    record["signal"]["action"] = "changed"
    path.write_text(json.dumps(record))
    with pytest.raises(ContractError, match="immutable"):
        record_shadow(root, tmp_path / "journal", now=NOW)
