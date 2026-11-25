# Portfolio Lab

Personal, research-only evaluation and allocation across independent trading specialists.
Long-only ordinary securities and cash; all execution is human-controlled. No broker connection.

## Ownership

- Trade Bot: strategic portfolio candidates, native protection and recovery, cycle context.
- Swing Trader: entries, holding rules and exits; its frozen ETF primary is monthly momentum.
- Rotation Trader: sector leadership transitions and allocation/timing specialists.
- Fundamental Event Trader: point-in-time company filings and non-price event research; currently gated.
- Portfolio Lab: comparison, cross-specialist budgets, consolidated exposures, portfolio constraints and governance.

Each specialist owns its native rules. Portfolio Lab never forces a specialist to undo an exit.
There is one portfolio-level risk ceiling, not repeated multiplication of each specialist's haircut.
No project imports strategy code from another repository. Integration is through hash-bound files.

## Run

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/portfolio-lab daily --repos-root ..
.venv/bin/streamlit run src/portfolio_lab/dashboard.py --server.port 8512
```

`daily` exports the three existing specialists using their own isolated interpreters, freezes
the allocator slate, performs research, audits artifacts, and writes an immutable shadow signal.
It needs local sibling checkouts with their archived datasets; it does not silently download
different data or rerun their historical champion selection. Every run has a unique output directory.

Individual steps:

```sh
.venv/bin/portfolio-lab export-all --repos-root ..
.venv/bin/portfolio-lab research --bundle data/bundles/RUN/trade-bot --bundle data/bundles/RUN/swing-trader --bundle data/bundles/RUN/rotation-trader
.venv/bin/portfolio-lab audit --report reports/runs/RUN
.venv/bin/portfolio-lab record-shadow --report reports/runs/RUN
.venv/bin/portfolio-lab evaluate-shadow --journal data/shadow/LINEAGE --bundle data/bundles/RUN/trade-bot --bundle data/bundles/RUN/swing-trader --bundle data/bundles/RUN/rotation-trader
```

## Evidence Contract

See [the protocol](docs/protocol.md) and [specialist schema](contracts/specialist-v1.schema.json).

Native results and common-clock results are different products. Common replay uses close-known
targets filled at the next observed session close, with returns only after that fill, holdings
drift, and trading costs funded from NAV. It cannot reproduce next-open gap execution. Cash earns
the captured lagged Treasury-yield series, selected consistently across specialists.

The currently available common history starts in 2006, so the combined study cannot establish
protection during the full dot-com collapse. Technology targets come from a selected modern-stock
universe, not a survivor-free historical opportunity set. Later periods have already been seen in
earlier research and are never relabeled pristine out of sample.

Research includes fixed blends, inverse-volatility budgets, conditional and trailing utilities,
two followup rounds, concentration/protection combinations, risk-matched controls, annual outer
selection, tail overlap, crisis episodes, block bootstrap, deduplicated PBO, and delay/cost stresses.
The experiment roster is finite and saved before each round. No inference or promotion follows
merely from positive full-history CAGR or one pointwise confidence interval.

Shadow signals cannot authorize trading. Their evaluator requires future captured-market
observations, never backdates a fill to the historical signal date, and expires an unrefreshed
paper target to cash after five executed sessions. Different policy/code lineages are not spliced.

## Tests

The cross-repository assessment is in [system assessment](docs/system_assessment_20261125.md).

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/python scripts/verify_workspace.py --repos-root .. --output reports/verification/UNIQUE
```

No paid data, options, derivatives, leverage, broker integration, or automated order placement.
