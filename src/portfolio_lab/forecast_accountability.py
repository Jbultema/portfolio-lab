"""Immutable, evidence-bound directional claims with strictly future scoring."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from portfolio_lab.briefing import calendar, completed_sessions, validate_pack
from portfolio_lab.contracts import ContractError, digest, frame_check, json_hash


def timestamp(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None or pd.isna(result):
        raise ContractError("Timezone-aware capture required")
    return result.tz_convert("UTC")


def record(root: Path, claim: dict, *, evidence: Path, now=None):
    required = {"model", "thesis", "ticker", "horizon", "threshold", "probability", "data_end", "evidence_sha256", "mode", "fact_ids"}
    if set(claim) != required:
        raise ContractError("Explicit claim schema required; capture time is assigned, not supplied")
    if (claim["mode"] not in {"prospective", "historical_reconstruction"}
            or not all(isinstance(claim[k], str) and 0 < len(claim[k]) <= limit for k, limit in (("model", 120), ("thesis", 1600), ("ticker", 24)))
            or not re.fullmatch(r"[a-f0-9]{64}", str(claim["evidence_sha256"]))
            or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,11}", claim["ticker"])
            or type(claim["horizon"]) is not int or claim["horizon"] not in {5, 21, 63}
            or type(claim["probability"]) not in (int, float) or not math.isfinite(claim["probability"])
            or not 0 <= claim["probability"] <= 1
            or type(claim["threshold"]) not in (int, float) or not math.isfinite(claim["threshold"])
            or not -1 < claim["threshold"] < 1):
        raise ContractError("Invalid forecast identity, probability, threshold or horizon")
    captured = timestamp(now or datetime.now(UTC))
    raw = evidence.read_bytes()
    pack = json.loads(raw)
    validate_pack(pack, claim["data_end"])
    fact_ids = claim["fact_ids"]
    if (not isinstance(fact_ids, list) or not fact_ids or any(not isinstance(f, str) for f in fact_ids)
            or len(fact_ids) != len(set(fact_ids)) or not set(fact_ids) <= {f["id"] for f in pack["facts"]}):
        raise ContractError("Forecast requires explicit matching supporting fact identities")
    if (hashlib.sha256(raw).hexdigest() != claim["evidence_sha256"] or pack.get("action_authorized") is not False
            or pack.get("as_of_session") != claim["data_end"]
            or timestamp(pack["information_cutoff_utc"]) > captured):
        raise ContractError("Claim must bind an available, matching read-only evidence pack")
    latest = str(completed_sessions(1, captured.to_pydatetime())[-1].date())
    data_end = str(pd.Timestamp(claim["data_end"]).date())
    if data_end > latest or (claim["mode"] == "prospective" and data_end != latest):
        raise ContractError("Prospective claim requires the latest completed session, not a backfill")
    payload = claim | {"data_end": data_end, "captured_at_utc": captured.isoformat(),
        "event": "horizon_close_return_below_threshold_from_first_executable_close",
        "performance_eligible": claim["mode"] == "prospective", "action_authorized": False}
    identity = json_hash(payload)
    root.mkdir(parents=True, exist_ok=True)
    folder = root / "evidence"
    folder.mkdir(exist_ok=True)
    bound = folder / (claim["evidence_sha256"] + ".json")
    if bound.exists():
        if digest(bound) != claim["evidence_sha256"]:
            raise ContractError("Corrupt archived forecast evidence")
    else:
        with bound.open("xb") as handle:
            handle.write(raw)
    path = root / (identity + ".json")
    with path.open("x") as handle:
        handle.write(json.dumps(payload | {"record_sha256": identity}, indent=2) + "\n")
    return path


def score(root: Path, prices: pd.DataFrame, *, now=None):
    frame_check(prices)
    clock = timestamp(now or datetime.now(UTC))
    last = completed_sessions(1, clock.to_pydatetime())[-1]
    quotes = prices.loc[:last]
    rows = []
    for path in sorted(root.glob("*.json")):
        claim = json.loads(path.read_text())
        if (claim.get("record_sha256") != json_hash({k: v for k, v in claim.items() if k != "record_sha256"})
                or path.stem != claim.get("record_sha256")
                or claim.get("action_authorized") is not False
                or claim.get("performance_eligible") != (claim.get("mode") == "prospective")
                or digest(root / "evidence" / (claim["evidence_sha256"] + ".json")) != claim["evidence_sha256"]):
            raise ContractError("Corrupt forecast journal")
        captured = timestamp(claim["captured_at_utc"])
        if captured > clock:
            raise ContractError("Future-dated forecast capture")
        row = {"id": path.stem, "model": claim["model"], "ticker": claim["ticker"],
            "horizon": claim["horizon"], "probability": claim["probability"], "threshold": claim["threshold"],
            "captured_at_utc": claim["captured_at_utc"], "thesis": claim["thesis"],
            "performance_eligible": claim["performance_eligible"], "status": "pending",
            "action_authorized": False}
        if claim["mode"] != "prospective":
            rows.append(row | {"status": "reconstruction_not_prospective"})
            continue
        cal = calendar()
        days = cal.sessions_in_range(captured.date(), (captured + pd.Timedelta(days=180)).date())
        execution = next(d for d in days if cal.session_close(d) > captured + pd.Timedelta(minutes=30))
        position = days.get_loc(execution)
        maturity = days[position + claim["horizon"]]
        if maturity > last:
            rows.append(row | {"entry_session": str(execution.date()), "maturity_session": str(maturity.date())})
            continue
        expected = days[position:position + claim["horizon"] + 1].tz_localize(None) if days.tz is not None else days[position:position + claim["horizon"] + 1]
        if claim["ticker"] not in quotes or not expected.isin(quotes.index).all():
            rows.append(row | {"status": "missing_scoring_prices"})
            continue
        series = quotes.loc[expected, claim["ticker"]]
        if series.isna().any():
            rows.append(row | {"status": "missing_scoring_prices"})
            continue
        outcome_return = float(series.iloc[-1]/series.iloc[0]-1)
        outcome = int(outcome_return < claim["threshold"])
        training = quotes.loc[:claim["data_end"], claim["ticker"]]
        first = training.first_valid_index()
        training = training.loc[first:] if first is not None else training.iloc[:0]
        # Every base-rate label ends by the claim's data cutoff.
        matured = training.pct_change(claim["horizon"], fill_method=None).dropna()
        expected_training = cal.sessions_in_range(training.index[0], training.index[-1]) if len(training) else pd.DatetimeIndex([])
        base = float(matured.lt(claim["threshold"]).mean()) if len(matured) >= 252 and training.index.equals(expected_training) and training.notna().all() else None
        rows.append(row | {"status": "matured_uncalibrated", "entry_session": str(execution.date()),
            "maturity_session": str(maturity.date()), "realized_return": outcome_return, "outcome": outcome,
            "brier": (claim["probability"]-outcome)**2, "historical_base_rate": base,
            "base_brier": None if base is None else (base-outcome)**2,
            "overlapping_labels_not_independent": True})
    return rows


def summarize(rows):
    groups = {}
    for row in rows:
        if row["status"] == "matured_uncalibrated" and row["performance_eligible"]:
            key = (row["model"], row["ticker"], row["horizon"], row["threshold"])
            groups.setdefault(key, []).append(row)
    results = []
    for key, group in groups.items():
        selected, last_end = [], ""
        for row in sorted(group, key=lambda r: (r["entry_session"], r["captured_at_utc"], r["id"])):
            if row["entry_session"] > last_end:
                selected.append(row)
                last_end = row["maturity_session"]
        base = [r["base_brier"] for r in selected if r["base_brier"] is not None]
        results.append({"model": key[0], "ticker": key[1], "horizon": key[2], "threshold": key[3],
            "matured_claims": len(group), "nonoverlapping_claims": len(selected),
            "nonoverlapping_brier": sum(r["brier"] for r in selected)/len(selected),
            "baseline_brier": sum(base)/len(base) if len(base) == len(selected) else None,
            "status": "immature" if len(selected) < 30 else "requires_calibration_and_human_review",
            "nonoverlap_does_not_prove_regime_independence": True, "action_authorized": False})
    return results
