from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from portfolio_lab.audit import audit, evaluate_shadow, record_shadow
from portfolio_lab.contracts import load_panel
from portfolio_lab.research import run


def export_all(repos_root: Path, destination: Path) -> list[Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    paths = []
    for repo, module in (
        ("trade-bot", "trade_bot.research.portfolio_export"),
        ("swing-trader", "swing_trader.portfolio_export"),
        ("rotation-trader", "rotation_trader.portfolio_export"),
    ):
        root = repos_root / repo
        output = (destination / stamp / repo).resolve()
        interpreter = root / ".venv/bin/python"
        if not interpreter.is_file():
            raise ValueError(f"Missing isolated interpreter: {interpreter}")
        subprocess.run(
            [str(interpreter), "-m", module, "--output", str(output)],
            cwd=root,
            check=True,
            timeout=240,
        )
        paths.append(output)
    event_root = repos_root / "fundamental-event-trader"
    if (event_root / "data/runtime.json").is_file():
        output = (destination / stamp / "fundamental-event-trader").resolve()
        subprocess.run([str(event_root / ".venv/bin/python"), "-m", "fundamental_event_trader.portfolio_export", "--output", str(output)],
                       cwd=event_root, check=True, timeout=240)
        paths.append(output)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Personal portfolio research; no orders or promotion"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("research", "daily"):
        p = sub.add_parser(name)
        p.add_argument("--bundle", type=Path, action="append", default=[])
        p.add_argument("--repos-root", type=Path, default=Path("..").resolve())
        p.add_argument("--output", type=Path)
    p = sub.add_parser("export-all")
    p.add_argument("--repos-root", type=Path, default=Path("..").resolve())
    p.add_argument("--destination", type=Path, default=Path("data/bundles"))
    for name in ("audit", "record-shadow"):
        p = sub.add_parser(name)
        p.add_argument("--report", type=Path, required=True)
    p = sub.add_parser("evaluate-shadow")
    p.add_argument("--journal", type=Path, required=True)
    p.add_argument("--bundle", type=Path, action="append", required=True)
    for name in ("brief-replay", "brief-daily"):
        p = sub.add_parser(name, help="Read-only market interpretation; never reselects strategies")
        p.add_argument("--bundle", type=Path, action="append", default=[])
        p.add_argument("--telemetry", type=Path)
        p.add_argument("--repos-root", type=Path, default=Path("..").resolve())
        p.add_argument("--output", type=Path)
        p.add_argument("--sessions", type=int, default=40)
    p = sub.add_parser("brief-audit")
    p.add_argument("--report", type=Path, required=True)
    p = sub.add_parser("brief-handoff")
    p.add_argument("--pack", type=Path, required=True)
    p = sub.add_parser("brief-review")
    p.add_argument("--pack", type=Path, required=True)
    p.add_argument("--result", type=Path, required=True)
    p = sub.add_parser("brief-attach")
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--session", required=True)
    p.add_argument("--result", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "brief-handoff":
        from portfolio_lab.brief_agent import handoff

        print(json.dumps(handoff(json.loads(args.pack.read_text())), indent=2))
    elif args.command == "brief-attach":
        from portfolio_lab.brief_agent import attach_review

        print(attach_review(args.report, args.session, args.result, args.output))
    elif args.command == "brief-review":
        from portfolio_lab.brief_agent import accept_local_result

        print(json.dumps(accept_local_result(json.loads(args.pack.read_text()), args.result)[0], indent=2))
    elif args.command == "brief-audit":
        from portfolio_lab.briefing import verify_replay

        checked = verify_replay(args.report)
        print(json.dumps({"status": "passed", "sessions": len(checked["sessions"]), "action_authorized": False}))
    elif args.command in {"brief-replay", "brief-daily"}:
        from portfolio_lab.brief_runner import run_briefs

        print(run_briefs(args))
    elif args.command == "export-all":
        print(json.dumps([str(p) for p in export_all(args.repos_root, args.destination)]))
    elif args.command in {"research", "daily"}:
        paths = args.bundle or export_all(args.repos_root, Path("data/bundles"))
        output = args.output or Path("reports/runs") / datetime.now(UTC).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        print(run(paths, output))
        status = audit(output)
        print(json.dumps(status))
        if status["errors"]:
            raise SystemExit(2)
        Path("reports").mkdir(exist_ok=True)
        temporary = Path("reports/latest.tmp")
        temporary.write_text(json.dumps({"report": str(output.resolve())}) + "\n")
        temporary.replace("reports/latest.json")
        if args.command == "daily":
            print(record_shadow(output, Path("data/shadow")))
    elif args.command == "audit":
        status = audit(args.report)
        print(json.dumps(status, indent=2))
        if status["errors"]:
            raise SystemExit(2)
    elif args.command == "evaluate-shadow":
        prices, _, cash, meta = load_panel(args.bundle)
        print(json.dumps(evaluate_shadow(args.journal, prices, cash, terminal_events=meta["terminal_events"]), indent=2))
    else:
        print(record_shadow(args.report, Path("data/shadow")))


if __name__ == "__main__":
    main()
