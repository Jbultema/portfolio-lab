from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd


class ContractError(ValueError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def frame_check(frame: pd.DataFrame, *, weights: bool = False) -> None:
    if frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        raise ContractError("Nonempty date-indexed frames required")
    if (
        frame.index.tz is not None
        or frame.index.hasnans
        or not frame.index.equals(frame.index.normalize())
        or frame.index.has_duplicates
        or not frame.index.is_monotonic_increasing
    ):
        raise ContractError("Dates must be unique, increasing and timezone-naive sessions")
    if not frame.columns.is_unique or any(not isinstance(c, str) for c in frame):
        raise ContractError("Unique string instrument identifiers required")
    if np.isinf(frame.to_numpy(dtype=float)).any():
        raise ContractError("Infinite values prohibited")
    if weights and (
        frame.isna().any().any() or frame.lt(0).any().any() or frame.sum(axis=1).gt(1 + 1e-9).any()
    ):
        raise ContractError("Targets must be finite long-only budgets summing to at most one")
    if not weights and frame.le(0).any().any():
        raise ContractError("Observed adjusted prices must be positive")


@dataclass
class Bundle:
    root: Path
    manifest: dict
    prices: pd.DataFrame
    targets: dict[str, pd.DataFrame]
    cash_returns: pd.Series
    terminal_events: list[dict] = field(default_factory=list)


def load_bundle(path: Path) -> Bundle:
    manifest = json.loads((path / "manifest.json").read_text())
    required = {
        "schema_version",
        "system",
        "artifacts",
        "experts",
        "native_execution",
        "primary_expert",
        "code_sha256",
        "source_inputs",
        "data_end",
    }
    if not required <= manifest.keys() or manifest["schema_version"] != 1:
        raise ContractError("Unsupported or incomplete specialist bundle")
    if (
        manifest.get("automatic_promotion_allowed") is not False
        or manifest.get("authority") != "research_only"
    ):
        raise ContractError("Specialist bundle must explicitly deny allocation authority")
    if not {"prices.parquet", "cash_returns.parquet"} <= manifest["artifacts"].keys():
        raise ContractError("Prices and cash returns must be hash-bound")
    for name, expected in manifest["artifacts"].items():
        file = (path / name).resolve()
        if (
            not file.is_relative_to(path.resolve())
            or not file.is_file()
            or digest(file) != expected
        ):
            raise ContractError(f"Artifact integrity failed: {name}")
    prices = pd.read_parquet(path / "prices.parquet")
    frame_check(prices)
    cash = pd.read_parquet(path / "cash_returns.parquet")["cash_return"]
    if not cash.index.equals(prices.index) or not np.isfinite(cash).all() or (cash <= -1).any():
        raise ContractError("Cash returns must be finite and aligned")
    targets = {}
    for expert in manifest["experts"]:
        name = expert["id"]
        if name in targets or expert.get("target_semantics") != "close_known_risky_budgets":
            raise ContractError("Duplicate or unsupported expert targets")
        if expert.get("evidence_status") != "retrospective_research":
            raise ContractError("Unrecognized evidence status")
        weight_path = (path / expert["weights_file"]).resolve()
        if expert["weights_file"] not in manifest["artifacts"] or not weight_path.is_relative_to(
            path.resolve()
        ):
            raise ContractError("Target path is unbound or outside the bundle")
        weights = pd.read_parquet(weight_path)
        frame_check(weights, weights=True)
        if not weights.index.equals(prices.index) or not set(weights) <= set(prices):
            raise ContractError("Targets must align to their own captured price panel")
        if (
            not set(expert["weights_file"] for expert in manifest["experts"])
            <= manifest["artifacts"].keys()
        ):
            raise ContractError("All target files must be hash-bound")
        if (weights.gt(1e-12) & prices.reindex(columns=weights.columns).isna()).any().any():
            raise ContractError("An expert targets an unobserved instrument")
        evaluation_start = pd.Timestamp(expert["evaluation_start"])
        if (
            pd.isna(evaluation_start)
            or evaluation_start.tzinfo is not None
            or not prices.index.min() <= evaluation_start <= prices.index.max()
        ):
            raise ContractError("Invalid evaluation start")
        targets[name] = weights
    if manifest["primary_expert"] not in targets:
        raise ContractError("Missing declared primary expert")
    primaries = [e["id"] for e in manifest["experts"] if e.get("role") == "primary"]
    if primaries != [manifest["primary_expert"]]:
        raise ContractError("Exactly one primary role must match the declared primary")
    if not targets or str(prices.index.max().date()) != manifest["data_end"]:
        raise ContractError("Missing experts or incorrect data endpoint")
    terminals = []
    if "terminal_events.json" in manifest["artifacts"]:
        from portfolio_lab.corporate_actions import terminal_records

        terminals = json.loads((path / "terminal_events.json").read_text())
        terminal_records(terminals, prices.columns, prices.index)
    if manifest["system"] == "fundamental-event-trader":
        if not {"qualification.json", "terminal_events.json"} <= manifest["artifacts"].keys():
            raise ContractError("Event specialist requires data/research and terminal evidence")
        admission = json.loads((path / "qualification.json").read_text())
        if (not isinstance(manifest["source_inputs"], dict)
                or admission.get("qualified_real_dataset") is not True
                or admission.get("native_research_audit") != "passed_research_integrity"
                or admission.get("fixture_only") is not False
                or admission.get("data_kind") != "real_historical"
                or admission.get("portfolio_allocation_allowed") is not False
                or admission.get("automatic_promotion_allowed") is not False
                or admission.get("code_sha256") != manifest["code_sha256"]
                or admission.get("dataset_manifest_sha256") != manifest["source_inputs"].get("dataset_manifest")
                or admission.get("research_manifest_sha256") != manifest["source_inputs"].get("research_manifest")):
            raise ContractError("Event specialist has not passed comparative research admission")
    return Bundle(path, manifest, prices, targets, cash, terminals)


def load_panel(paths: list[Path]) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], pd.Series, dict]:
    bundles = [load_bundle(p) for p in paths]
    systems = [b.manifest["system"] for b in bundles]
    if len(set(systems)) != len(systems):
        raise ContractError("Duplicate specialist systems")
    end = min(b.prices.index.max() for b in bundles)
    start = max(pd.Timestamp(e["evaluation_start"]) for b in bundles for e in b.manifest["experts"])
    # Use observed benchmark sessions, not a business-day calendar that invents holidays.
    reference = (
        next(b for b in bundles if b.manifest["system"] == "rotation-trader")
        if "rotation-trader" in systems
        else bundles[0]
    )
    index = reference.prices.loc[start:end].index
    if len(index) < 252:
        raise ContractError("Insufficient common history")
    targets, experts = {}, {}
    for b in bundles:
        if not index.isin(b.prices.index).all():
            raise ContractError(
                f"Missing sessions in {b.manifest['system']}; no zero-return substitution"
            )
        for e in b.manifest["experts"]:
            if e["id"] in targets:
                raise ContractError("Expert ids must be globally unique")
            targets[e["id"]] = b.targets[e["id"]].reindex(index)
            experts[e["id"]] = {**e, "system": b.manifest["system"]}
    instruments = sorted(set().union(*(set(w) for w in targets.values())) | {"SPY", "QQQ"})
    price_columns = {}
    source_rows = []
    for ticker in instruments:
        candidates = [
            b for b in bundles if ticker in b.prices and b.prices.loc[index, ticker].notna().any()
        ]
        if not candidates:
            raise ContractError(f"No price source for {ticker}")
        # A single captured source per instrument avoids splicing revised adjustment levels.
        chosen = max(candidates, key=lambda b: b.prices.loc[index, ticker].notna().sum())
        price_columns[ticker] = chosen.prices.loc[index, ticker]
        disagreements = []
        for b in candidates:
            diff = (
                b.prices.loc[index, ticker]
                .pct_change(fill_method=None)
                .sub(price_columns[ticker].pct_change(fill_method=None))
                .abs()
                .dropna()
            )
            disagreements.append(float(diff.max()) if len(diff) else 0.0)
        source_rows.append(
            {
                "ticker": ticker,
                "system": chosen.manifest["system"],
                "maximum_cross_source_return_difference": max(disagreements),
            }
        )
        if max(disagreements) > 0.03:
            raise ContractError(f"Material source disagreement for {ticker}")
    prices = pd.DataFrame(price_columns, index=index)
    cash = reference.cash_returns.reindex(index)
    if cash.isna().any():
        raise ContractError("Missing common cash yield")
    meta = {
        "experts": experts,
        "sources": source_rows,
        "bundles": [b.manifest for b in bundles],
        "bundle_sha256": [digest(b.root / "manifest.json") for b in bundles],
        "common_start": str(index.min().date()),
        "common_end": str(index.max().date()),
        "terminal_events": [],
    }
    terminal_by_security = {}
    for bundle in bundles:
        for record in bundle.terminal_events:
            if record["security_id"] not in instruments or pd.Timestamp(record["settlement_session"]) not in index:
                continue
            security = record["security_id"]
            chosen_system = next(row["system"] for row in source_rows if row["ticker"] == security)
            if chosen_system != bundle.manifest["system"]:
                prior = index.get_loc(pd.Timestamp(record["settlement_session"])) - 1
                if prior < 0:
                    raise ContractError("Terminal cash has no common pre-settlement price basis")
                owner_price = bundle.prices.loc[index[prior], security]
                chosen_price = price_columns[security].loc[index[prior]]
                if not np.isfinite(owner_price) or not np.isclose(owner_price, chosen_price, rtol=1e-8, atol=1e-10):
                    raise ContractError("Terminal cash and selected price source use different adjusted-share units")
            if security in terminal_by_security and terminal_by_security[security] != record:
                raise ContractError("Conflicting cross-specialist terminal cash evidence")
            terminal_by_security[security] = record
    meta["terminal_events"] = list(terminal_by_security.values())
    return prices, targets, cash, meta
