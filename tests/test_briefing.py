import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from portfolio_lab.brief_agent import (
    PROMPT_VERSION,
    accept_local_result,
    attach_review,
    handoff,
    narrate,
    signal_only_pack,
    validate_narrative,
)
from portfolio_lab.briefing import (
    SECTORS,
    SYSTEMS,
    Specialist,
    build_pack,
    calendar,
    completed_sessions,
    load_specialists,
    publish_replay,
    score_replay,
    validate_pack,
    verify_replay,
)
from portfolio_lab.contracts import Bundle, ContractError, json_hash

NOW = datetime(2026, 11, 25, 19, tzinfo=UTC)


@pytest.fixture
def specialists():
    dates = calendar().sessions_in_range("2024-01-02", "2026-11-24").tz_localize(None)
    columns = ["SPY", "QQQ", "RSP", "SMH", "GLD", "IEF", *SECTORS]
    prices = pd.DataFrame({t: 100 * np.exp(np.arange(len(dates)) * .0003 + np.sin(np.arange(len(dates)) / 13) * .015) for t in columns}, index=dates)
    result = {}
    for system in SYSTEMS:
        target = pd.DataFrame(0., index=dates, columns=["SPY", "GLD"])
        target["GLD" if system == "swing-trader" else "SPY"] = .7
        signals = pd.DataFrame({"reason": "native_rule", "scheduled": False, "stress": .3}, index=dates)
        bundle = Bundle(Path("unused"), {"primary_expert": "primary", "created_at_utc": NOW.isoformat()}, prices.copy(), {"primary": target}, pd.Series(0., index=dates))
        result[system] = Specialist(bundle, signals, {"driver_columns": ["scheduled"], "monitor_columns": ["stress"], "semantics": "reconstruction", "limitations": []}, {"source": "fixture"})
    return result


def test_completed_sessions_excludes_today_before_close_and_holidays():
    sessions = completed_sessions(40, NOW)
    assert len(sessions) == 40
    assert str(sessions[-1].date()) == "2026-11-24"
    assert "2026-11-26" not in completed_sessions(2, datetime(2026, 11, 27, 18, 14, tzinfo=UTC)).astype(str)
    assert completed_sessions(1, datetime(2026, 11, 27, 18, 14, tzinfo=UTC))[-1] == pd.Timestamp("2026-11-25")
    assert completed_sessions(1, datetime(2026, 11, 27, 18, 15, tzinfo=UTC))[-1] == pd.Timestamp("2026-11-27")


@pytest.mark.parametrize("count", [0, -1, 253])
def test_invalid_replay_length(count):
    with pytest.raises(ContractError):
        completed_sessions(count, NOW)


def test_future_shocks_cannot_change_historical_pack(specialists):
    day = pd.Timestamp("2026-11-02")
    original = build_pack(specialists, day)
    changed = copy.deepcopy(specialists)
    for s in changed.values():
        s.bundle.prices.loc[s.bundle.prices.index > day] *= .2
        s.bundle.targets["primary"].loc[s.bundle.prices.index > day] = 0
        s.signals.loc[s.signals.index > day, "stress"] = 1
    assert original == build_pack(changed, day)
    assert "forward_return" not in json.dumps(original)
    assert "captured_at" not in json.dumps(original)


def test_stale_bot_has_no_same_day_confirmation(specialists):
    bot = specialists["swing-trader"]
    bot.bundle.targets["primary"] = bot.bundle.targets["primary"].iloc[:-1]
    bot.signals = bot.signals.iloc[:-1]
    pack = build_pack(specialists, "2026-11-24")
    assert pack["fresh_specialists"] == 2
    assert pack["comparison"] == "partial_coverage"
    result = next(b for b in pack["bots"] if b["system"] == "swing-trader")
    assert result["lag_sessions"] == 1
    assert result["eligible_for_comparison"] is False
    assert next(f for f in pack["facts"] if f["id"] == "swing-trader.cash")["observed_session"] == "2026-11-23"


def test_gold_is_not_labeled_equity_risk_on(specialists):
    pack = build_pack(specialists, "2026-11-24")
    bot = next(b for b in pack["bots"] if b["system"] == "swing-trader")
    assert bot["target_exposure"] == .7
    assert bot["equity_risk_proxy"] == 0
    assert bot["stance"] == "defensive"


