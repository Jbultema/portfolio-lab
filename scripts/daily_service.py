"""Installable scheduler for the same pipeline used by the dashboard button."""

import argparse
import os
import plistlib
import subprocess
from pathlib import Path


def payload(root):
    return {"Label": "com.jbultema.portfolio-lab.daily", "WorkingDirectory": str(root),
            "ProgramArguments": [str(root / ".venv/bin/python"), "-m", "portfolio_lab.operations", "tick", "--workspace", str(root)],
            "EnvironmentVariables": {"PYTHONPATH": str(root / "src")}, "StartInterval": 900,
            "RunAtLoad": False, "ProcessType": "Background",
            "StandardOutPath": str(root / "reports/operations/service.log"),
            "StandardErrorPath": str(root / "reports/operations/service-error.log")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-plist", type=Path)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.emit_plist or Path.home() / "Library/LaunchAgents/com.jbultema.portfolio-lab.daily.plist"
    if output.exists() and not args.install:
        raise FileExistsError("Refusing to overwrite an existing scheduler definition")
    (root / "reports/operations").mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(plistlib.dumps(payload(root)))
    if args.install:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/com.jbultema.portfolio-lab.daily"], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(output)], check=True)
    print(output)


if __name__ == "__main__":
    main()
