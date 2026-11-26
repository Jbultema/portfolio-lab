# Dynamic allocation research: 2026-11-26

## Decision

Do not promote a new allocator from this study. Selectively allocating between the current bots preserves much more Trade Bot performance than compulsory equal-weight diversification, but it has not demonstrated incremental performance over unchanged Trade Bot.

The primary three-round study tested **50 core policy specifications and 12 conditional event specifications**, with **807 portfolio/control/execution paths**. A fourth, explicitly post-hoc follow-up tested **six additional price-context policies**, adding 72 candidate/control paths and three repeated baseline checks. That is **56 core policies plus 12 conditional event policies**, not 879 independent hypotheses.

At the primary execution assumption, **zero of the 56 core policies beat Trade Bot's CAGR over 2019 onward**. One consensus policy matched it because it never left Trade Bot. Some policies improved drawdown. Three event-conditioned cases produced microscopic positive CAGR differences in the short evaluation; the largest was about one basis point per year, based on ten switched sessions. None showed positive excess that passed the within-slate adjustment across the tested block lengths.

This is evidence against these implementations using the current experts and data. It is not proof that dynamic allocation, qualified event information or a future genuinely different specialist cannot work.

## What Changed

New research modules implement sparse, Trade-anchored allocation without equal-weight shrinkage or mandatory alternative budgets. An alternative can receive zero; the entire strategy budget can remain with Trade Bot. A full Trade Bot strategy budget still preserves its internal cash holdings and native risk controls; it does not mean full equity exposure.

Existing bot strategies, the admitted-specialist contract, the daily allocator and `reports/latest.json` are unchanged. Research is exposed separately in the `Dynamic allocation` workspace and through `reports/dynamic-allocation/latest.json`. The event probes remain conditional and unadmitted.

## Data And Execution

- Same captured data and i111-derived primary as the previous cross-bot study. Core common history: 5,258 NYSE sessions, 2006-01-03 through 2026-11-25.
- Trade primary: `i111_reentry_vol_target_fast_21d_no_trend_vol185_guard145`.
- Native targets and source manifests are hash-bound. No new price download, revised strategy selection or official macro-event history was introduced.
- Routing features and shadow expert outcomes use the prior completed close. Conditional historical outcomes are associated with the regime known at the beginning of their return interval, not a regime assigned after seeing that interval's outcome.
- Combined close-known targets fill at the next observed close. Execution stresses use next-close/10 bps and fifth-close/50 bps. Primary cost: 25 bps per traded side. Costs are funded and overlapping holdings netted before replay.
- Routing evidence continues to use the frozen next-close/25-bps shadow expert history when stressing execution. These are fixed-signal execution stresses, not an adaptive simulator of model signals retraining on the account's delayed fills.
- All policies are long-only, unlevered. No account positions, external narration, derivatives or automatic orders are involved.

The native next-open backtest and this common-clock close-fill test are not interchangeable. Full-history Trade Bot here remains 17.85% CAGR / -26.49% drawdown at 25 bps, or 20.82% / -25.02% at 10 bps.

## Hypotheses And Iterations

### Round 1: Six Families, 36 Policies

Each family tests two evidence horizons and alternative budget ceilings of 25%, 50% and 100%:

| Family | Hypothesis |
|---|---|
| Relative skill | Recent net, risk-penalized expert outcomes identify when another bot deserves capital |
| Conditional skill | An alternative has an incremental advantage in the current price-defined regime, with shrinkage toward zero advantage rather than equal allocation |
| Leadership | Broad positive sector leadership with weakening technology-relative leadership favours Rotation Trader |
| Rebound | Repair after a selloff, while volatility remains elevated, favours Swing Trader |
| Stress defender | A lower-downside alternative can protect during transition/stress; otherwise the switched sleeve is cash |
| Sparse weights | Strong enough relative evidence supports gradual weights, while weak alternatives remain at zero |

All start from Trade Bot. Weekly scheduling and minimum holds limit switching; there is no compulsory diversification floor.

### Round 2: Eight Timing/Persistence Follow-ups

Families advance by their median score over 2012-2015, not their later returns. The score combines return/drawdown utility versus Trade Bot and excess return against a matched-target-exposure control.

The first window advanced conditional skill and rebound. Conditional skill's median score was only +0.00021, while the next family was already negative: this was weak evidence, not a discovery.

For each selected family, the best first-window member receives four predeclared follow-ups: three/five-session confirmation x daily/weekly scheduling, with a ten-session minimum hold. These follow-ups are not treated as available before 2016 in the simulation; pre-availability performance is excluded from their reported periods.

### Round 3: Six Mechanism Combinations

The second selection window is 2016-2018. All six family median scores were negative. The least-bad families still advance under the predefined diagnostic procedure: a confirmed rebound policy and a stress-defender policy.

