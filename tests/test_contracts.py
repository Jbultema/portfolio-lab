import json

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.contracts import ContractError, digest, load_bundle, load_panel


def bundle(root, system="test", expert="test_primary"):
    root.mkdir()
    dates = pd.bdate_range("2020-01-01", periods=300)
    prices = pd.DataFrame(
        {"SPY": np.arange(300) + 100.0, "QQQ": np.arange(300) + 200.0}, index=dates
    )
    prices.to_parquet(root / "prices.parquet")
    (prices * 0 + 0.25).to_parquet(root / "weights.parquet")
    pd.DataFrame({"cash_return": 0.0001}, index=dates).to_parquet(root / "cash_returns.parquet")
    m = {
        "schema_version": 1,
        "system": system,
        "artifacts": {p.name: digest(p) for p in root.iterdir()},
        "experts": [
            {
                "id": expert,
                "role": "primary",
                "weights_file": "weights.parquet",
                "evaluation_start": str(dates[0].date()),
                "target_semantics": "close_known_risky_budgets",
                "evidence_status": "retrospective_research",
            }
        ],
        "native_execution": "test",
        "primary_expert": expert,
        "code_sha256": "test",
        "source_inputs": [],
        "data_end": str(dates[-1].date()),
        "authority": "research_only",
        "automatic_promotion_allowed": False,
    }
    (root / "manifest.json").write_text(json.dumps(m))
    return root


def test_valid_bundle(tmp_path):
    b = load_bundle(bundle(tmp_path / "bundle"))
    assert len(b.targets) == 1


def test_tampered_source_fails(tmp_path):
    root = bundle(tmp_path / "bundle")
    with (root / "weights.parquet").open("ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ContractError, match="integrity"):
        load_bundle(root)


@pytest.mark.parametrize(
    "change",
    [
        "authority",
        "unhashed_weights",
        "unhashed_prices",
        "unhashed_cash",
        "path_traversal",
        "duplicate_expert",
        "wrong_primary_role",
        "future_evaluation_start",
        "missing_evaluation_start",
    ],
)
def test_manifest_rejects_bad_contract(tmp_path, change):
    root = bundle(tmp_path / "bundle")
    p = root / "manifest.json"
    m = json.loads(p.read_text())
    if change == "authority":
        m["automatic_promotion_allowed"] = True
    elif change == "unhashed_weights":
        del m["artifacts"]["weights.parquet"]
    elif change == "unhashed_prices":
        del m["artifacts"]["prices.parquet"]
    elif change == "unhashed_cash":
        del m["artifacts"]["cash_returns.parquet"]
    elif change == "wrong_primary_role":
        m["experts"][0]["role"] = "rejected_diagnostic"
    elif change == "path_traversal":
        m["artifacts"]["../outside"] = "bad"
    elif change == "future_evaluation_start":
        m["experts"][0]["evaluation_start"] = "2100-01-01"
    elif change == "missing_evaluation_start":
        m["experts"][0]["evaluation_start"] = "NaT"
    else:
        m["experts"].append(m["experts"][0])
    p.write_text(json.dumps(m))
    with pytest.raises(ContractError):
        load_bundle(root)


def test_panel_rejects_duplicate_system(tmp_path):
    a = bundle(tmp_path / "a")
    b = bundle(tmp_path / "b", expert="other")
    with pytest.raises(ContractError, match="Duplicate specialist"):
        load_panel([a, b])


def test_panel_keeps_single_source_and_common_dates(tmp_path):
    a = bundle(tmp_path / "a", system="a", expert="a")
    b = bundle(tmp_path / "b", system="b", expert="b")
    prices, targets, cash, meta = load_panel([a, b])
    assert len(prices) == len(cash) == 300
    assert set(targets) == {"a", "b"}
    assert len(meta["sources"]) == 2
