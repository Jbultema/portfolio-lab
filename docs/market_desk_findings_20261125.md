# Market Desk: 40-Session Findings

Evidence captured November 25, 2026. Session window: September 30-November 24,
2026, the last 40 completed NYSE sessions at execution time. These are historical
reconstructions, not 40 previously captured forecasts or a new investment policy.

Local archive: `reports/market_desk_final_v2_20261125`.
Manifest SHA-256: `0b021565bf4b4ab8e2ea33ed9c80500ee107704fa33382445d0ee9b34d709315`.
The archive binds 131 artifacts, including all 40 fact packs and briefs, native
operating context, outcomes, timeline and a generated readout. Future daily runs
have separate immutable directories and timestamps.

## What the Market Evidence Says

At the November 24 close:

- QQQ was 16.0% below its trailing 63-session closing high.
- SPY had lost 6.1% over 21 sessions and was 1.6% below its 200-session average.
- Five of nine stable sector ETFs were above their own 200-session averages:
  55.6%, down 11.1 percentage points from 21 sessions earlier.
- Relative to SPY over 21 sessions, staples led by 10.5 percentage points,
  healthcare by 9.1, and consumer discretionary by 9.1. Technology lagged by 9.6
  points and energy by 7.1. Relative outperformance is not always a positive return.

This supports a technology-led stress interpretation with uneven participation,
not a claim that every sector is collapsing or that an AI-specific cause is proven.

## The Bots Are Not Saying the Same Thing

The frozen Trade Bot research control had a 38.5% equity target and 61.5%
unallocated cash. Its current low-equity streak was five sessions; its first
at-or-below-half-equity observation in this window was November 10. Native
telemetry attributes the latest reduction to volatility budgeting. Its generic
stress monitor is **not** an allocation trigger in this control.

The separately captured Trade Bot operating summary had an orange status and a
1.0 risk-budget multiplier. This is a different pipeline stage, not proof of 100%
equity or a contradiction that can be resolved by equating unlike fields. The
dashboard keeps operating summaries apart from reconstructed final targets.

Rotation's frozen primary still held a 50/50 energy/healthcare target. It moved
from cash to invested at the October 30 scheduled decision. Its current timing
monitor has deteriorated, but the held target has not yet changed: the explicit
reason is `timing_warning_waiting_for_native_rebalance`. Energy's recent weakness
makes this lag visible; healthcare's strength means it is not simply a technology
portfolio wearing a different label. This observation does not authorize changing
the frozen rule without a separately governed experiment.

Swing's frozen monthly ETF control remained allocated to materials, energy and
healthcare. Its captured prices ended November 23, so it is stale and excluded
from the November 24 comparison. Coverage was fully fresh on 39 of 40 dates.
The separate stock shadow passed integrity and policy-identity checks, but its
independent data gate failed: **NO ACTION**. A data gate is not a bearish forecast.

The latest Cycle Tracker observation was November 23. Its structured raw phase
was early unwind, while its stored smoothed narrative emphasized normal cycle.
That conflict and known transition restrictions are exposed, not silently
reconciled or used to override allocations. Fundamental Event Trader's local
qualification remains blocked; it contributes no market vote.

## Did the Signals Work?

There are 35 matured five-session origins and 19 matured 21-session origins per
benchmark. Outcomes use daily adjusted closing prices. The loss label is a drop
of at least 5% from the origin within the forward horizon, not intraday maximum
drawdown or portfolio performance. Overlapping observations are dependent.

For QQQ over the next five sessions:

| Fixed flag | Mature warnings | Loss precision | Loss recall | Unconditional loss rate |
|---|---:|---:|---:|---:|
| Broad early watch | 27 | 33.3% | 81.8% | 31.4% |
| QQQ already at least 5% below recent high | 21 | 42.9% | 81.8% | 31.4% |
| Trade control at or below half equity | 5 | 60.0% | 27.3% | 31.4% |
| Rotation at or below half equity | 22 | 18.2% | 36.4% | 31.4% |
| Sector breadth below half | 6 | 0.0% | 0.0% | 31.4% |

The broad watch covered damage but barely improved on the loss base rate. The
technology drawdown flag was more selective in this particular technology-led
episode. Trade's low-equity observations look more concentrated around near-term
damage, but five overlapping warning origins are much too few to establish skill.
Broad sector breadth was not a useful short-horizon QQQ loss discriminator here.

Hard stress and SPY's long-trend break first appeared November 19. All four active
origins are too recent to have matured five-session outcomes at the cutoff. Their
predictive precision is **undefined**, not excellent. Waiting for those conditions
to confirm was late relative to damage already visible in October and early November.

On the 21-session QQQ loss label, the unconditional event rate was already 94.7%.
High apparent accuracy in that sample is largely uninformative without an inactive
comparison and independent episodes. No thresholds were optimized to improve these
results, and these newly implemented definitions are not preregistered forecasts.

## Implementation and Remaining Gates

- All three native adapters reconcile to frozen primary target files.
- All 120 native prefix checks passed: 40 available cutoffs per provider. Swing's
  available 40 end one session earlier; its missing November 24 is not fabricated.
- Market Desk and research views passed desktop/mobile browser navigation checks.
  Actual fact-pack downloads were also received and parsed in both viewports.
- The final five-repository run passed 1,191 tests with none skipped. A subsequent
  complete Portfolio Lab UI rerun passed 107 tests, bringing current coverage to
  1,192 tests including the new no-matured-outcomes display case. The earlier
  timing-sensitive Swing test failure is retained; its test-only startup allowance
  was fixed and the complete Swing suite and five-repository run then passed.
  These are local checks, not remote CI or live-trading approval. Changes are local.
- Financial-policy identity is separate from interpretation/presentation identity.
  The regenerated pre-existing research metrics were exactly unchanged.
- A local launchd poller is installed. Its smoke run verified the existing archive
  and returned `already_current`; it does not fetch native prices or place trades.
- Default narration is evidence-only, not LLM execution. The strict signal-only,
  date-blind handoff excludes accounts, actual holdings, position lists, journals
  and repository contents. External narration remains a separately approved mode.

The durable result is better observability and an honest evaluation baseline, not
new proof of alpha. Next research should distinguish late native scheduling from
weak inputs, evaluate independent episodes and benign periods, and capture future
briefs before outcomes exist. Do not tune the warning thresholds on this window
and then report the same window as validation.
