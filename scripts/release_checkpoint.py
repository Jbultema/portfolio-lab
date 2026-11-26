"""Personal-SSH checkpoints, tested-source receipts and unauthenticated public PR reads."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

NAMES = ("trade-bot", "swing-trader", "rotation-trader", "portfolio-lab", "fundamental-event-trader")
ROOT_FILES = {"README.md", "pyproject.toml", "poetry.lock", "requirements.lock", ".gitignore"}
PREFIXES = {"src", "tests", "docs", "scripts", ".github", "contracts", "config", "configs"}
SECRET = re.compile(rb"(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[A-Z0-9]{16})")


def git(root, *args):
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def changed_sources(root):
    paths = set(git(root, "diff", "--name-only", "-z", "HEAD").split("\0"))
    paths |= set(git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    paths.discard("")
    unknown = [p for p in paths if p not in ROOT_FILES and Path(p).parts[0] not in PREFIXES]
    if unknown:
        raise ValueError(f"Protected non-source changes require review: {root.name}: {unknown}")
    for name in paths:
        path = root / name
        if path.is_symlink() or (path.exists() and SECRET.search(path.read_bytes())):
            raise ValueError(f"Publication safety review required: {root.name}/{name}")
    return sorted(paths)


def public_json(url):
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Jbultema-personal-release-audit"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"verified": True, "data": json.load(response)}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"verified": False, "error": type(exc).__name__}


def run(repos_root, qa_path, output, cycle, push):
    module_path = Path(__file__).with_name("verify_workspace.py")
    spec = importlib.util.spec_from_file_location("workspace_verify", module_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    qa = json.loads(qa_path.read_text())
    if qa.get("local_checks_passed") is not True:
        raise ValueError("Complete passing five-repo QA is required")
    output.mkdir(parents=True, exist_ok=False)
    report = {"cycle": cycle, "captured_at_utc": datetime.now(UTC).isoformat(), "repositories": {},
        "action_authorized": False, "no_employer_credentials_used": True, "original_worktrees_preserved": True}
    for name in NAMES:
        root = repos_root / name
        if verifier.source_fingerprint(root) != qa["repositories"][name]["source_fingerprint"]:
            raise ValueError(f"Tested source changed: {name}")
        branch = git(root, "branch", "--show-current")
        if not branch.startswith("codex/system-five-cycle-"):
            raise ValueError("Only this task's personal feature branches may be checkpointed")
        paths = changed_sources(root)
        remotes = git(root, "remote", "-v").splitlines()
        pushes = [row.split()[:2] for row in remotes if row.endswith("(push)")]
        allowed = re.compile(rf"git@(?:github-personal|github\.com):Jbultema/{re.escape(name)}\.git$")
        if len(pushes) != 1 or not allowed.fullmatch(pushes[0][1]):
            raise ValueError("Exactly one personal SSH push destination is required")
        remote = pushes[0][0]
        ssh = git(root, "config", "--get", "core.sshCommand") if "github-personal:" not in pushes[0][1] else "github-personal"
        if "github-personal" not in ssh and "id_ed25519_github_personal" not in ssh:
            raise ValueError("Personal SSH identity must be explicit")
        if paths:
            git(root, "add", "--", *paths)
            git(root, "-c", "user.name=Jbultema", "-c", "user.email=Jbultema@users.noreply.github.com", "commit", "-m", f"Complete system improvement cycle {cycle}: implementation and QA checkpoint")
        head = git(root, "rev-parse", "HEAD")
        if push:
            git(root, "push", "--set-upstream", remote, f"HEAD:refs/heads/{branch}")
            remote_head = git(root, "ls-remote", "--heads", remote, f"refs/heads/{branch}").split()[0]
            if remote_head != head:
                raise ValueError("Remote readback differs from tested checkpoint")
        pr = public_json(f"https://api.github.com/repos/Jbultema/{name}/pulls?state=open&head=" + urllib.parse.quote("Jbultema:" + branch))
        checks = public_json(f"https://api.github.com/repos/Jbultema/{name}/commits/{head}/check-runs")
        clean = not git(root, "status", "--porcelain")
        report["repositories"][name] = {"head": head, "branch": branch, "worktree_clean": clean,
            "pushed_and_read_back": push, "source_fingerprint": verifier.source_fingerprint(root),
            "tests": qa["repositories"][name]["test_counts"], "public_pr_read": pr, "public_ci_read": checks,
            "pr_exists": bool(pr.get("verified") and pr["data"]),
            "compare_url": f"https://github.com/Jbultema/{name}/compare/{branch}?expand=1"}
        (output / "checkpoint.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: committed={bool(paths)}, clean={clean}, pushed={push}", flush=True)
    report["all_release_worktrees_clean"] = all(r["worktree_clean"] for r in report["repositories"].values())
    report["all_prs_exist"] = all(r["pr_exists"] for r in report["repositories"].values())
    report["full_remote_checkpoint_complete"] = False
    (output / "checkpoint.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-root", type=Path, required=True)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycle", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    run(args.repos_root, args.qa, args.output, args.cycle, args.push)
