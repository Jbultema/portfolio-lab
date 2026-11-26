# Cross-bot combinations: findings, 2026-11-26

## Conclusion

The combinations buy some crisis protection, but they have not established a performance advantage over the unchanged i111-derived Trade Bot primary. Larger allocations to the weaker standalone bots substantially dilute growth. Event probes add some return versus leaving their sleeve in cash, but every tested event combination lagged its unchanged parent during the conditional 2025-plus evaluation. None passed the fixed-slate positive-excess significance check across the tested bootstrap block lengths.

This is not a conclusion that event information cannot work. It is a reason not to promote the current conditional sample or make Portfolio Lab the automatic allocation authority.

## What Was Integrated

- A native Fundamental Event Trader export of all 18 conditional candidate policies, with source-report, policy and data hashes. Portfolio Lab does not reimplement event signal generation.
- Cash conversion, executed net repurchases, working-capital repair, self-funded repurchases and liquidity repair. Horizon and trend-confirmation variants are correlated specifications, not independent discoveries.
- A separate conditional contract that the normal admitted-specialist loader rejects. No qualification gate was relaxed and no event allocation vote was added.
- Portfolio Lab's `Combination lab` workspace, linked from the Market Desk and current Event research page. Historical desk selections withhold the later research capture.
- Return/drawdown charts, paired uncertainty, crisis outcomes, matched cash and development-risk controls, fill/cost stresses, frozen-position shocks and modeled signal outages.
- Read-only numeric interpretation of each selected comparison, including whether protection actually improved and what the same budget in cash achieved.

The original `reports/latest.json`, selected allocator and daily allocation authority were not changed. New evidence is published through `reports/combination-stress/latest.json`.

## Scope And Execution

Core history: **5,258 actual NYSE sessions, 2006-01-03 through 2026-11-25**. Fresh local native exports from Trade Bot, Swing Trader and Rotation Trader; no new downloads. Exactly the same captured core instrument prices and cash-return history are retained for the unchanged Trade Bot comparison.

The Trade Bot primary is `i111_reentry_vol_target_fast_21d_no_trend_vol185_guard145`, not a substituted weaker strategy. The historical allocator uses the previously archived, audited Portfolio Lab selected targets; no winner was reselected here.

Close-known targets execute at the next, second or fifth observed close; subsequent returns accrue after the fill. Consolidated holdings are long-only, self-financing and cost-funded. Overlapping instruments are netted before costs. This is a common-clock close-fill test, not the original native next-open strategy backtest.

Primary execution: next close and **25 bps per traded side**. Other costs: 10 and 50 bps. The higher cost is material because Trade Bot turns over about 16.56 times portfolio value per year in this replay. These are assumed execution frictions, not measured realized account costs.

Registered before measurement: 23 core cases; 72 event combinations (18 policies x two parents x two sleeve sizes), plus 18 standalone probes, two parents and four parent-cash controls. With development-risk controls and execution cases: **1,173 paths**, plus **28 operational outage paths**. These are not 1,201 independent strategies. The prior native 520 conditional paths are not counted as new tests here.

Core risk-control scales are fitted through 2011, then frozen; their results start in later periods. Conditional risk controls use 2023-01-03 through 2024-06-28 development only. Event evaluation is 477 sessions from 2025-01-02 through 2026-11-25. No event history is padded into 2008, COVID or 2022.

## Long-History Results

Next-close execution, 25 bps per traded side:

| Portfolio | CAGR | Maximum drawdown | Sharpe |
|---|---:|---:|---:|
| Unchanged Trade Bot | 17.85% | -26.49% | 0.99 |
| 90% Trade / 10% Swing | 17.03% | -25.68% | 0.99 |
| 90% Trade / 10% Rotation | 16.52% | -24.98% | 0.98 |
| 80% Trade / 10% Swing / 10% Rotation | 15.74% | -23.87% | 0.98 |
| Equal three-bot budgets | 10.70% | -18.01% | 0.81 |
| Frozen Portfolio Lab allocator | 11.04% | -17.69% | 0.84 |
| 75% Trade / remainder cash | 13.93% | -20.37% | 1.02 |
| SPY buy and hold | 10.61% | -55.19% | 0.62 |
| QQQ buy and hold | 14.79% | -53.40% | 0.74 |

