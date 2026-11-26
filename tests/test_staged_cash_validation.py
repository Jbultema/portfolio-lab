import json

import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.staged_cash_validation import run


@pytest.mark.parametrize("kind,allowed", [("other", False), ("native_staged_cash_v1", True)])
def test_native_study_must_keep_its_explicit_research_boundary(tmp_path, kind, allowed):
    (tmp_path / "manifest.json").write_text(json.dumps({"kind": kind, "portfolio_allocation_allowed": allowed}))
    with pytest.raises(ContractError, match="unadmitted"):
        run(tmp_path, tmp_path / "output")


def test_corrupted_native_study_cannot_enter_common_replay(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"kind": "native_staged_cash_v1",
        "portfolio_allocation_allowed": False, "artifacts": {"prices.parquet": "0"*64}}))
    with pytest.raises(ContractError, match="integrity"):
        run(tmp_path, tmp_path / "output")