Their budgets are combined through union, intersection, stress-context routing, 63/126-session online parent selection and defensive union. The combined rules are not treated as available before 2019. No post-2018 outcome selects their parents.

The intersection rule never found agreement on an alternative in the later window and reproduced Trade Bot. Matching the baseline through inactivity is not an improvement.

### Conditional Event Tests: 12 Policies

Three previously studied accounting probes are tested at 25% and 50% ceilings under two mechanisms:

- A performance-gated event sleeve, activated only when prior net event-strategy outcomes justify the budget.
- A price-context router activated by above-normal accounting-probe target activity. It routes toward Rotation on leadership conditions or Swing on rebound conditions; otherwise it retains Trade Bot.

Probes: executed repurchases, working-capital repair and liquidity repair, each with 126-session event lifetimes. Accounting target activity is a proxy for qualifying positions, not a complete filing or financial-news event tape.

Each has an event-free price-only ablation. Event evaluation is 2025-01-02 onward, 477 sessions. The three probes were chosen after earlier exploratory work; this is not an untouched event holdout. Ten current survivors, missing failed-security paths and unverified original-release vintages continue to prevent admission.

### Round 4: Six Post-hoc Price-context Follow-ups

One event-free price-context control looked attractive in the short sample under five-session/50-bps execution, despite losing under primary execution. Rather than ignoring that lead or treating the favourable delay as a winner, a separate frozen follow-up tested the combined leadership/rebound rule over full core history: 25/50/100% ceilings x three/five-session confirmation, weekly scheduling and a ten-session minimum hold.

All six lagged Trade Bot's CAGR over the full history and over 2019 onward, including under the same severe execution stress. The short-sample lead did not generalize. This follow-up is explicitly post-hoc falsification, not new independent confirmation.

## Main Performance Results

Comparable later window: **2019-01-01 through 2026-11-25**, next-close fills and 25 bps per traded side. Displayed cases are illustrative, not a selected live portfolio.

| Approach | CAGR | Maximum drawdown |
|---|---:|---:|
| Unchanged Trade Bot | 24.96% | -25.97% |
| Swing Trader alone | 12.48% | -23.72% |
| Rotation Trader alone | 4.34% | -16.43% |
| Previously frozen Portfolio Lab allocator | 14.27% | -14.97% |
| Confirmed rebound, daily follow-up | 24.66% | -27.29% |
| 25% stress-defender ceiling, 126-session evidence | 24.04% | -25.05% |
| Online combination, 63 sessions | 23.84% | -24.84% |
| Defensive combination | 22.94% | -24.46% |
| Best-CAGR additional price-context follow-up | 24.20% | -25.89% |

The return-preserving policies are much closer to Trade Bot than the old near-equal allocator, but being closer to a strong baseline is not new alpha. All 36 initial policies also lag Trade Bot over the full 2006-plus history. The best initial full-history CAGR is 17.37%, with -27.98% drawdown, versus 17.85% / -26.49% for Trade Bot.

### Family-level Later Results

Median CAGR across the six initial specifications in each family, 2019 onward:

| Family | Median CAGR |
|---|---:|
| Relative skill | 19.65% |
| Conditional skill | 20.82% |
| Leadership | 21.84% |
| Rebound | 24.02% |
| Stress defender | 22.53% |
| Sparse weights | 20.97% |
| Trade Bot reference | 24.96% |

Recent-performance switching and regime-specific relative skill did not reliably identify the right specialist. The early selected full-switch conditional rule later returned 13.56% CAGR / -37.15% drawdown, a substantial failure. Timing confirmation reduced some damage but did not create a performance advantage.

## Did Another Bot Help, Or Was It Just Cash?

Every candidate has four comparable paths:

1. Raw combined portfolio.
2. Its proposed Trade budget alone, leaving alternative budget in cash.
3. Combined portfolio capped to Trade Bot's close-known invested target.
4. Trade Bot scaled to match that capped target exposure.

The last two match target exposure, not necessarily identical executed daily exposure: holdings can drift differently between trades. The cap prevents apparent gains from simply overriding Trade Bot's native cash decision with a more invested specialist.

For the defensive combination over 2019 onward:

| Path | CAGR | Maximum drawdown |
|---|---:|---:|
| Combined router | 22.94% | -24.46% |
| Its cash-only ablation | 23.07% | -24.09% |
| Exposure-capped router | 22.96% | -24.32% |
| Matched-target-exposure Trade | 23.23% | -24.16% |

Both simpler controls outperform their corresponding combined approach on return and drawdown. For the 126-session stress defender, raw CAGR is 24.04%, versus 24.00% for its cash-only ablation: the specialist contribution is negligible. Its capped CAGR is 23.99%, below matched Trade's 24.35%.

There is no robust evidence that the alternate bot earns the capital beyond what changing Trade Bot's risk budget can achieve.