At the lighter **10-bps** assumption, unchanged Trade Bot is **20.82% / -25.02%**, the 80/10/10 blend **18.38% / -21.30%**, and frozen Portfolio Lab **13.00% / -16.60%**. Do not compare the 25-bps common-clock result directly with the older approximately 22% native backtest without accounting for both execution timing and costs.

No core combination improved both full-history CAGR and maximum drawdown versus unchanged Trade Bot. Some protection is genuine diversification: the full-history daily return correlations are Trade/Swing 0.55, Trade/Rotation 0.50 and Swing/Rotation 0.66. These correlations are not independence or proof of incremental skill.

### Does Protection Beat Just Holding Less Trade Bot?

Not consistently. In 2024 onward, frozen Portfolio Lab returned **20.39% CAGR / -10.81% drawdown**, while its development-risk-matched Trade Bot control returned **29.11% / -9.72%**. The 80/10/10 blend returned **30.54% / -11.50%**, versus its matched Trade control **32.21% / -10.87%**. Here, the simpler control won on both growth and drawdown.

The longer diagnostic windows are mixed: frozen Portfolio Lab's 2019-2023 drawdown was -14.97%, versus -21.06% for its risk-matched Trade control, but CAGR was only 10.87% versus 15.91%. It is a return/protection trade-off, not costless added alpha.

## Crisis And Concentration Tests

Primary-execution episode maximum drawdown, measured within each named episode:

| Episode | Trade Bot | 80/10/10 | Frozen Portfolio Lab |
|---|---:|---:|---:|
| GFC | -26.03% | -22.43% | -17.69% |
| China/oil scare | -13.12% | -11.55% | -8.11% |
| Q4 2018 | -10.91% | -10.71% | -12.55% |
| COVID | -15.93% | -15.84% | -14.97% |
| 2022 rates/inflation | -25.54% | -20.53% | -11.50% |
| 2025 episode | -11.57% | -10.27% | -7.77% |
| June 2026 onward, unfinished | -11.25% | -11.07% | -10.81% |

The strongest historical diversification benefit is 2022-like pressure, not every crash. COVID improvement is small; Q4 2018 is worse for the frozen allocator. There is no dot-com episode in the common three-bot history.

Current modeled holdings are important: Trade Bot is **38.54% invested**, frozen Portfolio Lab **75.66%**. In the instantaneous AI-35% scenario, losses are **-13.49% Trade / -11.38% Lab**. In the broad equity -20% scenario, losses are **-7.71% Trade / -15.13% Lab**. Less technology concentration is not the same as less total downside.

These shocks apply fixed modeled moves to the latest executed holdings. They are not probability estimates, forecasts, historical AI-crash evidence or simulations of either system reacting after the gap. Technology proxies include correlated sector ETFs; this is not precise constituent-level look-through attribution.

## Incremental Event Findings

Conditional 2025-plus, primary execution:

| Portfolio | CAGR | Maximum drawdown |
|---|---:|---:|
| Trade Bot | 28.51% | -11.57% |
| 75% Trade / cash sleeve | 22.28% | -8.65% |
| 75% Trade / 25% repurchases, 126 sessions | 25.53% | -11.62% |
| 75% Trade / 25% working-capital repair, 126 sessions | 24.50% | -10.10% |
| Frozen Portfolio Lab | 18.80% | -10.81% |
| 75% Lab / 25% repurchases, 126 sessions | 18.20% | -9.28% |

Repurchases are shown as an illustrative high-return result, **not a selected winner**. Added to Trade Bot at 25%, the sleeve adds 3.26 percentage points of CAGR versus the same budget left in cash, but costs 2.97 points of drawdown protection and still trails unchanged Trade Bot by 2.98 points of CAGR. This does not establish a new independent edge.

Across all 72 combinations, CAGR lagged its unchanged parent by **0.22 to 7.66 percentage points**, depending on parent, policy and sleeve size. Some policies reduced drawdown, but the growth sacrifice remained.

