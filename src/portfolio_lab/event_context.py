"""Optional event specialist: operational evidence, never a missing-data market vote."""

import json
import math
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd

from portfolio_lab.contracts import ContractError


def validate_context(payload):
    if (not isinstance(payload, dict) or payload.get("schema_version") != 2 or payload.get("system") != "fundamental-event-trader"
            or payload.get("action_authorized") is not False
            or payload.get("portfolio_allocation_allowed") is not False
            or payload.get("automatic_promotion_allowed") is not False
            or payload.get("authority") != "research_only"
            or payload.get("status") not in {"blocked", "unavailable", "research_shadow", "stale_research"}):
        raise ContractError("Unqualified event interpretation context")
    captured = pd.Timestamp(payload.get("captured_at_utc"))
    if pd.isna(captured) or captured.tzinfo is None:
        raise ContractError("Ambiguous event capture time")
    weights = payload.get("target_holdings", {})
    if (not isinstance(weights, dict)
            or any(not isinstance(k, str) or not k for k in weights)
            or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in weights.values())
            or sum(weights.values()) > 1 + 1e-10):
        raise ContractError("Invalid event target weights")
    if payload["status"] in {"blocked", "unavailable"} and payload.get("target_holdings"):
        raise ContractError("Blocked event specialist cannot publish a usable target")
    for row in payload.get("recent_events", []):
        if not isinstance(row, dict) or not {"security_id", "cik", "accession", "available_at", "score", "source_sha256"} <= row.keys():
            raise ContractError("Incomplete source-bound event observation")
        stamp = pd.Timestamp(row["available_at"])
        if pd.isna(stamp) or stamp.tzinfo is None or captured.tzinfo is None or stamp > captured:
            raise ContractError("Future or ambiguous event evidence")
        if (isinstance(row["score"], bool) or not isinstance(row["score"], (float, int))
                or not math.isfinite(row["score"])
                or not isinstance(row["source_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
                or not isinstance(row["accession"], str)
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row["accession"])):
            raise ContractError("Invalid source-bound event observation")
    shadow = payload.get("prospective_shadow", {})
    if not isinstance(shadow, dict) or (shadow and (shadow.get("action_authorized") is not False or shadow.get("automatic_promotion_allowed") is not False
                   or shadow.get("profitability_established") is not False)):
        raise ContractError("Prospective observation count cannot confer trading authority or alpha")
    outcomes = payload.get("prospective_outcomes", {})
    if not isinstance(outcomes, dict) or (outcomes and (outcomes.get("action_authorized") is not False or outcomes.get("automatic_promotion_allowed") is not False)):
        raise ContractError("Shadow marks cannot authorize an allocation")
    news = payload.get("news", {})
    if news:
        if (not isinstance(news, dict) or news.get("schema_version") != 1 or news.get("authority") != "observation_only"
                or news.get("action_authorized") is not False or news.get("historical_strategy_evidence") is not False):
            raise ContractError("News coverage cannot confer strategy or allocation authority")
        if not isinstance(news.get("items"), list) or any(not isinstance(row, dict) for row in news["items"]):
            raise ContractError("Malformed current-news observations")
        if news["items"]:
            news_capture = pd.Timestamp(news.get("captured_at_utc"))
            if pd.isna(news_capture) or news_capture.tzinfo is None or news_capture > captured:
                raise ContractError("Future or ambiguous news capture")
        for row in news.get("items", []):
            if not {"url", "published_at_utc", "available_at_utc", "first_seen_at_utc", "version_first_seen_at_utc"} <= row.keys():
                raise ContractError("Incomplete news timing evidence")
            pub, available, first, version = (pd.Timestamp(row[k]) for k in
                                             ("published_at_utc", "available_at_utc", "first_seen_at_utc", "version_first_seen_at_utc"))
            if any(pd.isna(stamp) or stamp.tzinfo is None for stamp in (pub, available, first, version)) or not (pub <= available <= captured and first <= version <= available):
                raise ContractError("News version or first-observation timestamps are not causal")
            link = urlsplit(row["url"])
            if link.scheme != "https" or link.username or link.password or not link.hostname:
                raise ContractError("Unsafe news source URL")
    return payload


def unavailable(error):
    return {"schema_version": 2, "system": "fundamental-event-trader", "status": "unavailable",
            "stage": "unavailable", "captured_at_utc": datetime.now(UTC).isoformat(),
            "authority": "research_only", "action_authorized": False, "portfolio_allocation_allowed": False,
            "automatic_promotion_allowed": False, "registered_hypotheses": None, "tested_on_real_data": None,
            "target_holdings": {}, "recent_events": [], "criteria": [], "performance": [],
            "source_access": {}, "errors": [error], "remaining_gates": ["Restore verified specialist capture"]}


def fingerprint(payload):
    keys = ("status", "as_of_session", "code_sha256", "dataset_manifest_sha256", "research_manifest_sha256", "errors")
    shadow = payload.get("prospective_shadow", {})
    news = payload.get("news", {})
    return {**{key: payload.get(key) for key in keys}, "source_manifest": payload.get("source_access", {}).get("manifest_sha256"),
            "shadow_record": shadow.get("latest_record_sha256"), "shadow_status": shadow.get("status"),
            "shadow_consecutive_sessions": shadow.get("consecutive_sessions"),
            "news_manifest": news.get("manifest_sha256"), "news_refresh_due": news.get("refresh_due"),
            "news_status": news.get("status"), "news_attempt": news.get("latest_attempt_manifest_sha256")}


def current_fingerprint(root):
    try:
        result = subprocess.run([str(root / ".venv/bin/python"), "-m", "fundamental_event_trader.cli", "status"],
                                cwd=root, env=os.environ | {"PYTHONPATH": str((root / "src").resolve())},
                                capture_output=True, text=True, timeout=120)
        if result.returncode not in (0, 2):
            raise ContractError("qualification_check_failed")
        payload = validate_context(json.loads(result.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        payload = unavailable("qualification_check_failed")
    return fingerprint(payload)


def archive_news(payload, root: Path, destination: Path):
    from portfolio_lab.contracts import digest

    news = payload.get("news", {})
    if not news.get("manifest_sha256"):
        return {}
    folder = Path(news["archive_report"]).resolve()
    if not folder.is_relative_to((root / "data/news/captures").resolve()):
        raise ContractError("News evidence outside the dedicated public-news archive")
    manifest = folder / "manifest.json"
    if digest(manifest) != news["manifest_sha256"]:
        raise ContractError("News evidence manifest mismatch")
    meta = json.loads(manifest.read_text())
    if meta.get("kind") != "public_news_observation" or meta.get("historical_strategy_evidence") is not False or meta.get("action_authorized") is not False:
        raise ContractError("News archive cannot confer portfolio authority")
    files = {"manifest.json": digest(manifest), **meta["artifacts"]}
    total, mapping = 0, {}
    if len(files) > 1000:
        raise ContractError("Excessive news evidence file count")
    for name, expected in files.items():
        file = (folder / name).resolve()
        if not file.is_relative_to(folder) or not file.is_file() or digest(file) != expected:
            raise ContractError("News evidence file integrity failure")
        total += file.stat().st_size
        if total > 50_000_000:
            raise ContractError("News evidence exceeds local archive limit")
        relative = str(Path("fundamental-news") / name)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        mapping[relative] = expected
    return mapping


def capture(root: Path, *, destination: Path | None = None) -> dict:
    interpreter = root / ".venv/bin/python"
    if not interpreter.is_file():
        raise ContractError("Missing event specialist interpreter")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output = root / "reports/daily" / stamp
    result = subprocess.run([str(interpreter), "-m", "fundamental_event_trader.cli", "daily", "--output", str(output.resolve()), "--refresh-news"],
                            cwd=root, env=os.environ | {"PYTHONPATH": str((root / "src").resolve())},
                            capture_output=True, text=True, timeout=240)
    if result.returncode not in (0, 2):
        raise ContractError("Event specialist status command failed")
    meta = json.loads((output / "manifest.json").read_text())
    from portfolio_lab.contracts import digest

    if meta.get("action_authorized") is not False or meta.get("artifacts", {}).get("status.json") != digest(output / "status.json"):
        raise ContractError("Event daily observation integrity failure")
    payload = validate_context(json.loads((output / "status.json").read_text()))
    if destination is not None:
        payload["news_context_artifacts"] = archive_news(payload, root, destination)
    payload["daily_observation_manifest_sha256"] = digest(output / "manifest.json")
    return payload


def read(root: Path):
    file = root / "context/fundamental_event.json"
    if not file.is_file():
        return None
    payload = json.loads(file.read_text())
    # Older immutable archives legitimately contain only the original gate summary.
    if payload.get("schema_version") == 1:
        return payload
    return validate_context(payload)