def test_missing_market_session_fails_closed(specialists):
    specialists["trade-bot"].bundle.prices = specialists["trade-bot"].bundle.prices.drop(pd.Timestamp("2026-11-02"))
    with pytest.raises(ContractError, match="missing sessions"):
        build_pack(specialists, "2026-11-24")


def test_missing_specialist_does_not_erase_fresh_market(specialists):
    del specialists["swing-trader"]
    pack = build_pack(specialists, "2026-11-24")
    assert pack["fresh_specialists"] == 2
    assert pack["bots"][1]["status"] == "missing"


def test_unmatured_forward_returns_are_not_zero(specialists):
    sessions = completed_sessions(40, NOW)
    packs = [build_pack(specialists, d) for d in sessions]
    scores = score_replay(packs, specialists, sessions)
    assert len(scores) == 160
    assert scores[scores.horizon.eq(5)].matured.sum() == 70
    assert scores[scores.horizon.eq(21)].matured.sum() == 38
    assert scores.loc[~scores.matured, "forward_return"].isna().all()


def test_outcome_missing_session_does_not_silently_shorten_horizon(specialists):
    day = pd.Timestamp("2026-11-02")
    pack = build_pack(specialists, day)
    specialists["trade-bot"].bundle.prices = specialists["trade-bot"].bundle.prices.drop(pd.Timestamp("2026-11-05"))
    outcomes = score_replay([pack], specialists, completed_sessions(40, NOW))
    assert not outcomes.matured.any()


def narrative():
    return {"headline": "Market participation remains mixed", "sections": [{"heading": "Market", "claims": [
        {"text": "Sector participation is the breadth monitor.", "evidence_ids": ["market.breadth"], "kind": "observation"}]}]}


@pytest.mark.parametrize("kind", ["unknown_citation", "no_citation", "invented_number", "order", "probability", "schema"])
def test_adversarial_narratives_rejected(specialists, kind):
    pack = build_pack(specialists, "2026-11-24")
    brief = narrative()
    claim = brief["sections"][0]["claims"][0]
    if kind == "unknown_citation":
        claim["evidence_ids"] = ["future.crash"]
    elif kind == "no_citation":
        claim["evidence_ids"] = []
    elif kind == "invented_number":
        claim["text"] = "Returns will be 99%."
    elif kind == "order":
        claim["text"] = "Buy the market now."
    elif kind == "probability":
        claim["text"] = "The probability of a crash is high."
    else:
        brief["execute_order"] = True
    with pytest.raises(ContractError):
        validate_narrative(brief, pack)


def test_local_agent_handoff_requires_matching_evidence_and_independent_review(tmp_path, specialists):
    pack = build_pack(specialists, "2026-11-24")
    request = handoff(pack)
    assert request["tools"] == []
    record = {"input_sha256": json_hash(pack), "prompt_version": PROMPT_VERSION,
              "brief": narrative(), "author": "analyst", "review": {"approved": True, "issues": [], "reviewer": "skeptic"}}
    path = tmp_path / "response.json"
    path.write_text(json.dumps(record))
    assert accept_local_result(pack, path)[0]["mode"] == "reviewed_local_handoff"
    record["review"]["reviewer"] = "analyst"
    path.write_text(json.dumps(record))
    with pytest.raises(ContractError, match="distinct"):
        accept_local_result(pack, path)
    record["input_sha256"] = "different"
    path.write_text(json.dumps(record))
    with pytest.raises(ContractError, match="different evidence"):
        accept_local_result(pack, path)


def test_evidence_mode_never_claims_agent_execution(specialists):
    pack = build_pack(specialists, "2026-11-24")
    brief, log = narrate(pack, enabled=True)
    assert brief["mode"] == "evidence_only"
    assert log["external_transfer"] is False
    assert log["calls"] == []


@pytest.fixture
def archive(tmp_path, specialists, monkeypatch):
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    root = tmp_path / "archive"
    publish_replay([], tmp_path, root, count=40, now=NOW)
    return root


