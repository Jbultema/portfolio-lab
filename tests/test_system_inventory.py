import pytest

from portfolio_lab.system_inventory import (
    SYSTEMS,
    personal_remote,
    redact_credentials,
    validate_identity,
    write_report,
)


@pytest.mark.parametrize("name", SYSTEMS)
def test_only_exact_personal_push_destinations_are_accepted(name):
    assert personal_remote(f"git@github-personal:Jbultema/{name}.git", name)
    assert personal_remote(f"git@github.com:Jbultema/{name}.git", name)
    assert not personal_remote(f"git@github.com:hasbro/{name}.git", name)
    assert not personal_remote(f"git@github.com:Jbultema/{name}.git.evil", name)
    assert not personal_remote(f"https://github.com.evil/Jbultema/{name}", name)


@pytest.mark.parametrize("field", ("action_authorized", "portfolio_allocation_allowed"))
def test_registry_cannot_authorize_investment(field):
    value = {"schema_version": 1, "system": "trade-bot", "configuration_consistent": True,
             "action_authorized": False, "portfolio_allocation_allowed": False}
    value[field] = True
    with pytest.raises(ValueError):
        validate_identity(value, "trade-bot")


def test_conditional_event_probe_is_never_a_primary():
    value = {"schema_version": 1, "system": "fundamental-event-trader", "primary": "winner",
             "configuration_consistent": True, "action_authorized": False, "portfolio_allocation_allowed": False}
    with pytest.raises(ValueError):
        validate_identity(value, "fundamental-event-trader")


def test_cycle_inventory_never_overwrites_prior_evidence(tmp_path):
    output = tmp_path / "cycle1"
    write_report({"a": 1}, output)
    with pytest.raises(FileExistsError):
        write_report({"a": 2}, output)


def test_missing_primary_cannot_be_reported_as_consistent():
    with pytest.raises(ValueError):
        validate_identity({"schema_version": 1, "system": "trade-bot", "primary": None,
            "configuration_consistent": True, "action_authorized": False, "portfolio_allocation_allowed": False}, "trade-bot")


def test_inventory_never_writes_an_https_remote_credential():
    value = "origin https://user:private-secret@github.com/Jbultema/trade-bot.git (push)"
    safe = redact_credentials(value)
    assert "private-secret" not in safe
    assert "user:" not in safe
    assert "[redacted]@github.com" in safe
    assert not personal_remote(safe.split()[1], "trade-bot")
    assert "private-secret" not in redact_credentials("https://github.com/repo?token=private-secret")
