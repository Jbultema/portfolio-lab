"""Local verification of the five personal repos without refreshing data or trading."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

REPOSITORIES = (
    "trade-bot", "swing-trader", "rotation-trader", "portfolio-lab", "fundamental-event-trader"
)


def command(root: Path, args: list[str], *, timeout: int = 900) -> dict:
    try:
        result = subprocess.run(
            args, cwd=root, text=True, capture_output=True, timeout=timeout, check=False
        )
        return {
            "command": args, "exit_code": result.returncode,
            "stdout": result.stdout[-16000:], "stderr": result.stderr[-8000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"command": args, "exit_code": -1, "error": str(exc)}


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - sum(counts[k] for k in ("failures", "errors", "skipped"))
    return counts


def verify(root: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "scope": "local_software_verification_not_market_data_refresh_or_strategy_approval",
        "action_authorized": False, "remote_ci_verified": False, "repositories": {},
    }
    for name in REPOSITORIES:
        repo = root / name
        python = str(repo / ".venv/bin/python")
        checks = {}
        for key, args in (
            ("head", ["git", "rev-parse", "HEAD"]),
            ("worktree", ["git", "status", "--porcelain"]),
            ("whitespace", ["git", "diff", "--check", "HEAD"]),
            ("dependencies", [python, "-m", "pip", "check"]),
            ("lint", [python, "-m", "ruff", "check", "--no-cache", "src", "tests"]),
            ("tests", [python, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                       f"--junitxml={output / (name + '.xml')}"]),
        ):
            checks[key] = command(repo, args)
        junit = output / (name + ".xml")
        counts = junit_counts(junit) if junit.exists() else {}
        clean = not checks["worktree"].get("stdout", "").strip()
        passed = all(checks[k]["exit_code"] == 0 for k in checks)
        item = {"checks": checks, "test_counts": counts, "worktree_clean": clean,
                "local_checks_passed": passed}
        report["repositories"][name] = item
        print(f"{name}: {'PASS' if passed else 'FAIL'}, {counts}, clean={clean}", flush=True)
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    report["local_checks_passed"] = all(
        item["local_checks_passed"] for item in report["repositories"].values()
    )
    report["all_worktrees_clean"] = all(
        item["worktree_clean"] for item in report["repositories"].values()
    )
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.repos_root.resolve(), args.output.resolve())
    sys.exit(0 if report["local_checks_passed"] else 1)


if __name__ == "__main__":
    main()