def test_40_session_archive_is_complete_immutable_and_hash_bound(archive):
    manifest = verify_replay(archive)
    assert len(manifest["sessions"]) == 40
    assert len(manifest["artifacts"]) == 125
    (archive / "summary.json").write_text("tampered")
    with pytest.raises(ContractError, match="mismatch"):
        verify_replay(archive)


def test_archive_refuses_replacement(archive, monkeypatch, specialists):
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    with pytest.raises(FileExistsError):
        publish_replay([], archive, archive, now=NOW)


@pytest.mark.parametrize("fault", ["authority", "future", "unbound"])
def test_archive_audits_operational_event_context_not_only_market_packs(archive, fault):
    from portfolio_lab.contracts import digest

    payload = {"schema_version": 2, "system": "fundamental-event-trader", "status": "blocked",
               "captured_at_utc": "2026-11-24T22:00:00Z", "authority": "research_only",
               "action_authorized": False, "portfolio_allocation_allowed": False,
               "automatic_promotion_allowed": False, "target_holdings": {}, "recent_events": []}
    meta = json.loads((archive / "manifest.json").read_text())
    if fault == "authority":
        payload["action_authorized"] = True
    elif fault == "future":
        payload["captured_at_utc"] = (pd.Timestamp(meta["created_at_utc"]) + pd.Timedelta(days=1)).isoformat()
    file = archive / "context/fundamental_event.json"
    file.parent.mkdir(exist_ok=True)
    file.write_text(json.dumps(payload))
    if fault != "unbound":
        meta["artifacts"]["context/fundamental_event.json"] = digest(file)
        (archive / "manifest.json").write_text(json.dumps(meta))
    with pytest.raises(ContractError):
        verify_replay(archive)


def test_news_is_archived_without_rewriting_historical_model_facts(archive, tmp_path, specialists, monkeypatch):
    from portfolio_lab.contracts import digest

    telemetry = tmp_path / "news_telemetry"
    news_dir = telemetry / "fundamental-news"
    news_dir.mkdir(parents=True)
    news = {"schema_version": 1, "status": "available", "authority": "observation_only",
            "action_authorized": False, "historical_strategy_evidence": False,
            "captured_at_utc": "2026-11-25T19:00:00Z", "article_bodies_read": 0,
            "items": [{"id": "fixture", "url": "https://www.example.com/earnings",
                       "published_at_utc": "2026-11-24T22:00:00Z", "first_seen_at_utc": "2026-11-25T19:00:00Z",
                       "version_first_seen_at_utc": "2026-11-25T19:00:00Z", "available_at_utc": "2026-11-25T19:00:00Z",
                       "display_title": "Synthetic earnings fixture", "coverage": "headline_and_feed_summary", "source": "Fixture"}]}
    (news_dir / "items.json").write_text(json.dumps(news["items"]))
    native_manifest = {"kind": "public_news_observation", "action_authorized": False,
                       "historical_strategy_evidence": False, "artifacts": {"items.json": digest(news_dir / "items.json")}}
    (news_dir / "manifest.json").write_text(json.dumps(native_manifest))
    news["manifest_sha256"] = digest(news_dir / "manifest.json")
    event = {"schema_version": 2, "system": "fundamental-event-trader", "status": "blocked", "stage": "data_acquisition",
             "authority": "research_only", "captured_at_utc": "2026-11-25T19:00:00Z", "action_authorized": False,
             "portfolio_allocation_allowed": False, "automatic_promotion_allowed": False,
             "target_holdings": {}, "recent_events": [], "news": news,
             "news_context_artifacts": {"fundamental-news/manifest.json": digest(news_dir / "manifest.json"),
                                        "fundamental-news/items.json": digest(news_dir / "items.json")}}
    (telemetry / "fundamental_event.json").write_text(json.dumps(event))
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    output = publish_replay([], telemetry, tmp_path / "news_archive", count=40, now=NOW)
    verify_replay(output)
    assert (output / "context/fundamental-news/items.json").is_file()
    assert "## Current Financial News" in (output / "readout.md").read_text()
    for day in verify_replay(archive)["sessions"]:
        assert (archive / "sessions" / day / "pack.json").read_bytes() == (output / "sessions" / day / "pack.json").read_bytes()
    # Rebinding the context alone cannot make a missing source archive acceptable.
    meta = json.loads((output / "manifest.json").read_text())
    del meta["artifacts"]["context/fundamental-news/items.json"]
    (output / "manifest.json").write_text(json.dumps(meta))
    with pytest.raises(ContractError, match="Incomplete bound news"):
        verify_replay(output)


