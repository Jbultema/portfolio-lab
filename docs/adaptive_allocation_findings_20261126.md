# Adaptive allocation research: 2026-11-26

## Decision

Keep the native strategies and daily allocator unchanged. This iteration finds **no reliable incremental growth from routing capital between the current bots**. It does identify a narrower risk-sizing lead: some rules work better when the diverted sleeve is left in cash instead of invested in another bot. That lead is not yet qualified for deployment.

The completed study adds **46 policy specifications across eight initial families and three rounds**, evaluated through **1,428 portfolio/control/execution paths**. These are not 1,428 independent hypotheses. Post-hoc cash-control diagnostics add no new rules or replay paths. They inspect controls already included in the frozen experiment.

At next-close execution and 25 bps per traded side, **zero of 46 raw routers beat Trade Bot's CAGR from 2019 onward**, and none of the 32 initial rules beats it over the full common history. No tested router/control comparison has positive excess passing both a positive 95% lower bound and the within-slate adjustment. The additional cash-control audit also finds no such adjusted positive result.

## Comparable Results

Common later window: **2019-01-01 through 2026-11-25**, next-close fills, 25 bps per traded side, funded costs and consolidated overlapping holdings.

| Approach | CAGR | Maximum drawdown |
|---|---:|---:|
| Unchanged Trade Bot | 24.96% | -25.97% |
| Trade Bot at 90% of its native risky targets | 22.73% | -23.50% |
| Highest-CAGR new raw router: cash redeployment, cost gate, 21-session hold | 24.82% | -26.63% |
| Current-close context, 21-session hold, no cost gate | 24.24% | -21.66% |
| The same context rule, diverted sleeve in cash | 24.78% | -21.66% |
| 126-session residual-alpha router, 50% alternative ceiling | 22.54% | -29.86% |
| The same residual-alpha rule, diverted sleeve in cash | 25.81% | -23.87% |
| 252-session residual-alpha rule, diverted sleeve in cash | 25.38% | -21.66% |
| SPY buy and hold | 15.96% | -33.72% |
| QQQ buy and hold | 20.35% | -35.12% |

These illustrative cash cases were noticed by examining controls after measurement. They are not a hindsight-selected live recommendation.

Full common history: **2006-01-03 through 2026-11-25**, same execution and cost assumptions:

| Approach available over the full window | CAGR | Maximum drawdown |
|---|---:|---:|
| Unchanged Trade Bot | 17.85% | -26.49% |
| Best full-history initial raw router: 63-session cash redeployment, 25% ceiling | 17.59% | -26.58% |
| 126-session residual-alpha cash control, 50% throttle | 17.60% | -23.87% |
| 252-session residual-alpha cash control, 50% throttle | 17.81% | -27.72% |
| SPY buy and hold | 10.61% | -55.19% |
| QQQ buy and hold | 14.79% | -53.40% |

The 126-session cash control trades about 0.25 percentage points of full-history CAGR for 2.62 points of drawdown reduction. The 252-session control does not improve either full-history growth or maximum drawdown. Its attractive later-period result is not a durable full-history dominance result.

The original native next-open approximately 22% strategy result is a different execution product. This common-clock study does not reproduce it or replace it with the higher 2019-onward CAGR.

## What Was Tested

Each initial family has four configurations: two clocks/horizons/regularization strengths and 25%/50% alternative ceilings.

| Initial family | Mechanism | Median 2019+ raw CAGR |
|---|---|---:|
| Faster context | Paired current-close versus prior-close leadership/rebound observations | 22.88% |
| Risk-normalized skill | Choose using expert excess return per unit of realized risk | 21.75% |
| Residual alpha | Shrunk rolling alpha after SPY and QQQ-minus-SPY factors | 23.71% |
| Adaptive horizon | Switch 21/42-session versus 126-session evidence when volatility or leadership changes | 22.15% |
| Current-holdings quality | Score the securities each bot currently wants, not just its long-run CAGR | 20.79% |
| Cash redeployment | Retain Trade positions and invest part of unused cash in a qualifying specialist | 24.39% |
| Defensive opportunity | Require Trade to be defensive plus positive breadth, trend, holdings quality and better specialist drawdown health | 22.41% |
| Online context | Rolling ridge model with only matured post-fill outcomes and uncertainty haircuts | 23.21% |

All families use the same underlying captured price information. New mechanisms are not new independent information sources. The online model was not an improvement: its four raw later CAGRs range from 21.68% to 24.04%, with drawdowns from -27.73% to -30.59%.

