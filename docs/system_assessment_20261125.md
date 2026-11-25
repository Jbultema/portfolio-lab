# Trading System Assessment: November 25, 2026

## Verdict

The five repositories form a credible research and decision-support platform, not a proven
22%-CAGR investment system. Software checks and evidence controls are substantially stronger
than the evidence for durable incremental alpha. Passing tests does not validate market
assumptions, remove the historical search burden, or authorize a trade.

Scope is the five personal Jbultema trading repositories only. Employer repositories are not
part of this cleanup. Existing operational and research work was preserved and consolidated;
private journals, local market data, and immutable experiment records were not deleted to
make Git look clean. Re-downloadable frontier inputs are now ignored rather than committed.

## Implementation And Quality

| Repository | Implemented role | Quality assessment | Binding limitation |
|---|---|---|---|
| Trade Bot | Strategic candidates, native controls, daily snapshots, cycle context, operational monitoring | Broadest implementation and test coverage; daily-job stages, locking, retention, and target/held distinctions are consolidated | Selected modern technology universe; target replay is not capture-timed execution evidence |
| Swing Trader | Monthly ETF reference plus independent stock-shadow entries/exits, immutable state, missed-session recovery and manual journal | Strong operational separation of frozen primary, diagnostics, data gates and lineage | Stock history/prospective evidence is still immature; monthly ETF primary should not be described as a fast crisis-timing system |
| Rotation Trader | Sector allocation/timing, finite hypothesis registry, regime and crisis diagnostics | Extensive landscape testing and explicit non-promotion; stricter execution input checks now expose rather than conceal bad data | No robust promoted winner; native execution still differs from common drift/self-financing accounting |
| Portfolio Lab | Hash-bound adapters, common accounting, fixed/risk-matched controls, meta allocation and prospective paper journal | Coherent cross-system comparison with zero trading authority | Young integration layer, no mature prospective track record, concentration is an instrument proxy rather than historical constituent lookthrough |
| Fundamental Event Trader | SEC provenance, acceptance-time facts, Form 4 parsing, dataset qualification, matched event studies | Deliberately fail-closed data and accounting safeguards | Data-qualified trading strategy does not yet exist; 48 hypotheses are registered, not tested on a qualified real dataset |

These are independent specialists, not five interchangeable momentum implementations.
Portfolio Lab owns common evaluation and portfolio budgets, not the native trading rules.
Fundamental Event Trader is not admitted as a fourth investable specialist.

## Iterative Improvements In This Pass

First pass: audit dirty source/dependency closures, isolate generated inputs, check personal
remotes and commit identity, run full lint/tests and dependency consistency checks.

Second pass: add adversarial checks and exercise actual archived-data integrations:

- Trade Bot detects revised overlap prices and fetches full affected history instead of
  splicing incompatible adjusted levels. A failed revision refresh leaves the cache unchanged.
  A fresh benchmark no longer hides another security's stale terminal prices.
- Post-risk target accounting records all-cash targets and rejects nonfinite, negative, and
  leveraged weights. Its UI/evidence label now says diagnostic replay, not prospective results.
  This corrects an authority claim; it does not turn the old ledger into a forward journal.
- Swing Trader requires explicit timezone offsets and actual exchange-session completion,
  including the publication buffer on early-close days. A later capture cannot legitimize a
  signal assigned to a holiday.
- Rotation Trader rejects dropped instruments, missing target sessions, nonfinite parameters,
  unpriced held intervals and missing cash returns. The archived-data rerun exposed a second
  bug: independent no-trade bands could create exposure above 100%. When partial application
  would over-invest, the engine now executes and costs the complete desired basket.
- All three exporters reject missing targets/cash rather than silently filling them, bind
  package/lock files, and retain native runtime provenance. Native champions are not reselected
  by exporting a bundle.
- Portfolio Lab uses actual exchange close timestamps for shadow execution, requires every
  observed exchange session, handles capture order independently of signal filenames, and
  lets the last capture before one execution close supersede earlier captures. It rejects
  invalid expiry, intraday session labels, invalid evaluation starts and nonfinite costs.
- Fundamental Event Trader rejects empty datasets, invalid identity intervals, nonfinite
  signals/prices and missing benchmark observations. Event paths require valid benchmark and
  security prices throughout, not only valid endpoints.
