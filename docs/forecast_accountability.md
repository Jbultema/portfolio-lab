# Forecast Accountability

Market Desk replay is historical reconstruction. It is not a captured forecast,
and no forecast records are fabricated from those 40 historical sessions.

## Agent Contract

An analyst may submit an explicit 5/21/63-session probability claim for an ordinary
security's close-to-close return falling below a declared threshold. Every claim
requires a versioned model identity, a thesis, supporting fact IDs and the hash of
the exact validated Market Desk pack. Phase confidence and a narrative's strength
are not probabilities of a future drawdown. If a probability lacks a defensible
basis, submit no claim rather than invent a number. A skeptical reviewer should
check the facts, competing explanation, prediction event and prior trial history
before capture. This journal does not constitute an independent analyst pair.

Capture time is assigned by the process, never accepted in the input. Prospective
claims require the latest completed exchange session. Historical reconstructions
remain permanently ineligible. Exact evidence bytes are archived once. Rewriting
or duplicating a record under another name fails integrity validation.

The event is specifically **terminal horizon return below threshold**, not the
probability of any interim drawdown or a crash sometime during that horizon.
Execution starts at the first exchange close more than 30 minutes after capture;
P&L/outcome measurement begins after that close. Holidays and half-days use the
exchange calendar. Missing sessions/prices remain unscored, never compressed.

Matured claims receive Brier scores and an unconditional historical event-rate
comparator using labels matured by the claim's information cutoff. This baseline
is descriptive, not a qualified predictive model. The scorer accepts hash-bound
price artifacts; revised adjusted-price limitations remain. Future rows cannot
make an immature claim mature or affect its training base rate.

Repeated overlapping labels are reported separately from a greedily selected
nonoverlapping series. Fewer than 30 nonoverlapping matured observations remains
immature; exceeding that floor still requires calibration and independent human
review. Nonoverlap does not prove independent regimes. No record or score grants
portfolio, promotion or trade-execution authority.

## Commands

Run from this checkout with its isolated interpreter:

```sh
PYTHONPATH=src .venv/bin/python -m portfolio_lab.cli forecast-record \
  --claim /absolute/path/to/reviewed-claim.json \
  --evidence /absolute/path/to/sessions/YYYY-MM-DD/pack.json

PYTHONPATH=src .venv/bin/python -m portfolio_lab.cli forecast-score \
  --prices /absolute/path/to/prices.parquet \
  --manifest /absolute/path/to/manifest.json
```

Required claim fields: `model`, `thesis`, `ticker`, `horizon`, `threshold`,
`probability`, `data_end`, `evidence_sha256`, `mode`, `fact_ids`. `mode` is
`prospective` or `historical_reconstruction`. Default journal is `data/forecasts`.
No actual prospective forecasts or calibrated forecasting edge are claimed yet.
All processing remains local; no account information or evidence is sent to an API.
