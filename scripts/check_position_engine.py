import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from portfolio_lab.engine import replay


@pytest.mark.parametrize("cost", [0, 10, 25, 100])
@pytest.mark.parametrize("lag", [1, 3])
def test_position_unit_ledger_matches_common_funded_engine(cost, lag):
    # Cross-repo conformance is explicit, separate from each repository's isolated CI.
    file = Path.home() / "repos/position-bot/src/position_bot/engine.py"
    assert file.is_file(), "Cross-repo release requires the independent Position Bot ledger"
    import sys

    spec = importlib.util.spec_from_file_location("position_ledger_parity", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    rng = np.random.default_rng(1337)
    days = pd.date_range("2020-01-01", periods=180)
    p = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, .01, (180, 3)), axis=0)), index=days, columns=list("ABC"))
    values = rng.dirichlet([1, 1, 1, 1], size=180)[:, :3]
    for i in range(1, len(values)):
        if i % 7:
            values[i] = values[i - 1]
    w = pd.DataFrame(values, index=days, columns=p.columns)
    common = replay(p, w, pd.Series(0., index=days), cost_bps=cost, lag=lag)
    native = module.replay(p, w, cost_bps=cost, lag=lag)
    np.testing.assert_allclose(common.returns, native.returns, atol=1e-11, rtol=0)
    np.testing.assert_allclose(common.weights, native.weights, atol=1e-11, rtol=0)
