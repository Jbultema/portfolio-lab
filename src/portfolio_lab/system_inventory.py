"""Read-only canonical bot identities and personal-repository release readiness."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SYSTEMS = ("trade-bot", "swing-trader", "rotation-trader", "portfolio-lab", "fundamental-event-trader")
MODULES = {n: n.replace("-", "_") for n in SYSTEMS}


def redact_credentials(value):
    def clean(match):
        try:
            url = urlsplit(match.group())
            if url.username is not None or url.password is not None:
                host = url.hostname or "invalid"
                host += f":{url.port}" if url.port else ""
                return urlunsplit((url.scheme, "[redacted]@" + host, url.path, "", ""))
            if url.query or url.fragment:
                return urlunsplit((url.scheme, url.netloc, url.path, "[redacted]" if url.query else "", ""))
            return match.group()
        except ValueError:
            return "[redacted-invalid-url]"
    return re.sub(r"https?://[^\s]+", clean, value)


def command(root, args, timeout=60):
    try:
        result = subprocess.run(args, cwd=root, env=os.environ | {"PYTHONPATH": str(root / "src")}, text=True, capture_output=True, timeout=timeout, check=False)
        return {"exit_code": result.returncode, "stdout": redact_credentials(result.stdout.strip()), "stderr": redact_credentials(result.stderr[-2000:].strip())}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": -1, "stdout": "", "error": type(exc).__name__}


def personal_remote(url, name):
    return bool(re.fullmatch(rf"(?:git@(?:github\.com|github-personal):|https://github\.com/)Jbultema/{re.escape(name)}(?:\.git)?", url))


def validate_identity(value, expected):
    if (not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("system") != expected
            or value.get("action_authorized") is not False or value.get("portfolio_allocation_allowed") is not False
            or not isinstance(value.get("configuration_consistent"), bool)):
        raise ValueError("Invalid or authorized native identity")
    if expected == "fundamental-event-trader" and value.get("primary") is not None:
        raise ValueError("A broad event primary has not been admitted")
    if expected in {"trade-bot", "swing-trader", "rotation-trader"} and value["configuration_consistent"] and not value.get("primary"):
        raise ValueError("A consistent investable identity requires its actual primary")
    return value


def native_identity(root, name):
    if name == "portfolio-lab":
        return {"schema_version": 1, "system": name, "role": "comparison_and_accountability",
            "primary": None, "configuration_consistent": True, "primary_source": "native_bots_own_strategies",
            "action_authorized": False, "portfolio_allocation_allowed": False}
    result = command(root, [str(root / ".venv/bin/python"), "-m", MODULES[name] + ".system_identity"])
    if result["exit_code"]:
        return {"status": "unavailable", "reason": result.get("error", "native_identity_failed")}
    try:
        return validate_identity(json.loads(result["stdout"]), name)
    except (ValueError, TypeError):
        return {"status": "invalid", "reason": "native_identity_contract_failed"}


def inventory(repos_root):
    records = {}
    for name in SYSTEMS:
        root = repos_root / name
        checks = {key: command(root, args) for key, args in (
            ("head", ["git", "rev-parse", "HEAD"]),
            ("branch", ["git", "branch", "--show-current"]),
            ("status", ["git", "status", "--porcelain=v1", "-z"]),
            ("remotes", ["git", "remote", "-v"]),
            ("upstream", ["git", "rev-parse", "--abbrev-ref", "@{upstream}"]),
            ("divergence", ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"]),
            ("conflicts", ["git", "ls-files", "-u"]),
        )}
        remotes = [row.split()[1] for row in checks["remotes"]["stdout"].splitlines() if len(row.split()) == 3 and row.endswith("(push)")]
        identity = native_identity(root, name)
        valid_git = bool(checks["branch"]["stdout"]) and all(checks[k]["exit_code"] == 0 for k in ("head", "branch", "status", "remotes", "conflicts"))
        clean = valid_git and not checks["status"]["stdout"] and not checks["conflicts"]["stdout"]
        synced = checks["divergence"]["exit_code"] == 0 and checks["divergence"]["stdout"].split() == ["0", "0"]
        personal = bool(remotes) and all(personal_remote(url, name) for url in remotes)
        records[name] = {"git": checks, "native_identity": identity, "worktree_clean": clean,
            "upstream_synced": synced, "personal_push_remotes": personal,
            "local_checkpoint_ready": clean and synced and personal and identity.get("configuration_consistent") is True,
            "remote_refs_fetched_this_call": False, "remote_pr_or_ci_verified": False}
    return {"schema_version": 1, "captured_at_utc": datetime.now(UTC).isoformat(), "repositories": records,
        "all_local_checkpoints_ready": all(r["local_checkpoint_ready"] for r in records.values()),
        "remote_pr_or_ci_verified": False, "action_authorized": False, "portfolio_allocation_allowed": False}


def write_report(payload, output):
    output.mkdir(parents=True, exist_ok=False)
    path = output / "inventory.json"
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    (output / "manifest.json").write_text(json.dumps({"artifacts": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = inventory(args.repos_root.resolve())
    write_report(payload, args.output)
    print(json.dumps({n: {k: v[k] for k in ("worktree_clean", "upstream_synced", "personal_push_remotes", "local_checkpoint_ready")} for n, v in payload["repositories"].items()}, indent=2))


if __name__ == "__main__":
    main()