### Frozen Research Chronology

1. Thirty-two initial candidates. Parents advance by median family score over **2012-2015**, then the best member within each selected family. Fast context and cash redeployment advance even though both family medians are negative. The separate minimum-quality gate retains Trade Bot.
2. Eight follow-ups: confirmation, 5/21-session holds and round-trip cost gating, available only from **2016**. The **2016-2018** selection window advances residual alpha and cash redeployment for diagnostic combinations. Their median scores are near zero; the minimum-quality gate again retains Trade Bot.
3. Six combinations, available only from **2019**: union, agreement, rolling parent choice, stress scaling, defensive-opportunity gating and trend veto.

No later-period result selects these parents. However, this history was already inspected in earlier research, so this chronology is not an untouched holdout and cannot erase whole-program selection bias. The pre-2019 gated research choice remains **unchanged Trade Bot**.

## Is It Selection Skill Or More Risk?

Every candidate has five paths:

1. Raw router.
2. Router capped at Trade Bot's close-known gross invested target.
3. Trade Bot scaled to match that capped target.
4. The candidate's Trade sleeve alone, with alternative sleeves in cash.
5. Trade Bot plus SPY at the same gross invested target as the raw router, or Trade scaled down when the router invests less.

These match gross targets, not beta or exact daily realized exposure. Holdings can drift differently between rebalances.

The best raw cash-redeployment follow-up earns 24.82%, versus 24.96% for leaving its extra investment in cash. Its capped portfolio earns 24.28%, versus 24.96% for matched-target Trade. It beats its SPY-surplus substitute slightly, but not the unchanged cash decision. This is not a useful capital-allocation discovery.

For the 126-session residual-alpha rule, funding the selected alternative reduces later CAGR from the cash control's **25.81% to 22.54%** and worsens drawdown from **-23.87% to -29.86%**. The information may be more useful as a warning about Trade risk than as proof that another bot deserves the money.

Cash-redeployment expert multipliers can sum above one because the underlying bots hold cash. Actual risky-asset targets always total at most one. The dashboard plots **risky-asset contributions after internal cash**, not these notional multipliers. Mandatory daily safety projection cannot be blocked by a hold period or cost gate.

## Adversarial Checks

Six predeclared scenarios separate cost and delay: next close at 10/25/50 bps; second close at 25 bps; fifth close at 25/50 bps. Some raw policies beat Trade in individual cheaper or delayed cases, but no raw policy beats it in all six. The cost-gated 21-session context rule, for example, gains under delayed fills but loses growth and drawdown at primary execution. A favorable fill delay is not reliable alpha.

The 252-session cash control preserves a small later growth advantage across all six cases. Under joint stress it earns 20.32% CAGR / -21.24% drawdown versus Trade's 20.20% / -24.05%. Nevertheless, its full-history and crisis-omission failures remain.

The post-hoc cash audit bootstraps all eligible controls together, using 1,000 paired resamples at 21/63/126-session block lengths. For the 126-session, 50% cash rule at the primary case:

- Later annual log excess: **+0.68%**, 63-session-block 95% interval **-1.12% to +2.40%**, within-slate adjusted p-value **1.0**.
- Full-history annual log excess: **-0.21%**, interval **-1.90% to +1.40%**.
- It exceeds Trade by more than 10 bps annualized in **43.3% of overlapping one-year windows** and **78.4% of overlapping three-year windows** after 2019. These windows are not independent tests; many one-year windows are effectively flat.
- Excluding calendar **2020** turns its later annual log excess negative, to **-0.23%**. Omitting 2022 does not destroy this particular rule's lead.
- The 252-session rule has the opposite concentration issue: excluding calendar **2022** turns its later annual log excess negative, to **-0.67%**.

Episode omissions stitch together non-contiguous returns. They are attribution diagnostics, not tradable historical strategies. No comparison passes the adjusted positive-excess test. Adjustments cover this slate only, not all prior research or the post-hoc decision to investigate cash controls.

## Recent Transition

Unfinished period: **2026-06-01 through 2026-11-25**. Report total return, not an annualized short-window forecast.

| Approach | Total return | Maximum drawdown |
|---|---:|---:|
| Unchanged Trade Bot | -3.85% | -11.25% |
| 126-session residual-alpha cash control | -4.14% | -10.74% |
| 252-session residual-alpha cash control | -3.85% | -11.25% |
| 21-session context raw router, no cost gate | -2.86% | -10.95% |
| Same context rule, alternatives left in cash | -3.30% | -7.44% |