At 63-session bootstrap blocks, the repurchase combination's annual-log excess versus its development-risk-matched Trade control was +1.64%, with a 95% interval of **-1.32% to +4.09%**. Its within-slate adjusted p-value was 0.922. No positive result against risk-matched Trade survived the slate adjustment at any tested block length. Larger blocks produce a few positive marginal intervals but not stable, multiplicity-adjusted evidence.

Fundamental limitations remain: ten current survivors, unverified original-release vintages, limited event sample, no failed-security paths and previously inspected history. Accounting incomparability excludes JPM from the structural probes and retains its slot as cash. Nothing here qualifies a broad event specialist or exhausts the ten-family research program.

## Execution, Operations And Stability

- At **five-session fill / 50 bps**, full-history Trade Bot is **12.13% CAGR / -37.54% drawdown**; frozen Portfolio Lab **7.34% / -24.47%**. Protection remains, but growth and execution sensitivity are material.
- Modeled signal outages hold the last target for five sessions, then cash that sleeve through session 21. Across the predefined historical starts, the worst 63-session return effect was -2.70 percentage points for Trade alone, -2.20 for 80/10/10 and -1.02 for equal budgets. Outages also sometimes help by missing losses; that is not operational alpha or evidence the failure is safe.
- Post-run rolling diagnostics, 2012 onward, sample every 21 sessions. Frozen Portfolio Lab beats Trade Bot's return in **19.2% of 167 overlapping one-year windows** and **6.3% of 143 overlapping three-year windows**, while usually reducing drawdown. The windows overlap and are not independent trials.
- Omitting each named crisis's return dates does not reverse the core combinations' growth deficit. This is a frozen-return-path sensitivity check, not a rerun of executable strategies through an alternative market history.
- Event bootstrap sensitivity repeats 1,000 paired resamples at 21, 63 and 126-session blocks against own parent, same-parent cash and development-risk-matched Trade, under primary and joint-stress execution. There are **zero positive slate-adjusted p-values below 0.05** in these comparisons. This is not a whole-program multiple-testing correction or an untouched holdout.

## What To Do With This Evidence

Keep Trade Bot as the unchanged performance reference. Use Portfolio Lab to make return/protection trade-offs visible, rather than assuming three bots must beat one. Do not automatically replace it with equal allocations or the frozen allocator.

Do not optimize combination weights against these results. The next defensible research step is a frozen protection objective with an explicit acceptable growth cost, an exposure-matched control, crisis-specific failure criteria and future observations. For event research, the prerequisite remains broader point-in-time identities, delisted paths and original filing/release evidence. Additional threshold sweeps on the current survivor sample will not repair that gap.

## Evidence And Reproduction

- Primary immutable output: `reports/combination_stress_20261126_v3/`
- Supplementary sensitivity: `reports/combination_robustness_20261126_v2/`
- Native captured exports: `data/bundles/combination_stress_20261126/20261126T162244141447Z/`
- Conditional export: `data/conditional-events/20261126/`
- Browser evidence: `reports/browser-combination-20261126/`
- Earlier `_v1`/`_v2` primary draft directories have no measured results; the failed first supplementary run is unpublished. The dashboard points only to verified completed primary evidence.

Verify the completed primary study:

```sh
.venv/bin/python -m portfolio_lab.combination_stress verify \
  --output reports/combination_stress_20261126_v3
```

New experiments require a fresh output directory. Freeze before measurement with `combination_stress freeze --bundle ...` for each of the three native bundles, plus `--conditional-events`, `--archived-allocator` and `--output`. Run with `combination_stress run --output ... --publish reports/combination-stress/latest.json`. The runner refuses changed sources, modified financial code and reuse of a measured output. Supplementary checks use `python -m portfolio_lab.combination_robustness --source ... --output ...` and do not alter the primary evidence.

The local dashboard is at `http://[::1]:8513/?workspace=combination`. Desktop and mobile checks cover nonblank equity/drawdown traces, scope/window/parent/execution controls, download integrity and document overflow.