## Crises And Recent Conditions

The defensive combination reduces COVID episode drawdown from -15.93% to -11.22%. It reduces the 2022/rates episode from -25.54% to -23.92%. These are useful protection observations, but they come with the documented growth cost and do not establish specialist-selection skill.

For the unfinished June 2026-onward period:

| Approach | Total return | Maximum drawdown |
|---|---:|---:|
| Trade Bot | -3.85% | -11.25% |
| Stress defender | -3.65% | -10.98% |
| Defensive combination | -2.88% | -9.69% |
| Same defensive combination's cash-only ablation | -2.47% | -9.33% |

This supports the narrower conclusion that reducing risk can help during this window. It does not show a need to fund another bot to obtain the protection. The period is unfinished, and these reconstructed outcomes are not captured live decisions or personal-account results.

## Event Results And Uncertainty

Trade Bot's conditional-window reference is **28.5123% CAGR / -11.5719% drawdown**. The highest-CAGR event-conditioned router is **28.5225% / -11.5719%**, only **0.0102 percentage points** ahead annually, after allocating away from Trade Bot for ten of 477 sessions.

At 63-session blocks its annual log excess is +0.0080%, with a 95% interval of **-0.6209% to +0.6623%** and adjusted p-value **1.0**. The capped version returns only 28.07% CAGR, below its matched Trade control's 28.51%. Under five-session/50-bps execution, the raw event router returns 25.05%, below Trade's 25.33%.

This is neither economically substantial nor robust. Gated repurchase sleeves also lose growth; gating reduces dilution but does not establish an advantage. The event-free control's short-sample stress gain fails its long-history follow-up.

Across both core and event slates, none of the positive annual-log excess estimates passes the within-slate adjustment under the tested 21/63/126-session blocks, against Trade, cash, matched target exposure or the applicable event-free ablation. The six supplementary policies also produce no adjusted positive result. These tests do not correct for the entire historical research program, adaptive selection history or previously inspected market data.

## Stability And What We Learned

- Allowing zero alternative budgets removes much of the dilution caused by compulsory diversification. It does not make weaker specialists useful automatically.
- Rebound follow-ups remain near Trade largely because they switch rarely. The closest daily follow-up allocates to Swing only about 3.6% of its simulated post-2016 sessions. Sparse activity is not proof of prediction skill.
- The stress defender beats Trade's return in only 26.5% of 83 overlapping one-year windows and 3.4% of 59 overlapping three-year windows, measured from 2019 onward. These windows overlap and are not independent trials.
- The defensive combination improves drawdown in all of those overlapping three-year windows but beats Trade's return in none. This is an identifiable protection/growth trade-off.
- Selection rankings change across early windows; the selected families are not stable winners.
- Aggressive switching amplifies mistakes. The best response to weak evidence is often retaining Trade, not allocating to the runner-up.
- No official macro-event release history, broad news-event archive or new failed-security history was added. These results do not exhaust genuinely new event information.

## Next Decision

Keep the allocation changes research-only. Do not select a live rule by inspecting the later table or tuning to the current drawdown.

The useful next branch is a simpler, explicitly evaluated total-risk policy, tested against unchanged Trade with a predeclared acceptable growth cost. Native integration would be a separate decision. Further threshold searches on the same weaker bot set are not justified by a strong signal here.

An event-conditioned allocator remains a future hypothesis only when supported by a broader point-in-time event dataset, historical failed securities and new prospective observations. More routing complexity is not a substitute for additional information or better specialists.

## Reproduction And Verification

- Primary output: `reports/dynamic_allocation_20261126/`
- Rolling/duplicate/crisis-dependence diagnostics: `reports/dynamic_diagnostics_20261126/`
- Supplementary context output: `reports/dynamic_context_followup_20261126/`
- Browser evidence: `reports/browser-dynamic-20261126/`
- Dashboard: `http://[::1]:8513/?workspace=dynamic`

```sh
.venv/bin/python -m portfolio_lab.dynamic_research verify \
  --output reports/dynamic_allocation_20261126
.venv/bin/python -m portfolio_lab.dynamic_context_followup verify \
  --output reports/dynamic_context_followup_20261126
```

New runs require fresh output directories. Use `dynamic_research freeze --source reports/combination_stress_20261126_v3 --output ...` before `dynamic_research run --output ...`. Frozen dependency hashes, input manifests and protocol hashes are checked before and after measurement. A measured primary output cannot be overwritten. The supplementary study has its own freeze/run/verify commands and is labeled post-hoc.

Validation: the full Portfolio Lab suite, targeted causal-prefix and selection-chronology tests, Ruff, and desktop/mobile browser checks. Browser tests assert actual selected policy and execution values, nonblank equity/drawdown and budget charts, no document overflow and working downloads. Existing unrelated repository changes are preserved.
