import json

import pytest

from portfolio_lab.adaptive_cash_audit import verify_audit
from portfolio_lab.contracts import ContractError, digest


def audit_fixture(root, *, allowed=False):
    summary = {"kind": "adaptive_cash_control_audit_v1", "portfolio_allocation_allowed": allowed}
    (root / "summary.json").write_text(json.dumps(summary))
    for name in ("uncertainty", "rolling_consistency", "episode_omissions"):
        (root / f"{name}.csv").write_text("test\n1\n")
    files = {p.name: digest(p) for p in root.iterdir()}
    (root / "manifest.json").write_text(json.dumps({"artifacts": files}))


def test_cash_control_audit_verifies_all_artifacts(tmp_path):
    audit_fixture(tmp_path)
    assert verify_audit(tmp_path)["portfolio_allocation_allowed"] is False
    (tmp_path / "uncertainty.csv").write_text("test\n2\n")
    with pytest.raises(ContractError):
        verify_audit(tmp_path)


def test_cash_control_cannot_authorize_live_allocations(tmp_path):
    audit_fixture(tmp_path, allowed=True)
    with pytest.raises(ContractError):
        verify_audit(tmp_path)


def test_cash_control_audit_cannot_omit_unflattering_artifacts(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"artifacts": {}}))
    with pytest.raises(ContractError):
        verify_audit(tmp_path)
