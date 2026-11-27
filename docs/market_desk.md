# Market Interpretation Desk

## Scope and authority

The desk explains public market structure, frozen specialist research targets,
native rule telemetry, changes, disagreements, and source health. It cannot
select or promote strategies, change parameters, submit trades, read brokerage
accounts, or convert its scenarios into allocation overrides.

Its first view is the daily read, not a research leaderboard. The existing
portfolio research views remain available in the workspace menu.

## Daily operation

From the Portfolio Lab root:

```sh
.venv/bin/portfolio-lab brief-daily
.venv/bin/portfolio-lab brief-audit --report reports/market_desk_release_v2_20261125
.venv/bin/python -m streamlit run src/portfolio_lab/dashboard.py --server.address ::1 --server.port 8512
```

`brief-daily` captures local specialist exports in their own Python environments,
collects native diagnostics without reselection, and rebuilds a rolling 40-session
archive. It does **not** fetch market prices, rerun the full strategy search,
retune models, or execute anything. Run the native data-update workflows first.
An unavailable provider is recorded as missing, not replaced with cash or
silently forward-filled. A stale provider is excluded from same-session agreement.
No fresh market reference means no new publication.

`reports/market-desk/latest.json` is replaced atomically only after archive
verification. Existing archives are never overwritten. Jobs record start/end,
success/failure and exception type in `reports/market-desk/jobs`. A writer lock
prevents overlapping publications. A crash leaves the lock in place intentionally:
verify that its PID is no longer alive before removing that one stale lock.

Automatic polling is disabled. Use Portfolio Lab's **Update all & publish**
button to refresh all native inputs and rebuild the report explicitly.
The former report-only and coordinated LaunchAgents are unloaded; their
installer/poller scripts have been removed. No data refresh starts merely by
opening the dashboard. A current archive with partial coverage remains explicit.

## Evidence and interpretability

Each fact has an immutable ID, value, unit, source, observation session,
availability cutoff, and role: `native_driver`, `monitor`, or `target`.
Native adapters reconcile telemetry target columns against each bundle's frozen
primary target. Facts are computed from prefixes ending at the selected close.
No forward returns enter a fact pack, state classification, or narrator handoff.

Cash, defensive instruments and equity-risk instruments are separate. The
equity-risk proxy is an instrument classification, not factor beta or ETF
constituent look-through. Low-equity streaks use a fixed 50% target boundary.
Research targets are never described as held positions or actual executions.

Trade Bot operating summaries are shown separately, including storage timestamps
and configuration identities. A stored risk-budget multiplier is one pipeline
stage, not total equity exposure. Reconstructed controls and historical operating
records must not be combined into a purported executed track record.

The Swing monthly ETF control is not the separate stock-shadow system. Its latest
stock-shadow integrity and operational gate are shown as a current audit, not a
historical vote. Cycle Tracker is contextual, with explicit raw/narrative
disagreement and transition-model caveats. Fundamental Event Trader's actual
qualification result is collected locally; a blocked dataset produces no opinion.

## Narrative modes and privacy

The default is `evidence_only`: local deterministic calculations and explanations.
It is not an LLM, and no external requests or model execution are claimed.

A bounded agent handoff is available:

```sh
.venv/bin/portfolio-lab brief-handoff --pack REPORT/sessions/SESSION/pack.json
.venv/bin/portfolio-lab brief-review --pack REPORT/sessions/SESSION/pack.json --result RESULT.json
.venv/bin/portfolio-lab brief-attach --report REPORT --session SESSION --result RESULT.json --output NEW_ARCHIVE
```

The handoff uses a strict field allowlist of public numeric signals and research
model health. It excludes account balances, actual holdings, target-position lists,
journals, repository files, free source text, capture identities and calendar dates.
The handoff itself has no network access and no tools. Running an external narrator
requires explicit approval of that transfer; configuring a cloud model is not
local inference. A local model can consume the same interface.

Agent claims must cite existing fact IDs, contain no numeric prose (exact values
are rendered from verified facts), and pass schema/authority checks. An identified,
distinct skeptical reviewer must approve. Self-declared reviewer identities are
an audit convention, not cryptographic proof of independent judgment. Deterministic
checks cannot prove arbitrary prose semantically true; reviewed text remains
interpretation, never policy. Rejected outputs do not change the evidence baseline.
Attaching approved prose creates a new archive with its parent's manifest hash;
it cannot rewrite the original daily artifact or financial policy lineage.

## Forty-session evaluation

```sh
.venv/bin/portfolio-lab brief-replay --sessions 40
.venv/bin/python scripts/check_brief_prefixes.py --bundles CAPTURE_ROOT --count 40 --output NEW_CHECK_DIRECTORY
.venv/bin/python scripts/check_dashboard.py --url 'http://[::1]:8512' --output NEW_BROWSER_DIRECTORY
```

The replay covers the last 40 **completed NYSE sessions**, not 40 weekdays. For
each session it publishes the fact pack, brief, narrator status, and timeline.
Source coverage remains per-bot; the oldest provider does not truncate fresh data.
The prefix checker separately rebuilds every native diagnostic history at each
provider's last 40 available cutoffs, including target reconciliation columns.

Evaluation is separate: 5- and 21-session SPY/QQQ returns and worst loss from the
origin. An outcome requires the origin plus exactly that many later exchange
sessions, every observation present, and no observation beyond the evaluation
cutoff. Unmatured outcomes are null, not zero or selectively dropped by performance.

Fixed descriptive flags are compared with the unconditional loss base rate:
early watch, hard stress, technology drawdown, broad-index trend, sector breadth,
and native low-equity targets. Precision, recall, sample size, active/inactive
returns, and missing outcomes are visible. These definitions were implemented
after this history was observed; none is a preregistered blind forecast claim.
Overlapping windows are dependent, and one stressed two-month interval cannot
establish durable predictive advantage. No strategy CAGR is attributed to prose.

Pretrained narrators can know history even with prefixes. Date-blind inputs reduce
but cannot remove that contamination. Only immutable, capture-timed future
briefs can establish a genuinely prospective narrative record.

## Governance boundaries

Financial policy manifests now explicitly use `financial_policy_v1`: allocation,
contracts, accounting engine, shadow evaluation/audit, research selection, and the governance definition.
Legacy full-source manifests retain their old strict check; they are not silently
grandfathered. The initial migration regenerated research once and verified all
old metrics were unchanged. Narrator/prompt hashes and source identities are
recorded independently. Wording and UI edits do not reset trading policy identity.
