# Position Bot And The Daily Control Room

## Conclusion

Position Bot is implemented as an independent public-positioning research and
monitoring specialist and connected to Portfolio Lab. It is NOT admitted as an
allocation engine: the tested strategies do not establish incremental net alpha,
and original historical release timestamps/vintages are not fully qualified.
The operating Trade Bot primary and portfolio allocator remain unchanged.

## Research Actually Executed

Eight ETF mappings, nine positioning mechanisms, two lookbacks and two portfolio
breadths produce 36 rules. Twelve registered pairs bring the main slate to 48.
Four benchmarks, three costs, two fill lags and two release-delay scenarios
produce 624 main execution paths. Six turnover/review-clock follow-ups add 36
paths. This is 54 rule/implementation hypotheses, not 660 independent discoveries.
Corrective source-frozen reruns are not additional hypotheses.

Development is 2012-2016, validation 2017-2019, test 2020-2022, and later diagnostics
2023 onward. Earlier research already inspected these periods; no new untouched
holdout is claimed. Selection does not read test/later performance. Independent
share-unit and common funded ledgers reconcile across randomized holdings,
0/10/25/100bp costs and one/three-session delays.

At 25bp and next-close execution, native selected weekly research was roughly
**-0.44% CAGR / -35.03% max DD**, versus SPY **14.38% / -33.72%** and QQQ
**18.75% / -35.12%**, January 2012-November 25, 2026. Native cash earns zero.
The 21-session review follow-up improves this to **3.80% / -18.44%**, and the
42-session follow-up to **3.54% / -18.35%**. Slower trading reduces damage from
turnover, not proof of a compelling new positioning advantage. These follow-ups
do not silently replace the research rule or confer admission.

Zero positive slate-adjusted native excess lower bounds were found against the
price-only control across 21/63/126-session block tests. The slate correction is
not a correction for every experiment performed across the entire trading program.

## Portfolio Integration

Twelve standalone/blend/cash/gate portfolios plus four development-fitted risk
controls produce 96 common-clock execution paths. Same period, 25bp per traded
side, funded drift, common captured cash yield:

| Portfolio | CAGR | Maximum Drawdown |
|---|---:|---:|
| Trade primary | 20.81% | -25.97% |
| 90% Trade / 10% Position | 18.60% | -25.12% |
| 90% Trade / 10% cash | 18.92% | -23.50% |
| 75% Trade / 25% Position | 15.33% | -24.10% |
| 75% Trade / 25% cash | 16.06% | -19.67% |
| Position-confirmed Trade gate | 14.44% | -16.07% |

The fixed blends are inferior to corresponding cash controls in this full sample.
The confirmation gate reduces drawdown substantially but surrenders growth; it
has not earned authority over Trade's risk budget. The 20.81% figure differs from
the prior 2008+ comparison because this study starts in 2012; it is not a newly
improved primary, a forward forecast, or an actual-account track record.

## Daily Use

Portfolio Lab now owns the common button, background jobs, coordinated scheduler,
report publication and deep-dive links. Position data appears as separately labeled
current context and in the downloadable daily report, never retroactively injected
into historical fact packs or counted as another independent market vote.
Event's verified blocked readiness is likewise an observed data gate, not an
operational crash or a market signal. No cloud narrator or private holdings are sent.

The first live trial revealed Yahoo/DNS/missing-column failures and correctly
retained the previous complete report. A separate current-session cached-data
workflow passed all five native stages and atomic synchronized report publication.
The old report-only scheduler was unloaded to remove its publication race.
Final live-refresh, scheduler and browser receipts are in the local release evidence.

## Boundaries

This is usable conditional research/monitoring software, not a newly proven
investment strategy. Public source reliability, actual availability, revised
classifications, ETF/futures basis and survivor selection remain distinct concerns.
See `docs/daily_operations.md` and Position Bot's README for commands and gates.
Source changes are published in personal repositories/review branches; no existing
bot primary was promoted or main branch silently merged.
