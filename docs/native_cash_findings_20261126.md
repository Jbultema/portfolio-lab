# Native Staged Cash-Risk Validation

## Decision

Do not promote these staged rules. Additional price-confirmation gates reduce
growth without establishing an incremental timing advantage. Keep the operating
primary unchanged. A lower-risk static allocation is a risk preference, not a
new timing discovery.

## Actual Work

The native `staged_dual_momentum` type composes its selection and staged sizing
inside Trade Bot, with validated native configuration and explicit required
signal series. Its base can be the actual i111 dual-momentum primary or the
registered native risk-repair challenger. It is not a Portfolio Lab allocator.

The fixed slate contains 24 new rules: two actual parent strategies, gentle /
confirmed / explicit repair modes, 126 / 252-session market peaks, and retained /
replaced incumbent drawdown-guard ablations. Two unchanged parents and four
65%/85% static-risk controls complete 30 candidates. No winner is selected.
The guard ablation was registered before inspecting the initial slate's returns.

Native engine: 180 cost/delay paths. Independent funded common-clock engine:
192 paths including SPY and QQQ buy-and-hold controls. Costs are 10/25/50 bp
per traded side; delayed-execution cases are explicit. Initial/native and final
guard-ablation archives remain separate, not overwritten.

All comparisons share 2008-04-09 through 2026-11-25 (4,689 sessions), after
252 complete sessions of SPY/QQQ/credit/participation inputs. This cannot test
pre-GFC warning onset and is not a survivor-free opportunity set or new holdout.

## Results

Funded common-clock full sample, next-close fill, 25 bp:

| Model | CAGR | Maximum drawdown |
|---|---:|---:|
| Current primary unchanged | 17.59% | -26.57% |
| Gentle 126 / incumbent guard | 16.39% | -26.26% |
| Confirmed 126 / incumbent guard | 15.64% | -27.67% |
| Explicit repair 126 / incumbent guard | 15.85% | -27.82% |
| Primary static 85% risk control | 17.59% | -24.40% |
| Native risk-repair parent unchanged | 17.63% | -26.74% |
| Risk-repair parent static 85% | 17.67% | -23.65% |
| SPY buy and hold | 11.32% | -51.48% |
| QQQ buy and hold | 16.13% | -49.37% |

The apparent static-control improvement is not evidence for a better risk clock.
In 2019+ its growth trails each corresponding unchanged parent. In the native
engine at 25bp, unchanged current-primary CAGR is 16.73%/-28.48% DD versus
16.48%/-26.23% for static 85%. Native and common engines have different
control timing/accounting and are reported separately, not declared conformant.

No new rule has a positive slate-adjusted excess comparison at 21/63/126-session
bootstrap blocks. Every new rule still loses annual-log return to its parent
after separately omitting 2020, 2022, or the sampled GFC interval. These omission
diagnostics are discontinuous, nontradable series, not alternative backtests.
Adjustments cover this slate, not the entire historical research program.

## Durable Conclusions

Removing the incumbent drawdown guard changes most staged paths little or not
at all. This particular double-throttle explanation does not account for their
performance loss. The extra staged gates themselves are too restrictive here;
more persistent confirmation/re-entry is not automatically better protection.

Future research should distinguish selection's lack of qualified alternatives,
volatility sizing, and discretionary risk preference. Do not add another dynamic
allocator or threshold sweep to manufacture a recovery in this inspected sample.
Qualified new information and frozen prospective evidence remain the real gates.

## Evidence

- Trade Bot `reports/system_cycles_20261126/cycle3_native_v2`
- Portfolio Lab `reports/system_cycles_20261126/cycle3_common`
- The native protocol, all specifications, source hashes, costs and every path
  are retained. Funded returns, uncertainty and crisis omissions are downloadable
  artifacts, not rounded narrative-only results.