- A repeatable five-repository verifier writes JUnit counts, test/lint/dependency results,
  checkout SHAs and clean-tree state. Trade Bot now has a CI workflow too.

No threshold optimization or new strategy promotion was performed as part of cleanup.
Correctness-induced changes to native research results must be evaluated as corrections,
not advertised as newly discovered alpha.

## Performance Evidence

The common-clock comparison remains the appropriate cross-repository comparison: January 3,
2006 through November 23, 2026; next-session-close fills, drifting holdings and self-financing
10bp risky-notional costs. Selected modern stocks remain a survivorship/selection limitation.

| Common-clock path | CAGR | Maximum drawdown |
|---|---:|---:|
| Reconstructed Trade Bot primary | 20.81% | -25.02% |
| Swing Trader primary | 10.07% | -24.60% |
| Rotation Trader primary | 5.90% | -25.93% |
| Fixed equal blend | 12.50% | -17.09% |
| Fixed 75% Trade Bot blend | 17.73% | -20.70% |
| Training-selected conditional allocator | 12.93% | -16.60% |
| Development-risk-matched Trade Bot | 17.09% | -20.25% |

Diversification is real in this historical sample, but protection has a substantial return
cost. The sophisticated allocator has not established a compelling advantage over simple
controls. Do not mix these numbers with shorter-window native 22% claims or infer that they
are reliable future returns. The 2019+ periods have already been viewed in other research.

The earlier 167-variant orthogonal survey and 88-variant non-price survey are preserved in
Trade Bot. Some residual-momentum findings were promising standalone diagnostics, but their
regime-break behavior was poor. CFTC/options/margin families did not establish a robust
incremental edge. Revised macro data and approximate margin release dates remain limitations.
No extra repository or additional tuning erases that trial history.

## Remaining Gaps, In Priority Order

1. **Execution conformance:** Rotation Trader still resets target weights without charging
   all drift-induced rebalancing and uses an approximate cost convention. Common Portfolio
   Lab accounting avoids that defect, but native headlines need a separate engine correction
   and full rebaseline before performance qualification. Trade Bot's market-date replay also
   cannot stand in for capture-before-fill evidence or the configured execution lag.
2. **Prospective evidence:** preserve immutable captures, reconcile intended versus actually
   executed human trades, log missed sessions and accumulate compatible future observations.
   Initialization, backfill and matured historical returns are different evidence classes.
3. **Point-in-time opportunity set:** qualify historical membership, delisted securities,
   ticker/issuer identity, original filings and terminal prices. A selected current technology
   list is not a fair test of finding the next leadership cohort.
4. **Cycle Tracker consistency:** the transition map has no direct post-unwind-to-unwind
   edge, although the stress multiplier handles that pair. Multiplication cannot overcome a
   zero transition prior. Audit path stickiness and raw-versus-smoothed disagreement on
   recurrence episodes before any calibration change. Cycle Tracker remains contextual.
5. **Portfolio realism:** obtain point-in-time ETF holdings for constituent overlap; add
   account restrictions, stable-value transfer rules, taxes and human execution delay before
   translating research budgets into account-specific recommendations.
6. **Data-qualified non-price alpha:** the preserved SEC access probe returned HTTP 403 and
   no historical equity panel has qualified. Complete source qualification and content-defined
   events before a new real-data event study. Do not backfill current winners as a substitute.
7. **Maintainability:** some research/dashboard modules are large, type checking is not a
   system-wide passing gate, and duplicate native accounting remains. Calendar/NumPy warnings
   are dependency-maintenance debt. Source-wide provenance is conservative but means UI-only
   changes invalidate research identity; do not bypass that gate to avoid rerunning evidence.

## Reproduce Verification

From Portfolio Lab, after installing each repository's isolated environment:

```sh
.venv/bin/python scripts/verify_workspace.py --repos-root .. --output reports/verification/UNIQUE
.venv/bin/portfolio-lab daily --repos-root .. --output reports/UNIQUE
.venv/bin/portfolio-lab audit --report reports/UNIQUE
.venv/bin/python scripts/check_dashboard.py --url 'http://[::1]:8512' --output reports/browser_UNIQUE
```

The verifier does not fetch Git, download market data, select a new native champion, start
orders or assert remote CI passed. Its JSON explicitly distinguishes local software checks,
clean checkout state and remote-CI verification. Local datasets remain required to reproduce
the archived-data research; a fresh source clone alone is sufficient for the offline unit suite.