Some rules reduce damage in this window, but the residual-alpha lead is not a newly validated AI-crash detector. One version is inactive here and another slightly trails Trade's return. Conditional protection observed in a reconstructed, unfinished episode is not current trading authorization.

## Implementation And Limits

- Separate modules: `adaptive_allocation.py`, `adaptive_research.py`, `adaptive_diagnostics.py`, `adaptive_cash_audit.py`.
- Dashboard: **Adaptive allocation**, or `?workspace=adaptive`; pointer `reports/adaptive-allocation/latest.json`. Earlier Dynamic allocation and the daily allocator pointers are unchanged.
- All 466 online fits have matured labels. Features at close s predict relative log returns s+2 through s+6 after a next-close fill; a fit at t cannot use a training row whose label ends after t. Monthly fitting, rolling training windows, fit-local transformations and uncertainty deductions are fixed before measurement.
- Nine direct baseline reconciliation checks match previous Trade/Swing/Rotation daily return values and dates exactly across the shared execution cases. Only the date-index name metadata differs.
- This study uses 5,258 common NYSE sessions and the previously captured native strategies, including the i111-derived Trade primary. No official news/macro release history or new price vintage was added. Conditional event probes remain unadmitted and are not treated as a fourth qualified bot.
- Source universes remain modern and selected, not survivorship-free. Native strategy selection was previously researched. This study is conditional on those experts and does not establish their future reliability.
- Common history starts in 2006, so there is no full dot-com-collapse validation. Static AI-gap shocks are not probabilities or simulations of successful reactive protection.
- Fixed shadow expert outcomes remain next-close/25-bps when execution is stressed. This isolates execution sensitivity; it is not a simulator that retrains signals on the account's delayed realized fills.
- No broker, leverage, derivatives, personal holdings, external narration or automatic promotion was introduced.

## Reproduce

Primary study: `reports/adaptive_allocation_20261126_v2`.
Manifest SHA256: `d2f0d7b0d90869d276e98493f9c57006ba3391579a0ed0016a8a92ea6bbddb2c`.

```sh
.venv/bin/python -m portfolio_lab.adaptive_research verify --output reports/adaptive_allocation_20261126_v2
.venv/bin/python -m portfolio_lab.adaptive_research freeze --source reports/dynamic_allocation_20261126 --output reports/adaptive_allocation_UNIQUE
.venv/bin/python -m portfolio_lab.adaptive_research run --output reports/adaptive_allocation_UNIQUE
.venv/bin/python -m portfolio_lab.adaptive_diagnostics --source reports/adaptive_allocation_20261126_v2 --output reports/adaptive_diagnostics_UNIQUE
.venv/bin/python -m portfolio_lab.adaptive_cash_audit --source reports/adaptive_allocation_20261126_v2 --output reports/adaptive_cash_audit_UNIQUE
```

Completed descriptive audits: `reports/adaptive_diagnostics_20261126` and `reports/adaptive_cash_audit_20261126_v2`. An earlier interrupted study is explicitly marked incomplete and excluded from all completed trial counts. The restart changed import formatting only, not the protocol's hypotheses, thresholds, windows or selection rules.

## Next Research

Treat residual-alpha cash throttling as a **native risk-sizing research lead**, not a reason to allocate to weak specialists. A useful next study would predeclare when to reduce and restore Trade risk, test that mechanism against simpler risk controls, and retain a genuinely prospective shadow period. It must explain the 2012-2015 growth penalty and the episode concentration before any promotion.

For cross-bot routing, improving the alternatives' standalone evidence and obtaining qualified, genuinely different event information is more promising than further fine-tuning the same price-only family thresholds. This iteration does not show that dynamic allocation is impossible; it shows that the current alternatives have not earned their proposed capital under these tests.

## Validation

Portfolio Lab: **250 tests passed**, Ruff passed, and `git diff --check` passed. Real Chrome checks pass on desktop (1440x1000) and mobile (390x844): charts are nonblank, controls and CSV downloads work, no application/browser exceptions appear, and the document has no horizontal overflow. Both the new adaptive workspace and the previous dynamic/event workspace were checked on the fresh process.

Fresh local dashboard: `http://[::1]:8514/?workspace=adaptive`. The older server was preserved; it had cached an earlier Python module signature and is not the accepted process for this release. Browser evidence is under `reports/browser-adaptive-20261126` and `reports/browser-dynamic-20261126`.
