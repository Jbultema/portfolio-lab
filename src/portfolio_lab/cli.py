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
    args = parser.parse_args()
    if args.command == "export-all":
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
        prices, _, cash, _ = load_panel(args.bundle)
        print(json.dumps(evaluate_shadow(args.journal, prices, cash), indent=2))
    else:
        print(record_shadow(args.report, Path("data/shadow")))


if __name__ == "__main__":
    main()
