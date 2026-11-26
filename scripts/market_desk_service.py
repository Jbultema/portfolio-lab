"""Desk poller; may refresh public news. No model calls, strategy search or trades."""

import argparse
import json
import plistlib
import subprocess
from pathlib import Path

from portfolio_lab.briefing import completed_sessions, interpretation_hash, verify_replay
from portfolio_lab.contracts import digest
from portfolio_lab.event_context import current_fingerprint, fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-plist", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.emit_plist:
        payload = {"Label": "com.jbultema.portfolio-lab.market-desk",
                   "ProgramArguments": [str(root / ".venv/bin/python"), str(Path(__file__).resolve())],
                   "WorkingDirectory": str(root), "StartInterval": 900, "RunAtLoad": False,
                   "StandardOutPath": str(root / "reports/market-desk/service.log"),
                   "StandardErrorPath": str(root / "reports/market-desk/service-error.log"),
                   "ProcessType": "Background"}
        with args.emit_plist.open("xb") as handle:
            plistlib.dump(payload, handle)
        return
    pointer = root / "reports/market-desk/latest.json"
    expected = str(completed_sessions(1)[-1].date())
    if pointer.exists():
        config = json.loads(pointer.read_text())
        report = Path(config["report"])
        if digest(report / "manifest.json") != config["manifest_sha256"]:
            raise ValueError("Current archive pointer failed integrity")
        manifest = verify_replay(report)
        pack = json.loads((report / "sessions" / manifest["sessions"][-1] / "pack.json").read_text())
        if config["last_session"] == expected and manifest["brief_code_sha256"] == interpretation_hash() and pack["fresh_specialists"] == 3:
            event_file = report / "context/fundamental_event.json"
            event_root = root.parent / "fundamental-event-trader"
            unchanged_event = not (event_root / ".venv/bin/python").is_file()
            if event_file.is_file():
                unchanged_event = fingerprint(json.loads(event_file.read_text())) == current_fingerprint(event_root)
            if unchanged_event:
                print(json.dumps({"status": "already_current", "session": expected}), flush=True)
                return
    subprocess.run([str(root / ".venv/bin/portfolio-lab"), "brief-daily", "--repos-root", str(root.parent)], cwd=root, check=True, timeout=1200)


if __name__ == "__main__":
    main()
