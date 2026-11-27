"""Scorecard authority, evidence integrity and explicit strategy labels."""

import json

import pytest

from portfolio_lab.contracts import ContractError, digest
from portfolio_lab.system_scorecard_ui import candidate_label, load_scorecard, remote_pr_state


def test_scorecard_cannot_authorize_allocation(tmp_path):
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"schema_version": 1, "action_authorized": True}))
    with pytest.raises(ContractError, match="Research-only"):
        load_scorecard(pointer)


def test_changed_archive_is_not_rendered_as_verified(tmp_path):
    pointer = tmp_path / "pointer.json"
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    pointer.write_text(json.dumps({"schema_version": 1, "action_authorized": False,
        "archives": {"validation": {"path": str(tmp_path), "manifest_sha256": "0"*64}}}))
    with pytest.raises(ContractError, match="integrity"):
        load_scorecard(pointer)


def test_archive_cannot_read_unbound_parent_files(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    private = tmp_path / "outside.json"
    private.write_text("{}")
    manifest = archive / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": {"../outside.json": digest(private)}}))
    pointer = tmp_path / "pointer.json"
    pointer.write_text(json.dumps({"schema_version": 1, "action_authorized": False,
        "archives": {"validation": {"path": str(archive), "manifest_sha256": digest(manifest)}}}))
    with pytest.raises(ContractError):
        load_scorecard(pointer)


def test_candidate_labels_do_not_hide_stacked_vs_replaced_guard():
    spec = {"kind": "native_staged", "mode": "confirmed", "lookback": 126,
        "incumbent_drawdown_guard": "replaced"}
    assert candidate_label(spec) == "Confirmed / 126 sessions / guard replaced"


@pytest.mark.parametrize("read,expected", [({"verified": False}, "Unverified"),
    ({"verified": True, "data": []}, "None open"),
    ({"verified": True, "data": [{"number": 1}]}, "Open")])
def test_unknown_pr_state_is_not_reported_as_an_absent_pr(read, expected):
    assert remote_pr_state({"public_pr_read": read}) == expected
