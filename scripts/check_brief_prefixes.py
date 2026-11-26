"""Exhaustive last-N native telemetry prefix check using each isolated runtime."""

import argparse
import hashlib
import importlib
import json
import subprocess
from pathlib import Path

import pandas as pd


def worker(system, bundle, count, output):
    if system == "trade-bot":
        module = importlib.import_module("trade_bot.research.interpretation_export")
        config = module.load_config("configs/baseline.yaml")
        setting = config.strategies[config.primary_strategy]
        def calculate(frame):
            return module.signals(frame, setting)
    elif system == "swing-trader":
        module = importlib.import_module("swing_trader.interpretation_export")
        setting = module.load_config("config/default.toml")
        def calculate(frame):
            return module.signals(frame, setting)
    else:
        module = importlib.import_module("rotation_trader.interpretation_export")
        setting = module.load_config("config/default.toml")
        spec = json.loads(Path("reports/latest/research_summary.json").read_text())["selected_specification"]
        def calculate(frame):
            return module.signals(frame, setting, spec)
    prices = pd.read_parquet(bundle / "prices.parquet")
    full = calculate(prices)
    results = []
    for date in prices.index[-count:]:
        prefix = calculate(prices.loc[:date])
        pd.testing.assert_frame_equal(full.loc[:date], prefix, check_freq=False)
        results.append({"session": str(date.date()), "passed": True})
        print(f"{system} prefix {date.date()} passed", flush=True)
    output.write_text(json.dumps({"system": system, "checks": results,
                                  "adapter_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
                                  "bundle_manifest_sha256": hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()}, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundles", type=Path)
    p.add_argument("--repos-root", type=Path, default=Path("..").resolve())
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--worker", choices=["trade-bot", "swing-trader", "rotation-trader"])
    p.add_argument("--bundle", type=Path)
    args = p.parse_args()
    if args.worker:
        worker(args.worker, args.bundle, args.count, args.output)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    for system in ("trade-bot", "swing-trader", "rotation-trader"):
        root = args.repos_root / system
        subprocess.run([str(root / ".venv/bin/python"), str(Path(__file__).resolve()),
                        "--worker", system, "--bundle", str((args.bundles / system).resolve()),
                        "--count", str(args.count), "--output", str((args.output / f"{system}.json").resolve())],
                       cwd=root, check=True, timeout=1800)


if __name__ == "__main__":
    main()
