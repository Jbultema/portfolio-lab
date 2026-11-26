import importlib.util
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_fingerprint_changes_for_new_executable_but_not_report(tmp_path):
    import subprocess

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    path = tmp_path / "src/test.py"
    path.write_text("a = 1\n")
    module = load("verify_workspace")
    before = module.source_fingerprint(tmp_path)
    path.write_text("a = 2\n")
    assert module.source_fingerprint(tmp_path) != before
    (tmp_path / "src/unsafe.py").symlink_to(path)
    with pytest.raises(ValueError):
        module.source_fingerprint(tmp_path)


def test_publication_scanner_rejects_recognizable_secret_without_printing_it(tmp_path, monkeypatch):
    module = load("release_checkpoint")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/bad.py").write_text("ghp_" + "A" * 40)
    monkeypatch.setattr(module, "git", lambda *args: "src/bad.py")
    with pytest.raises(ValueError, match="safety review") as exc:
        module.changed_sources(tmp_path)
    assert "A" * 40 not in str(exc.value)


def test_raw_market_data_is_not_published_as_source(tmp_path, monkeypatch):
    module = load("release_checkpoint")
    monkeypatch.setattr(module, "git", lambda *args: "data/private-account.json")
    with pytest.raises(ValueError, match="Protected non-source"):
        module.changed_sources(tmp_path)
