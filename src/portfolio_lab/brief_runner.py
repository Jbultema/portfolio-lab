"""Fail-closed local daily runner, atomic publication and immutable dated archives."""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from portfolio_lab.briefing import (
    collect_telemetry,
    interpretation_hash,
    publish_replay,
    verify_replay,
)
from portfolio_lab.contracts import ContractError, digest

PROVIDERS = {
    "trade-bot": "trade_bot.research.portfolio_export",
    "swing-trader": "swing_trader.portfolio_export",
    "rotation-trader": "rotation_trader.portfolio_export",
}


def capture_local_bundles(repos_root: Path, destination: Path) -> tuple[list[Path], dict]:
    """Provider failures are health facts, not cash signals or erased fresh evidence."""
    paths, health = [], {}
    for name, module in PROVIDERS.items():
        root = repos_root / name
        output = (destination / name).resolve()
        try:
            subprocess.run([str(root / ".venv/bin/python"), "-m", module, "--output", str(output)],
                           cwd=root, check=True, timeout=240, capture_output=True, text=True)
            paths.append(output)
            health[name] = {"status": "captured"}
        except (OSError, subprocess.SubprocessError) as exc:
            health[name] = {"status": "unavailable", "error_type": type(exc).__name__}
    if not paths:
        raise ContractError("No usable local specialist exports")
    return paths, health


def run_briefs(args):
    reports = Path("reports/market-desk")
    reports.mkdir(parents=True, exist_ok=True)
    lock = reports / ".writer.lock"
    try:
        handle = lock.open("x")
    except FileExistsError as exc:
        raise ContractError("Market Desk writer already active; inspect lock before recovery") from exc
    with handle:
        handle.write(json.dumps({"pid": os.getpid(), "started_at": datetime.now(UTC).isoformat()}))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    log = {"started_at": datetime.now(UTC).isoformat(), "status": "running", "action_authorized": False}
    try:
        initial_code = interpretation_hash()
        if args.bundle:
            paths, health = args.bundle, {"mode": "explicit_captured_bundles"}
        else:
            paths, health = capture_local_bundles(args.repos_root, Path("data/brief-bundles") / stamp)
        telemetry = args.telemetry or Path("data/brief-telemetry") / stamp
        if args.telemetry is None:
            paths = collect_telemetry(paths, args.repos_root, telemetry)
            (telemetry / "source_health.json").write_text(json.dumps(health, indent=2) + "\n")
        output = args.output or reports / "runs" / stamp
        publish_replay(paths, telemetry, output, count=args.sessions)
        manifest = verify_replay(output)
        if manifest["brief_code_sha256"] != initial_code or interpretation_hash() != initial_code:
            raise ContractError("Interpretation code changed during capture; prior publication retained")
        pointer = {"report": str(output.resolve()), "manifest_sha256": digest(output / "manifest.json"),
                   "last_session": manifest["sessions"][-1], "published_at": datetime.now(UTC).isoformat()}
        temporary = reports / f"latest-{stamp}.tmp"
        temporary.write_text(json.dumps(pointer, indent=2) + "\n")
        temporary.replace(reports / "latest.json")
        log |= {"status": "completed", "report": str(output), "sessions": len(manifest["sessions"])}
        return output
    except Exception as exc:
        log |= {"status": "failed", "error_type": type(exc).__name__}
        raise
    finally:
        log["finished_at"] = datetime.now(UTC).isoformat()
        (reports / "jobs").mkdir(exist_ok=True)
        (reports / "jobs" / f"{stamp}.json").write_text(json.dumps(log, indent=2) + "\n")
        lock.unlink(missing_ok=True)
