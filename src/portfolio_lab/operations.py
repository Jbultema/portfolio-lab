"""One local orchestration entry point. No orders, model search or promotion."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from portfolio_lab.briefing import completed_sessions, verify_replay
from portfolio_lab.contracts import ContractError, digest, load_bundle

SYSTEMS = ("trade-bot", "swing-trader", "rotation-trader", "fundamental-event-trader", "position-bot")
CORE = SYSTEMS[:3]
TERMINAL = {"completed", "degraded", "failed", "cancelled"}


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def roots(workspace):
    config = workspace / "data/operations_config.json"
    values = json.loads(config.read_text()).get("repositories", {}) if config.exists() else {}
    output = {}
    for name in SYSTEMS:
        candidate = Path(values.get(name, workspace.parent / name)).expanduser().resolve()
        if not candidate.exists() and name == "position-bot":
            candidate = Path.home() / "repos/position-bot"
        output[name] = candidate
    return output


def store(workspace):
    return workspace / "reports/operations"


def job_file(workspace, job):
    if not isinstance(job, str) or len(job) != 32 or any(c not in "0123456789abcdef" for c in job):
        raise ContractError("Invalid local job identifier")
    return store(workspace) / "jobs" / job / "job.json"


def read_job(workspace, job):
    return json.loads(job_file(workspace, job).read_text())


def active(workspace):
    lock = store(workspace) / "active.json"
    if not lock.exists():
        return None
    try:
        job = json.loads(lock.read_text())["job_id"]
    except (json.JSONDecodeError, KeyError):
        return {"status": "starting", "job_id": None}
    payload = read_job(workspace, job)
    if payload["status"] in TERMINAL:
        return None
    pid = payload.get("pid")
    elapsed = (datetime.now(UTC) - datetime.fromisoformat(payload["created_at_utc"])).total_seconds()
    if pid:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=False)
        alive = result.returncode == 0 and "portfolio_lab.operations" in result.stdout and job in result.stdout
    else:
        alive = elapsed < 120
    if not alive:
        payload |= {"status": "failed", "error": "Worker exited without a terminal receipt", "finished_at_utc": datetime.now(UTC).isoformat()}
        atomic(job_file(workspace, job), payload)
        return None
    return payload


def start(workspace, *, refresh=True, launch=True):
    workspace = Path(workspace).resolve()
    store(workspace).mkdir(parents=True, exist_ok=True)
    with (store(workspace) / ".launcher.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        return _start(workspace, refresh=refresh, launch=launch)


def _start(workspace, *, refresh=True, launch=True):
    workspace = Path(workspace).resolve()
    current = active(workspace)
    if current:
        return current
    root = store(workspace)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "active.json"
    # File creation is the cross-process exclusion boundary, not a Streamlit session flag.
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        prior = json.loads(lock.read_text())
        state = read_job(workspace, prior["job_id"])
        if state["status"] not in TERMINAL:
            return state
        lock.unlink()
        return _start(workspace, refresh=refresh, launch=launch)
    job = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    payload = {"schema_version": 1, "job_id": job, "status": "queued", "created_at_utc": now,
               "heartbeat_at_utc": now, "expected_session": str(completed_sessions(1)[-1].date()),
               "refresh": refresh, "stages": [], "action_authorized": False,
               "strategy_search_allowed": False, "automatic_promotion_allowed": False}
    atomic(job_file(workspace, job), payload)
    with os.fdopen(fd, "w") as handle:
        json.dump({"job_id": job}, handle)
    atomic(root / "latest.json", {"job_id": job})
    if launch:
        try:
            log = job_file(workspace, job).parent / "worker.log"
            with log.open("ab") as output:
                child = subprocess.Popen([sys.executable, "-m", "portfolio_lab.operations", "worker", "--workspace", str(workspace), "--job", job],
                    cwd=workspace, env=os.environ | {"PYTHONPATH": str(workspace / "src")},
                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            # Worker owns subsequent state changes. PID lives in the independent lock receipt.
            atomic(root / f"worker-{job}.json", {"pid": child.pid})
        except OSError as exc:
            payload |= {"status": "failed", "error": f"Worker launch failed: {type(exc).__name__}"}
            atomic(job_file(workspace, job), payload)
    return read_job(workspace, job)


def commands(name, root, destination, refresh, workspace):
    python = str(root / ".venv/bin/python")
    if name == "trade-bot":
        return [[python, "-m", "trade_bot.cli", "run-daily-update",
                 *([] if refresh else ["--cached-data", "--cached-macro", "--cached-news"])]]
    if name in {"swing-trader", "rotation-trader"}:
        return [[python, str(workspace / "src/portfolio_lab/native_daily.py"), "--system", name,
                 "--output", str(destination), *(["--refresh"] if refresh else [])]]
    if name == "fundamental-event-trader":
        return [[python, "-m", "fundamental_event_trader.cli", "daily", "--output", str(destination),
                 *(["--refresh-news"] if refresh else [])]]
    if name == "position-bot":
        capture = []
        if refresh:
            from_json = root / "data/latest.json"
            seed = []
            if from_json.exists():
                pointer = json.loads(from_json.read_text())
                seed = ["--seed-raw", str(Path(pointer["report"]) / "raw")]
            capture = [[python, "-m", "position_bot.cli", "fetch-data", "--refresh", *seed]]
        return [*capture, [python, "-m", "position_bot.cli", "daily"]]
    raise ContractError("Unknown native daily provider")


def execute(command, cwd, log, payload, stage, state_file, *, timeout=1800):
    environment = os.environ | {"PYTHONPATH": str(cwd / "src")}
    with log.open("ab") as output:
        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        began = time.monotonic()
        try:
            while process.poll() is None:
                if state_file.with_name("cancel.request").exists():
                    raise InterruptedError("Cancelled by user")
                if time.monotonic() - began > timeout:
                    raise TimeoutError("Native update exceeded its execution deadline")
                payload["heartbeat_at_utc"] = datetime.now(UTC).isoformat()
                atomic(state_file, payload)
                time.sleep(2)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    stage["exit_code"] = process.returncode
    if process.returncode:
        if stage["system"] == "fundamental-event-trader" and process.returncode == 2:
            from portfolio_lab.event_context import validate_context

            status_path = state_file.parent / "fundamental-event-trader/status.json"
            manifest_path = status_path.parent / "manifest.json"
            if status_path.is_file() and manifest_path.is_file():
                meta = json.loads(manifest_path.read_text())
                if (meta.get("system") == "fundamental-event-trader"
                        and meta.get("artifacts", {}).get("status.json") == digest(status_path)):
                    value = validate_context(json.loads(status_path.read_text()))
                    if value["status"] == "blocked":
                        stage["readiness"] = "blocked_no_allocation_authority"
                        return
        raise ContractError(f"Native update failed with exit {process.returncode}; inspect its log")


def worker(workspace, job, executor=execute):
    guard_file = job_file(Path(workspace), job).with_name("worker.lock")
    with guard_file.open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ContractError("Daily worker is already executing") from exc
        return _worker(workspace, job, executor)


def _worker(workspace, job, executor):
    workspace = Path(workspace).resolve()
    state_file = job_file(workspace, job)
    payload = read_job(workspace, job)
    if payload["status"] != "queued":
        raise ContractError("A daily job can execute only once")
    payload |= {"pid": os.getpid(), "status": "running", "started_at_utc": datetime.now(UTC).isoformat()}
    atomic(state_file, payload)
    repositories = roots(workspace)
    failures = []
    try:
        for name in SYSTEMS:
            stage = {"system": name, "status": "running", "started_at_utc": datetime.now(UTC).isoformat(),
                     "log": str(state_file.parent / f"{name}.log")}
            payload["stages"].append(stage)
            atomic(state_file, payload)
            try:
                root = repositories[name]
                if not (root / ".venv/bin/python").is_file():
                    raise ContractError("Native interpreter unavailable")
                for command in commands(name, root, state_file.parent / name, payload["refresh"], workspace):
                    executor(command, root, Path(stage["log"]), payload, stage, state_file)
                stage["status"] = "completed"
            except InterruptedError:
                stage["status"] = "cancelled"
                raise
            except (OSError, ValueError, subprocess.SubprocessError, TimeoutError) as exc:
                stage |= {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                failures.append(name)
            stage["finished_at_utc"] = datetime.now(UTC).isoformat()
            atomic(state_file, payload)
        if any(name in failures for name in CORE):
            raise ContractError("Core update failed; previous complete report retained")
        if state_file.with_name("cancel.request").exists():
            raise InterruptedError("Cancelled before export")
        bundles, health = capture_local_bundles_from_roots(repositories, state_file.parent / "bundles")
        if len(bundles) != 3 or any(load_bundle(b).manifest["data_end"] != payload["expected_session"] for b in bundles):
            raise ContractError("Core exports are not synchronized to the requested completed session")
        payload["export_health"] = health
        # The archive is built to an explicit path; run_briefs atomically changes the live pointer only after verification.
        from types import SimpleNamespace

        from portfolio_lab.brief_runner import run_briefs
        from portfolio_lab.briefing import collect_telemetry

        telemetry = state_file.parent / "telemetry"
        paths = collect_telemetry(bundles, workspace.parent, telemetry, repositories=repositories)
        if len(paths) != 3:
            raise ContractError("Core telemetry incomplete; previous complete report retained")
        for name, filename in (("position-bot", "position_bot.json"), ("fundamental-event-trader", "fundamental_event.json")):
            context_file = telemetry / filename
            value = json.loads(context_file.read_text()) if context_file.exists() else {"status": "unavailable"}
            bad = value.get("status") == "unavailable"
            if name == "position-bot":
                bad |= (value.get("as_of_session") != payload["expected_session"]
                        or not value.get("prices_fresh") or not value.get("positioning_fresh"))
            if bad and name not in failures:
                failures.append(name)
        for path in paths:
            name = json.loads((path / "manifest.json").read_text())["system"]
            signals = pd.read_parquet(telemetry / name / "signals.parquet")
            if str(signals.index[-1].date()) != payload["expected_session"]:
                raise ContractError("Native telemetry stale; previous complete report retained")
        if state_file.with_name("cancel.request").exists():
            raise InterruptedError("Cancelled before publication")
        args = SimpleNamespace(bundle=paths, telemetry=telemetry, repos_root=workspace.parent, output=state_file.parent / "report", sessions=40, publish=not failures, required_session=payload["expected_session"])
        report = run_briefs(args)
        checked = verify_replay(report)
        if checked["sessions"][-1] != payload["expected_session"]:
            raise ContractError("Published session disagrees with synchronized daily job")
        payload |= {"status": "degraded" if failures else "completed", "report": str(report.resolve()),
                    "report_manifest_sha256": digest(report / "manifest.json"), "failed_systems": failures,
                    "synchronized_session": payload["expected_session"]}
        if not failures:
            atomic(store(workspace) / "last_complete.json", {"job_id": job, "session": payload["expected_session"],
                                                          "report": str(report.resolve()), "manifest_sha256": digest(report / "manifest.json")})
    except InterruptedError:
        payload["status"] = "cancelled"
    except Exception as exc:
        payload |= {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        payload["finished_at_utc"] = datetime.now(UTC).isoformat()
        atomic(state_file, payload)
    return payload


def capture_local_bundles_from_roots(repositories, destination):
    from portfolio_lab.brief_runner import PROVIDERS

    paths, health = [], {}
    for name, module in PROVIDERS.items():
        root = repositories[name]
        output = (destination / name).resolve()
        try:
            subprocess.run([str(root / ".venv/bin/python"), "-m", module, "--output", str(output)],
                cwd=root, env=os.environ | {"PYTHONPATH": str(root / "src")}, timeout=300, check=True, capture_output=True)
            paths.append(output)
            health[name] = {"status": "captured"}
        except (OSError, subprocess.SubprocessError) as exc:
            health[name] = {"status": "failed", "error_type": type(exc).__name__}
    return paths, health


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "start", "worker", "status", "cancel"])
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--job")
    parser.add_argument("--cached", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    os.chdir(workspace)
    if args.command in {"run", "start"}:
        result = start(workspace, refresh=not args.cached, launch=args.command != "run")
        if args.command == "run" and result["status"] == "queued":
            result = worker(workspace, result["job_id"])
        print(json.dumps(result, indent=2))
        if result["status"] in {"failed", "degraded"}:
            raise SystemExit(2)
    elif args.command == "worker":
        result = worker(workspace, args.job)
        if result["status"] != "completed":
            raise SystemExit(2)
    elif args.command == "cancel":
        path = job_file(workspace, args.job)
        path.with_name("cancel.request").touch(exist_ok=True)
    else:
        print(json.dumps(active(workspace) or {"status": "idle"}, indent=2))


if __name__ == "__main__":
    main()