def test_replay_refuses_mixed_code_versions(tmp_path, specialists, monkeypatch):
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    calls = iter(["before", "after"])
    monkeypatch.setattr("portfolio_lab.briefing.interpretation_hash", lambda: next(calls))
    output = tmp_path / "mixed"
    with pytest.raises(ContractError, match="code changed"):
        publish_replay([], tmp_path, output, count=1, now=NOW)
    assert not (output / "manifest.json").exists()


def test_market_desk_app_all_views(archive, monkeypatch):
    path = Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py"
    monkeypatch.setenv("PORTFOLIO_LAB_DESK", str(archive))
    app = AppTest.from_file(str(path), default_timeout=30).run()
    assert not app.exception
    assert app.title[0].value == "Market Interpretation Desk"
    for view in ("News & events", "Signals & bots", "Event research", "Replay scorecard", "Evidence"):
        app.radio[0].set_value(view).run()
        assert not app.exception


def test_runner_lock_and_failure_preserve_published_pointer(tmp_path, monkeypatch):
    from portfolio_lab.brief_runner import run_briefs

    monkeypatch.chdir(tmp_path)
    root = tmp_path / "reports/market-desk"
    root.mkdir(parents=True)
    pointer = root / "latest.json"
    pointer.write_text('{"report":"previous-valid-archive"}')
    args = SimpleNamespace(bundle=[tmp_path / "missing"], telemetry=tmp_path, output=tmp_path / "new", sessions=40)
    with pytest.raises(FileNotFoundError):
        run_briefs(args)
    assert "previous-valid-archive" in pointer.read_text()
    assert not (root / ".writer.lock").exists()
    (root / ".writer.lock").write_text("another process")
    with pytest.raises(ContractError, match="already active"):
        run_briefs(args)


def test_narrator_allowlist_drops_all_account_and_position_context(specialists):
    pack = build_pack(specialists, "2026-11-24")
    pack["account_balance"] = "PRIVATE_ACCOUNT_SENTINEL"
    pack["journal"] = "PRIVATE_JOURNAL_SENTINEL"
    public = signal_only_pack(pack)
    serialized = json.dumps(public)
    assert "PRIVATE_" not in serialized
    assert "target_holdings" not in serialized
    assert "2026-11-24" not in serialized
    pack["facts"].append({**pack["facts"][0], "id": "account.balance"})
    with pytest.raises(ContractError, match="public-signal"):
        signal_only_pack(pack)


def test_future_evidence_and_duplicate_ids_are_rejected(specialists):
    pack = build_pack(specialists, "2026-11-24")
    pack["facts"][0]["observed_session"] = "2026-11-25"
    with pytest.raises(ContractError, match="Future information"):
        validate_pack(pack, "2026-11-24")
    pack["facts"][0]["observed_session"] = "2026-11-24"
    pack["facts"].append(pack["facts"][0])
    with pytest.raises(ContractError, match="Duplicate"):
        validate_pack(pack, "2026-11-24")


def test_review_attachment_cannot_rewrite_parent_or_financial_policy(archive, tmp_path):
    from portfolio_lab.contracts import digest
    from portfolio_lab.governance import policy_hash

    before = digest(archive / "manifest.json")
    policy = policy_hash()
    pack = json.loads((archive / "sessions/2026-11-24/pack.json").read_text())
    document = {"input_sha256": json_hash(pack), "prompt_version": PROMPT_VERSION,
                "brief": narrative(), "author": "analyst", "review": {"approved": True, "issues": [], "reviewer": "skeptic"}}
    path = tmp_path / "approved.json"
    path.write_text(json.dumps(document))
    output = attach_review(archive, "2026-11-24", path, tmp_path / "reviewed")
    assert verify_replay(output)["parent_manifest_sha256"] == before
    assert digest(archive / "manifest.json") == before
    assert policy_hash() == policy
    with pytest.raises(FileExistsError):
        attach_review(archive, "2026-11-24", path, output)


