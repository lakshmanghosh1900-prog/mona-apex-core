from __future__ import annotations

import pytest

from fabric.registry.budget_manager import BudgetManager
from fabric.registry.fastapi_integration import build_stage12_verify_payload
from fabric.registry.permission_enforcer import (
    METADATA_FIELDS,
    TOOL_METADATA_REGISTRY,
    PermissionEnforcer,
    get_enforcer,
    reset_enforcer,
    validate_metadata,
    validate_registry_consistency,
)
from fabric.registry.registry_loader import load_registry

EXPECTED_TOOLS = {
    "browser.search",
    "browser.open",
    "files.read",
    "files.write",
    "code.run",
    "sheets.write",
    "email.send",
    "research.search",
}


@pytest.fixture()
def enforcer():
    reset_enforcer()
    instance = get_enforcer()
    yield instance
    reset_enforcer()


def test_metadata_has_8_tools():
    assert len(TOOL_METADATA_REGISTRY) >= 8
    assert set(TOOL_METADATA_REGISTRY) >= EXPECTED_TOOLS


def test_metadata_validation_clean():
    assert validate_metadata() == []
    assert validate_registry_consistency() == []


def test_every_metadata_entry_has_all_fields():
    for name, entry in TOOL_METADATA_REGISTRY.items():
        for field_name in METADATA_FIELDS:
            assert field_name in entry, f"{name}: missing {field_name}"


def test_timeout_defined():
    assert TOOL_METADATA_REGISTRY["code.run"]["timeout"] == 60
    assert TOOL_METADATA_REGISTRY["browser.search"]["timeout"] == 30


def test_retry_defined_browser_search():
    entry = TOOL_METADATA_REGISTRY["browser.search"]
    assert entry["retry_max"] == 3
    assert entry["retry_backoff"]["strategy"] == "exponential"
    assert entry["retry_backoff"]["multiplier"] > 1


def test_cost_is_zero_for_all_tools():
    for name, entry in TOOL_METADATA_REGISTRY.items():
        assert entry["cost"] == 0.0, name
        assert entry["cost_per_1000"] == 0.0, name
        assert entry["budget_limit_per_day"] == 0.0, name


def test_high_risk_requires_approval():
    registry = load_registry()
    assert TOOL_METADATA_REGISTRY["email.send"]["requires_approval"] is True
    assert registry.requires_approval("email.send") is True
    for name, entry in TOOL_METADATA_REGISTRY.items():
        if registry.get(name) and registry.requires_approval(name):
            assert entry["requires_approval"] is True, name


def test_low_risk_requires_no_approval():
    registry = load_registry()
    assert TOOL_METADATA_REGISTRY["browser.search"]["requires_approval"] is False
    assert registry.requires_approval("browser.search") is False


def test_quota_defined_browser_search():
    assert TOOL_METADATA_REGISTRY["browser.search"]["quota_per_hour"] == 100
    assert TOOL_METADATA_REGISTRY["email.send"]["quota_per_hour"] == 10


def test_budget_manager_zero_cost():
    budget = BudgetManager()
    assert budget.zero_cost is True
    assert budget.spent_today() == 0.0
    assert budget.can_spend(0.0) is True
    assert budget.check(tool_cost_usd=0.0)["allowed"] is True
    assert budget.check(tool_cost_usd=0.0)["stack"] == "zero-cost"
    assert budget.calls == 0


def test_budget_manager_blocks_paid_spend_at_zero_limit():
    budget = BudgetManager(daily_limit_usd=0.0)
    assert budget.spend(1.0) is False
    assert budget.spent_today() == 0.0


def test_budget_manager_tracks_when_limit_allows():
    budget = BudgetManager(daily_limit_usd=5.0)
    assert budget.spend(1.5) is True
    assert budget.spent_today() == pytest.approx(1.5)
    assert budget.remaining_today() == pytest.approx(3.5)
    assert budget.zero_cost is False


def test_check_permission_email_send_admin_only(enforcer):
    assert enforcer.check_permission("email.send", "User")["allowed"] is False
    assert enforcer.check_permission("email.send", "Operator")["allowed"] is False
    assert enforcer.check_permission("email.send", "Admin")["allowed"] is True
    assert enforcer.check_permission("email.send", "Owner")["allowed"] is True


def test_check_permission_browser_search_any_role(enforcer):
    for role in ("User", "Operator", "Admin", "Owner"):
        assert enforcer.check_permission("browser.search", role)["allowed"] is True, role


def test_check_permission_unknown_tool(enforcer):
    with pytest.raises(KeyError):
        enforcer.check_permission("no.such", "User")


def test_quota_enforcement_window(enforcer):
    for _ in range(100):
        enforcer.record_call("browser.search")
    quota = enforcer.check_quota("browser.search")
    assert quota["used"] == 100
    assert quota["allowed"] is False
    assert enforcer.check("browser.search", role="User")["allowed"] is False
    assert any("quota exhausted" in r for r in enforcer.check("browser.search", role="User")["reasons"])


def test_quota_allows_below_limit(enforcer):
    enforcer.record_call("browser.search")
    quota = enforcer.check_quota("browser.search")
    assert quota["used"] == 1
    assert quota["allowed"] is True
    assert quota["window_seconds"] == 3600


def test_get_timeout(enforcer):
    assert enforcer.get_timeout("code.run") == 60
    assert enforcer.get_timeout("browser.search") == 30


def test_get_retry_policy(enforcer):
    policy = enforcer.get_retry_policy("browser.search")
    assert policy["max_attempts"] == 3
    assert policy["strategy"] == "exponential"
    assert policy["multiplier"] == 2.0


def test_concurrency_limits(enforcer):
    assert enforcer.try_acquire("email.send") is True
    assert enforcer.try_acquire("email.send") is False
    enforcer.release("email.send")
    assert enforcer.try_acquire("email.send") is True
    assert enforcer.check_concurrency("email.send")["limit"] == 1


def test_record_call_updates_quota_and_budget(enforcer):
    result = enforcer.record_call("email.send")
    assert result["recorded"] is True
    assert result["cost_usd"] == 0.0
    assert result["quota_used"] == 1
    assert result["spent_today"] == 0.0
    assert enforcer.budget.zero_cost is True


def test_full_check_shape(enforcer):
    report = enforcer.check("email.send", role="User")
    assert report["allowed"] is False
    assert report["requires_approval"] is True
    assert report["risk_level"] == "HIGH"
    assert report["timeout"] == 30
    assert report["retry_policy"]["max_attempts"] == 2
    assert report["canonical_spec"] == "MONA — Powered by Apex Core"
    assert set(report) >= {"permission", "quota", "budget", "concurrency", "reasons"}

    allowed = enforcer.check("browser.search", role="User")
    assert allowed["allowed"] is True
    assert allowed["requires_approval"] is False
    assert allowed["risk_level"] == "LOW"
    assert allowed["reasons"] == []


def test_verify_stage12_complete():
    payload = build_stage12_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert payload["problems"] == []
    assert len(payload["checks"]) == 8
    assert all(payload["checks"].values()), payload["checks"]
    assert payload["stage"] == "Phase 1 Stage 1.2 - Tool Permission Metadata"
