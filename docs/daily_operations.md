# Portfolio Lab Daily Operations

Portfolio Lab is the single local interaction point. The sidebar exposes
**Update all & publish**, **Rebuild verified local data**, daily job status,
Positioning research, and native deep-dive links. Play icons start an allowlisted
native dashboard without stopping another process. Event research remains inside
Portfolio Lab rather than linking to a nonexistent standalone dashboard.

## One Pipeline, Two Triggers

```sh
PYTHONPATH=src .venv/bin/python -m portfolio_lab.operations start
PYTHONPATH=src .venv/bin/python -m portfolio_lab.operations run --cached
PYTHONPATH=src .venv/bin/python scripts/daily_service.py --install
```

The button and `com.jbultema.portfolio-lab.daily` LaunchAgent call the same
orchestrator. It polls every 15 minutes while the Mac is awake and logged in.
Exchange session closes plus 15 minutes determine the expected session, including
half-days. It catches up the latest missing daily publication; it does not invent
prospective historical forecasts. It does not wake a sleeping Mac.

Repository paths and optional dashboard URLs live in ignored
`data/operations_config.json`. The tested configuration binds the persistent
review worktrees and the independent `position-bot` clone. No employer credentials,
accounts, private holdings or cloud narration are required.

Stages:
1. Trade Bot native daily prices/macro/news and operating snapshot.
2. Swing public-data refresh and frozen monthly primary reconstruction.
3. Rotation public-data refresh and reconstruction of the bound frozen selection.
4. Event public news/context capture and explicit readiness assessment.
5. Position public CFTC/current ETF refresh and frozen research-rule reconstruction.
6. Three-core export and telemetry reconciliation to the same expected session.
7. Immutable 40-session desk, optional specialist context, integrity verification,
   and atomic publication.

No strategy search, reselection, automatic promotion or orders occur. Swing/Rotation
use dedicated frozen adapters rather than their broad research-running commands.
`daily` in the old Portfolio Lab research CLI is not this workflow.

## Failure Semantics

Cross-process launcher and worker locks coalesce concurrent clicks and protect
against duplicate execution. Detached workers keep progress outside Streamlit
reruns; receipts record stages, heartbeat, exit codes and logs. Provider failures
do not prevent the other native stages from being attempted. Native commands have
bounded execution and cancellation terminates their owned subprocess group.
Abandoned queued/dead workers become explicit failures rather than waiting for
another market-data refresh to discover them days later.

Failure/staleness in any core export/telemetry retains the prior publication.
Optional specialist failure creates an isolated degraded report, not a complete
publication or a new `last_complete.json`. Event's verified `blocked` readiness
receipt is a successful observation of a data gate, not a crashed job or a bearish
market vote. Position Bot likewise remains outside the admitted allocator.

The current-session local-data button is explicit: it never claims a network
refresh happened. Freshness and hashes are still checked. An explicit network
refresh never silently substitutes cached columns when a provider fails.

The new coordinator replaces the report-only `market-desk` LaunchAgent when
installed for operation. Run only one publication scheduler against a workspace.
The original checkouts/WIP remain preserved; deploying a review source is not
equivalent to merging main or accepting remote CI.

## Positioning Evidence

Position Bot supplies public CFTC participant positions, governed ETF mappings,
report/release/capture times and a separately qualified research strategy.
It appears in the daily readout and dedicated positioning workspace, not as an
extra independent confirmation vote. Current captures are never inserted into
past fact packs. The cross-bot integration lab evaluates standalone, fixed blends,
confirmation gating, cash controls, development-fitted risk controls, costs,
execution lags, crisis omissions and joint uncertainty. Its results cannot admit
an unqualified positioning strategy.
