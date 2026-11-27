import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.operations import (
    SYSTEMS,
    active,
    atomic,
    commands,
    job_file,
    read_job,
    start,
    worker,
)


def test_concurrent_buttons_coalesce_one_job(tmp_path):
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = list(pool.map(lambda _: start(tmp_path, launch=False), range(12)))
    assert len({j["job_id"] for j in jobs}) == 1
    assert len(list((tmp_path / "reports/operations/jobs").iterdir())) == 1


def test_failed_launch_is_terminal_and_retryable(tmp_path):
    with patch("portfolio_lab.operations.subprocess.Popen", side_effect=OSError("no worker")):
        failed = start(tmp_path)
    assert failed["status"] == "failed"
    assert active(tmp_path) is None
    assert start(tmp_path, launch=False)["job_id"] != failed["job_id"]


def test_abandoned_queued_job_reconciled(tmp_path):
    job = start(tmp_path, launch=False)
    job["created_at_utc"] = (datetime.now(UTC) - timedelta(minutes=3)).isoformat()
    atomic(job_file(tmp_path, job["job_id"]), job)
    assert active(tmp_path) is None
    assert read_job(tmp_path, job["job_id"])["status"] == "failed"


def test_dead_worker_is_not_permanently_queued(tmp_path):
    job = start(tmp_path, launch=False)
    job["pid"] = 99999999
    atomic(job_file(tmp_path, job["job_id"]), job)
    assert active(tmp_path) is None


@pytest.mark.parametrize("name", SYSTEMS)
def test_daily_commands_never_search_or_submit_orders(name, tmp_path):
    plan = commands(name, tmp_path / name, tmp_path / "out", True, tmp_path)
    assert all("research" not in command and "run" not in command for command in plan)
    assert all("shell" not in command and "order" not in command for command in plan)


def test_core_failure_preserves_prior_report_and_attempts_other_bots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pointer = tmp_path / "reports/market-desk/latest.json"
    atomic(pointer, {"report": "prior_complete"})
    job = start(tmp_path, launch=False)
    result = worker(tmp_path, job["job_id"])
    assert result["status"] == "failed"
    assert len(result["stages"]) == 5
    assert json.loads(pointer.read_text())["report"] == "prior_complete"


def test_terminal_job_cannot_execute_twice(tmp_path):
    job = start(tmp_path, launch=False)
    job["status"] = "completed"
    atomic(job_file(tmp_path, job["job_id"]), job)
    with pytest.raises(ContractError, match="only once"):
        worker(tmp_path, job["job_id"])


@pytest.mark.parametrize("job", ["../x", "bad", "A" * 32, 4])
def test_job_path_cannot_escape(tmp_path, job):
    with pytest.raises(ContractError):
        job_file(tmp_path, job)


def test_unsafe_native_adapter_names_rejected(tmp_path):
    with pytest.raises(ContractError):
        commands("../../evil", tmp_path, tmp_path, False, tmp_path)


def test_schedule_uses_same_pipeline_and_pins_source():
    import importlib.util

    file = Path(__file__).parents[1] / "scripts/daily_service.py"
    spec = importlib.util.spec_from_file_location("daily_service", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.payload(Path("/example/portfolio-lab"))
    assert data["StartInterval"] == 900
    assert "portfolio_lab.operations" in data["ProgramArguments"]
    assert data["EnvironmentVariables"]["PYTHONPATH"] == "/example/portfolio-lab/src"
