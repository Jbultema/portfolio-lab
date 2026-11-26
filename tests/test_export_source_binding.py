from portfolio_lab.cli import export_all


def test_exports_bind_to_each_native_worktree_source(tmp_path, monkeypatch):
    calls = []
    for name in ("trade-bot", "swing-trader", "rotation-trader", "fundamental-event-trader"):
        root = tmp_path / name
        (root / ".venv/bin").mkdir(parents=True)
        (root / ".venv/bin/python").touch()
        (root / "src").mkdir()
    event = tmp_path / "fundamental-event-trader/data"
    event.mkdir()
    (event / "runtime.json").write_text("{}")
    monkeypatch.setattr("portfolio_lab.cli.subprocess.run", lambda *a, **kw: calls.append(kw))
    assert len(export_all(tmp_path, tmp_path / "bundles")) == 4
    assert all(row["env"]["PYTHONPATH"] == str((row["cwd"] / "src").resolve()) for row in calls)
