import importlib.util
from pathlib import Path


def module():
    spec = importlib.util.spec_from_file_location(
        "verify_workspace", Path(__file__).parents[1] / "scripts/verify_workspace.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def test_junit_counts_exclude_skipped_and_failed(tmp_path):
    path = tmp_path / "tests.xml"
    path.write_text(
        '<testsuites><testsuite tests="9" failures="1" errors="1" skipped="2"/>'
        '<testsuite tests="3" failures="0" errors="0" skipped="0"/></testsuites>'
    )
    assert module().junit_counts(path) == {
        "tests": 12, "failures": 1, "errors": 1, "skipped": 2, "passed": 8
    }


def test_missing_command_is_failure_not_skipped(tmp_path):
    assert module().command(tmp_path, [str(tmp_path / "missing")])["exit_code"] == -1
