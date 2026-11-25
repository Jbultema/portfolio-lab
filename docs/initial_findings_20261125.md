# Initial Evidence: November 25, 2026

Status: retrospective research and prospective signal initialization only. No promotion.

The release replay uses common observed sessions from January 3, 2006 through November 23,
2026. Trade Bot and Rotation Trader inputs extend through November 24; Swing Trader ends
November 23, so the common comparison intentionally stops there. There is no fabricated
Swing Trader return for the missing shared session.

| Common-clock portfolio | CAGR | Maximum drawdown |
|---|---:|---:|
| Reconstructed Trade Bot primary | 20.81% | -25.02% |
| Swing Trader primary | 10.07% | -24.60% |
| Rotation Trader primary | 5.90% | -25.93% |
| Fixed equal blend | 12.50% | -17.09% |
| Fixed 75% Trade Bot, 12.5% each other specialist | 17.73% | -20.70% |
| Fixed 90% Trade Bot, 5% each other specialist | 19.57% | -22.73% |
| Training-selected conditional allocator | 12.93% | -16.60% |
| Development-volatility-scaled Trade Bot | 17.09% | -20.25% |

These are not the native next-open or lagged-close headline metrics. Signals fill at the
next observed close, holdings drift, and 10bp risky-notional trading costs reduce NAV.

## What the evidence supports

- The specialists are not exact duplicates: primary return correlations range from 0.50 to
  0.66, while descriptive market-beta residual correlations range from 0.27 to 0.52.
- Diversification reduces drawdown but has a substantial historical opportunity cost versus
  the selected technology universe. It is not free protection or proof of a new alpha source.
- Conditional allocation adds only a small gain over the fixed equal blend. Relative annual
  log return was -0.02% in 2019-2023 and +1.02% in 2024 onward. The latter pointwise block
  interval is positive, but it is not lifetime-trial-adjusted or evidence of reliable future alpha.
- Of 39 allocator specifications, 27 produce distinct paths. The within-family PBO diagnostic
  is 8.6%; older research trials are incompletely enumerated, so this cannot clear promotion.
- The current combined study cannot establish performance through the full dot-com crash:
  the common technology history starts too late and its universe is selected retrospectively.

Three simple fixed Trade Bot-heavy blend controls were added after the initial diagnostic
read and are labeled accordingly. They are comparisons, not blind discoveries. Followups and
final allocator selection use development/validation through 2018; all later periods have
already been observed in prior work and remain diagnostics.

## Operational conclusions

Native scheduling now avoids treating a partial file tail as month/week end. Planned regular
exchange holidays are used without anticipating future emergency closures. Frozen Rotation
Trader specifications are rebuilt instead of silently reusing outdated tail targets.

The full export/research/audit/shadow pipeline passes. A shadow signal is not an executed
portfolio: initial evaluation correctly returns `pending_future_execution`. No historical
fill is backdated to the source signal date. Desktop/mobile Chrome checks cover rendered
performance charts and every evidence tab.

Native validation also completed independently: all 4,400 registered Rotation Trader variants
were rerun under corrected scheduling, and the same frozen primary was selected with no
promotion. Its full-history native result remains 6.50% CAGR and -27.26% drawdown. Swing
Trader's nine native comparisons were regenerated separately; its frozen monthly primary
remains 11.35% CAGR and -25.11% drawdown. These native windows and execution conventions
differ from the common-clock table above and must not be mixed with it.

Local test suites passed: Trade Bot 759, Swing Trader 198, Rotation Trader 39, Portfolio Lab 59,
and Fundamental Event Trader 38. CI workflows are configured in the new repos; local passing
tests are not a claim that remote CI has run.

The dashboard is research-only and remains `NO ACTION`. On the inspected Mac, IPv4 loopback
127.0.0.1 is not configured; the dashboard is bound only to IPv6 loopback at
`http://[::1]:8512`. No operating-system network settings were changed.

Detailed local evidence: `reports/release_20261125/`, including 64 hash-bound artifacts.
Manifest SHA256: `3a6b49297ddf03d91afd48f3275f9ee78fbaf7850ee00103415254c51498766b`.

## Next Evidence Gates

1. Accumulate compatible prospective signals and actual future marks; do not tune against them daily.
2. Add account-specific execution constraints and point-in-time ETF holdings before claiming exact
   constituent concentration or cross-account netting savings.
3. Qualify an original-vintage fundamental/event dataset including delisted identities. The current
   official SEC endpoint probe is HTTP 403 and no fourth specialist has been admitted.

## Cleanup Validation

The subsequent cleanup release in `reports/cleanup_release_20261125/` binds 64 artifacts;
manifest SHA256 is `6afc630e8ef7745eb50e0edd0c7fd76e84ddaa7a5a9bc8243644b385ed1a61c0`.
All 62 path-metric rows exactly match the prior release above. The expanded source/contract
checks therefore do not change the common-clock performance conclusions. Its shadow lineage
is new because implementation identity changed; evaluation correctly remains
`pending_future_execution`, not a historical performance record.

The [system assessment](system_assessment_20261125.md) records the cleanup improvements and
remaining gaps, including native Rotation Trader accounting and the no-trade-band correction.
Final local test counts and checkout identities are produced by `scripts/verify_workspace.py`.
