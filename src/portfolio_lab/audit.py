from __future__ import annotations

import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from portfolio_lab.contracts import ContractError, digest, json_hash


def audit(output: Path, *, now: datetime | None = None) -> dict:
    errors = []
    try:
        manifest = json.loads((output / "manifest.json").read_text())
        if (
            manifest.get("authority") != "research_only"
            or manifest.get("automatic_promotion_allowed") is not False
        ):
            errors.append("invalid_authority")
        artifacts = manifest["artifacts"]
        for name, expected in artifacts.items():
            path = (output / name).resolve()
            if (
                not path.is_relative_to(output.resolve())
                or not path.is_file()
                or digest(path) != expected
            ):
                errors.append(f"artifact_mismatch:{name}")
        required = {
            "frozen_selection.json",
            "current_state.json",
            "trial_registry.csv",
            "metrics.csv",
            "returns.parquet",
            "selected_targets.parquet",
            "selected_budgets.parquet",
        }
        if not required <= artifacts.keys():
            errors.append("missing_required_artifacts")
        current = json.loads((output / "current_state.json").read_text())
        if current.get("action") != "NO ACTION":
            errors.append("unexpected_action_authority")
        code_root = Path(__file__).parent
        actual_code = json_hash(
            {str(p.relative_to(code_root)): digest(p) for p in sorted(code_root.rglob("*.py"))}
        )
        if actual_code != manifest["policy_source_sha256"]:
            errors.append("source_code_changed_since_research")
        for name, expected in manifest.get("environment", {}).items():
            if version(name) != expected:
                errors.append(f"dependency_changed:{name}")
        today = (now or datetime.now(UTC)).date()
        age = (today - datetime.fromisoformat(current["as_of_close"]).date()).days
        if age < 0 or age > 7:
            errors.append("stale_or_future_market_date")
        if current["selected_research_policy"] != manifest["selection"]["selected"]:
            errors.append("selection_identity_mismatch")
        for bundle in manifest["metadata"]["bundles"]:
            for source in bundle["source_inputs"]:
                # Source paths are repo-local. Bundle bytes are independently bound;
                # do not misinterpret relative paths as portfolio-lab paths.
                if not source.get("sha256"):
                    errors.append("missing_source_identity")
    except (OSError, KeyError, ValueError, TypeError) as exc:
        errors.append(f"unreadable_evidence:{type(exc).__name__}")
    return {
        "status": "passed_research_integrity" if not errors else "failed_closed",
        "errors": errors,
        "authority": "research_only",
        "action_authorized": False,
    }


def record_shadow(output: Path, journal_root: Path, *, now: datetime | None = None) -> Path:
    checked = audit(output, now=now)
    if checked["errors"]:
        raise ContractError(f"Cannot shadow invalid research: {checked['errors']}")
    manifest = json.loads((output / "manifest.json").read_text())
    state = json.loads((output / "current_state.json").read_text())
    lineage = json_hash(
        {
            "policy_source": manifest["policy_source_sha256"],
            "selection": manifest["selection"],
            "specialist_code": [b["code_sha256"] for b in manifest["metadata"]["bundles"]],
        }
    )
    folder = journal_root / lineage
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{state['as_of_close']}.json"
    payload = {
        "schema_version": 1,
        "lineage": lineage,
        "signal": state,
        "input_bundle_hashes": manifest["metadata"]["bundle_sha256"],
        "authority": "research_only",
        "performance_eligible": False,
        "reason": "initialization_or_signal_record_only_no_backdated_fills",
        "earliest_execution": "a_regular_session_close_strictly_after_record_capture",
        "expiry_after_executed_sessions": 5,
    }
    stable_hash = json_hash(payload)
    if path.exists():
        existing = json.loads(path.read_text())
        if existing.get("signal_hash") != stable_hash or existing.get("record_sha256") != json_hash(
            {k: v for k, v in existing.items() if k != "record_sha256"}
        ):
            raise ContractError("Conflicting or corrupt immutable shadow record")
        return path
    payload |= {
        "signal_hash": stable_hash,
        "captured_at_utc": (now or datetime.now(UTC)).isoformat(),
    }
    payload["record_sha256"] = json_hash(payload)
    with path.open("x") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def evaluate_shadow(journal: Path, prices, cash_returns) -> dict:
    import exchange_calendars as xcals
    import pandas as pd

    from portfolio_lab.contracts import frame_check
    from portfolio_lab.engine import metrics, replay

    frame_check(prices)
    records = []
    for path in sorted(journal.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("record_sha256") != json_hash(
            {k: v for k, v in record.items() if k != "record_sha256"}
        ):
            raise ContractError("Corrupt shadow record")
        records.append(record)
    if not records:
        return {"status": "pending_no_records", "action_authorized": False}
    if len({r["lineage"] for r in records}) != 1:
        raise ContractError("Cannot splice policy lineages")
    calendar = xcals.get_calendar(
        "XNYS", start=prices.index.min(), end=prices.index.max()
    )
    schedule = calendar.schedule.loc[prices.index.min():prices.index.max()]
    if not prices.index.equals(schedule.index):
        raise ContractError("Shadow prices must include every actual NYSE session and no holidays")
    closes = pd.DatetimeIndex(schedule["close"])
    weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    entries = []
    # A later capture supersedes an earlier one at the same execution close,
    # regardless of historical signal date or filename ordering.
    captures = []
    for record in records:
        captured = pd.Timestamp(record["captured_at_utc"])
        if pd.isna(captured) or captured.tzinfo is None:
            raise ContractError("Shadow capture must be timezone-aware")
        expiry = record["expiry_after_executed_sessions"]
        if not isinstance(expiry, int) or isinstance(expiry, bool) or expiry != 5:
            raise ContractError("Invalid shadow expiry policy")
        captures.append((captured, record))
    captures.sort(key=lambda item: item[0])
    if len({captured for captured, _ in captures}) != len(captures):
        raise ContractError("Ambiguous simultaneous shadow captures")
    for captured, record in captures:
        position = int(closes.searchsorted(captured, side="right"))
        if position >= len(prices):
            continue
        if position == 0:
            raise ContractError("Need a pre-execution observation for shadow accounting")
        targets = record["signal"]["target_holdings"]
        if not set(targets) <= set(prices):
            raise ContractError("Missing shadow holding price")
        if entries and entries[-1][0] == position:
            entries[-1] = (position, record)
        else:
            entries.append((position, record))
    if not entries:
        return {
            "status": "pending_future_execution",
            "records": len(records),
            "action_authorized": False,
        }
    for i, (position, record) in enumerate(entries):
        next_position = entries[i + 1][0] if i + 1 < len(entries) else len(prices)
        stop = min(next_position, position + int(record["expiry_after_executed_sessions"]))
        # Replay shifts once. Write the locked target to its prior-close row,
        # but the target was captured before the modeled execution close.
        for ticker, value in record["signal"]["target_holdings"].items():
            weights.loc[weights.index[position - 1 : stop - 1], ticker] = value
    result = replay(prices, weights, cash_returns)
    first = entries[0][0]
    observed = result.returns.iloc[first:]
    return {
        "status": "prospective_paper_immature"
        if len(observed) < 126
        else "prospective_paper_human_review_required",
        "sessions": len(observed),
        "records": len(records),
        "first_execution": str(prices.index[first].date()),
        "metrics": metrics(observed, result.turnover),
        "expiry_policy": "cash_after_five_executed_sessions_without_refresh",
        "action_authorized": False,
        "automatic_promotion_allowed": False,
    }