def test_archive_date_selection_changes_the_read_not_the_policy(archive, monkeypatch):
    path = Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py"
    monkeypatch.setenv("PORTFOLIO_LAB_DESK", str(archive))
    app = AppTest.from_file(str(path), default_timeout=30).run()
    app.selectbox[0].set_value("2026-09-30").run()
    assert not app.exception
    assert any("CLOSE 2026-09-30" in c.value for c in app.caption)


@pytest.mark.parametrize("fault", ["none", "bundle_identity", "artifact_tamper", "target_mismatch", "missing_instrument"])
def test_native_telemetry_is_bound_and_reconciled(tmp_path, fault):
    from test_contracts import bundle

    from portfolio_lab.contracts import digest

    root = bundle(tmp_path / "bundle", system="trade-bot", expert="primary")
    metadata = json.loads((root / "manifest.json").read_text())
    metadata["created_at_utc"] = NOW.isoformat()
    (root / "manifest.json").write_text(json.dumps(metadata))
    target = pd.read_parquet(root / "weights.parquet").rename(columns=lambda c: f"target_{c}")
    if fault == "target_mismatch":
        target.iloc[-1, 0] += .1
    elif fault == "missing_instrument":
        target = target.drop(columns="target_QQQ")
    directory = tmp_path / "telemetry/trade-bot"
    directory.mkdir(parents=True)
    target.to_parquet(directory / "signals.parquet")
    meta = {"schema_version": 1, "system": "trade-bot", "signals_sha256": digest(directory / "signals.parquet"),
            "bundle_sha256": digest(root / "manifest.json")}
    if fault == "bundle_identity":
        meta["bundle_sha256"] = "wrong"
    elif fault == "artifact_tamper":
        meta["signals_sha256"] = "wrong"
    (directory / "manifest.json").write_text(json.dumps(meta))
    if fault == "none":
        assert set(load_specialists([root], directory.parent)) == {"trade-bot"}
    else:
        with pytest.raises(ContractError):
            load_specialists([root], directory.parent)


def test_failed_provider_is_not_substituted_as_cash(tmp_path, monkeypatch):
    from portfolio_lab.brief_runner import capture_local_bundles

    def execute(args, **kwargs):
        if "swing_trader.portfolio_export" in args:
            raise OSError("simulated unavailable local provider")

    monkeypatch.setattr("portfolio_lab.brief_runner.subprocess.run", execute)
    paths, health = capture_local_bundles(tmp_path, tmp_path / "capture")
    assert len(paths) == 2
    assert health["swing-trader"]["status"] == "unavailable"


def test_stale_targets_are_not_forward_filled_on_comparison_charts(tmp_path, monkeypatch, specialists):
    stale = specialists["swing-trader"]
    stale.signals = stale.signals.iloc[:-1]
    stale.bundle.targets["primary"] = stale.bundle.targets["primary"].iloc[:-1]
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    root = tmp_path / "partial"
    publish_replay([], tmp_path, root, now=NOW)
    timeline = pd.read_parquet(root / "timeline.parquet")
    assert pd.isna(timeline["swing-trader.equity"].iloc[-1])
    assert pd.notna(timeline["trade-bot.equity"].iloc[-1])


def test_short_archive_without_mature_outcomes_has_an_honest_empty_state(tmp_path, monkeypatch, specialists):
    monkeypatch.setattr("portfolio_lab.briefing.load_specialists", lambda *a: specialists)
    root = tmp_path / "single_session"
    publish_replay([], tmp_path, root, count=1, now=NOW)
    monkeypatch.setenv("PORTFOLIO_LAB_DESK", str(root))
    path = Path(__file__).parents[1] / "src/portfolio_lab/dashboard.py"
    app = AppTest.from_file(str(path), default_timeout=30).run()
    app.radio[0].set_value("Replay scorecard").run()
    assert not app.exception
    assert any("not matured" in info.value for info in app.info)
