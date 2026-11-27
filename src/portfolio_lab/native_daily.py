"""Native daily adapters: refresh data and rebuild frozen rules, never select strategies."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", choices=["swing-trader", "rotation-trader"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    if args.system == "swing-trader":
        from swing_trader.cli import _refresh_data_bundle
        from swing_trader.config import load_config
        from swing_trader.portfolio_export import export_bundle

        if args.refresh:
            _refresh_data_bundle(load_config("config/default.toml"), root / "data/raw/prices.parquet")
        export_bundle(args.output / "bundle")
    else:
        from rotation_trader.config import load_config
        from rotation_trader.data import download_price_snapshot
        from rotation_trader.portfolio_export import export_bundle

        manifest = None
        if args.refresh:
            snapshot = download_price_snapshot(load_config("config/default.toml").data, root / "data/raw/prices")
            manifest = snapshot.manifest_path
        export_bundle(args.output / "bundle", price_manifest=manifest)
    bundle = args.output / "bundle"
    metadata = json.loads((bundle / "manifest.json").read_text())
    payload = {"system": args.system, "as_of_session": metadata["data_end"],
               "captured_at_utc": datetime.now(UTC).isoformat(), "bundle": str(bundle.resolve()),
               "strategy_search_performed": False, "action_authorized": False}
    if args.system == "rotation-trader" and manifest is not None:
        from rotation_trader.provenance import file_sha256

        payload |= {"price_manifest": str(manifest.resolve()), "price_manifest_sha256": file_sha256(manifest),
                    "frozen_research_sha256": file_sha256(root / "reports/latest/run_manifest.json")}
    output = root / "reports/frozen-daily/latest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(output)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
