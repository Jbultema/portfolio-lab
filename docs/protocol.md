# Research Protocol And Decision Authority

## Frozen comparison

The first registered allocator slate contains 15 specifications. Four lookback/shrinkage
combinations are registered per estimator family. Three followups per family are added in
round two and again in round three; six protection/concentration combinations form round four.
That is 39 allocator specifications, not 39 independent strategies. Equivalent paths are
deduplicated for the within-family PBO diagnostic. Standalone specialists and controls are
reported separately. Prior research trials remain part of the evidence history.

Development ends in 2011 and validation ends in 2018. Followups and final selection only read
these two periods. Later 2019-2023 and 2024+ periods are diagnostics, not untouched holdouts.
Annual outer selection begins in 2019 with a 21-observed-session boundary gap. It may assess
only models already in the slate; none of this provides a new blind holdout after historical
model families have been designed. A truly new policy requires a new prospective lineage.

The conditional allocator estimates realized one-session utilities conditional on the state
known before each historical return interval. It uses no un-matured forward labels. Conditional
means shrink toward unconditional means, budgets shrink toward equal weights, and per-change
budget movement is bounded. Low evidence starts from equal weights and an uncertain regime.

## Mandatory controls

- Each frozen specialist on the same common sessions.
- SPY and QQQ buy and hold, cash, static 50% and 75% Trade Bot sleeves.
- Fixed equal blend and inverse-volatility blending without a regime classifier.
- Development-volatility-scaled Trade Bot; matching is approximate after drift and costs.
- Sector timing and recovery challengers selected only on development/validation.
- Costs at 10, 25 and 50 basis points per risky traded notional; one, two and four session lags.
- Crisis windows including recovery, conditional normal/transition/stress results, and longest
  underwater spells. A shallower decline does not imply a faster recovery.

## Data and execution

One captured adjusted-close series is selected per security. Different adjustment levels are
not spliced. Material cross-source return differences fail closed. Common dates are the
intersection of complete observed sessions; no weekday calendar, synthetic holidays, missing
specialist zero returns, backfilled IPO prices, or fabricated terminal values are allowed.

Targets are risky budgets at the completed close. Cash is implicit. A new target fills no
earlier than the next observed close. Previous holdings earn the intervening return; the
new holding first earns returns after its fill. Holdings drift when targets do not change.
Costs reduce actual investable NAV, including fully invested purchases. Trading opposite
instructions from different sleeves is netted at consolidated-security level within this one
hypothetical account. Cross-account netting is not assumed, and account-specific fees/taxes
must be added before personal execution planning.

Native engine differences are disclosed rather than averaged away. Reconstructed Trade Bot
controls are causal but re-clocked, not exact native returns. The common-close replay cannot
establish an edge specifically dependent on next-open or intraday execution.

## Orthogonality

Compare return correlation, market-tail correlation, market-beta residual correlation,
security-weight overlap and simultaneous losses. These are descriptive, not proof of
independence. ETF constituent overlap and exact sector exposures need point-in-time holdings
data. Current technology caps are conservative instrument proxies, not full lookthrough.

New data sources do not qualify a new specialist automatically. Fundamental Event Trader
remains excluded until issuer identity, original publication availability, delisted coverage
and price quality are verified. Filing counts and amended financials are not substitutes for
content or point-in-time fundamental changes.

## Promotion

No automatic promotion exists. A model must beat fixed/risk-matched controls after costs,
survive regime and execution perturbations, and accumulate compatible prospective evidence.
The old trial history is incompletely enumerated, so there is no selection-adjusted significance
claim. A pointwise bootstrap interval is not a family-wide or lifetime error guarantee.

Research identity, source hashes, frozen selections, execution convention, data dates and
limitations accompany every report. Artifact mutation or code drift makes the audit fail closed.
The user is the only execution authority. No command connects to a broker.
