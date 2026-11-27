"""Allowlisted native dashboard launchers; never stop or replace another listener."""

import fcntl
import os
import socket
import subprocess
import time
from urllib.parse import urlsplit

from portfolio_lab.contracts import ContractError
from portfolio_lab.operations import atomic, roots, store

ENTRIES = {"trade-bot": "src/trade_bot/dashboard_v2/app.py",
           "swing-trader": "src/swing_trader/dashboard.py",
           "rotation-trader": "src/rotation_trader/dashboard.py",
           "position-bot": "src/position_bot/dashboard.py"}


def endpoint(url):
    item = urlsplit(url)
    if (item.scheme != "http" or item.hostname not in {"localhost", "127.0.0.1", "::1"}
            or item.username or item.password or not item.port or not 1024 <= item.port <= 65535):
        raise ContractError("Native dashboards must use explicit local unprivileged endpoints")
    return item.hostname, item.port


def listening(url):
    host, port = endpoint(url)
    try:
        with socket.create_connection((host, port), timeout=.15):
            return True
    except OSError:
        return False


def launch(workspace, name, url):
    if name not in ENTRIES:
        raise ContractError("No allowlisted dashboard launcher")
    host, port = endpoint(url)
    root = roots(workspace)[name]
    folder = store(workspace) / "dashboards"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"{name}.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if listening(url):
            return {"status": "listener_already_present", "url": url}
        script = root / ENTRIES[name]
        if not script.is_file():
            raise ContractError("Native dashboard source unavailable")
        with (folder / f"{name}.log").open("ab") as handle:
            process = subprocess.Popen([str(root / ".venv/bin/python"), "-m", "streamlit", "run", str(script),
                "--server.address", host, "--server.port", str(port), "--server.headless", "true"],
                cwd=root, env=os.environ | {"PYTHONPATH": str(root / "src")}, stdout=handle,
                stderr=subprocess.STDOUT, start_new_session=True)
        result = {"pid": process.pid, "system": name, "url": url, "source_root": str(root)}
        atomic(folder / f"{name}.json", result)
        for _ in range(30):
            if listening(url):
                return {**result, "status": "listening"}
            if process.poll() is not None:
                raise ContractError("Dashboard startup failed; inspect its operations log")
            time.sleep(.2)
        raise ContractError("Dashboard startup not yet confirmed; inspect its operations receipt")
