"""Keep financial-policy identity independent from presentation and commentary."""

from pathlib import Path

from portfolio_lab.contracts import digest, json_hash

POLICY_FILES = ("allocation.py", "audit.py", "contracts.py", "corporate_actions.py", "engine.py", "research.py", "governance.py")


def policy_hash() -> str:
    root = Path(__file__).parent
    return json_hash({name: digest(root / name) for name in POLICY_FILES})
