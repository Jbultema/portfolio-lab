import json
import sys

import pytest

from portfolio_lab.cli import main
from portfolio_lab.contracts import ContractError


def test_forecast_cli_requires_a_price_manifest(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["portfolio-lab", "forecast-score", "--prices", "unverified.parquet"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_forecast_cli_checks_price_integrity_before_reading(monkeypatch, tmp_path):
    source = tmp_path / "prices.parquet"
    source.write_bytes(b"not-a-price-panel")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": {"prices.parquet": "0"*64}}))
    monkeypatch.setattr(sys, "argv", ["portfolio-lab", "forecast-score", "--prices", str(source), "--manifest", str(manifest)])
    with pytest.raises(ContractError, match="integrity"):
        main()
