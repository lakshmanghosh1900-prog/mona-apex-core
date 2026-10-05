from __future__ import annotations

import time

import pytest

from fabric.registry.auth import (
    AuthContext,
    AuthError,
    AuthService,
    ROLE_LEVELS,
    get_auth_service,
    reset_auth_service,
)
from fabric.registry.fastapi_security import build_stage21_verify_payload
from fabric.registry.policy_engine import (
    DECISION_ALLOW,
    DECISION_DENY,
    DECISION_REQUIRE_APPROVAL,
    PolicyEngine,
    get_policy_engine,
)


@pytest.fixture()
def auth():
    return AuthService(secret="unit-test-secret")


@pytest.fixture()
def engine():
    return get_policy_engine()


def test_issue_and_verify_roundtrip(auth):
    issued = auth.issue_token("mona-user", "User", ttl_seconds=120)
    context = auth.verify_token(issued["token"])
    assert isinstance(context, AuthContext)
    assert context.subject == "mona-user"
    assert context.role == "User"
    assert context.level == ROLE_LEVELS["User"]


def test_tampered_token_rejected(auth):
    issued = auth.issue_token("mona-user", "User")
    token = issued["token"]
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(AuthError):
        auth.verify_token(tampered)


def test_forged_signature_rejected(auth):
    issued = auth.issue_token("mona-user", "User")
    payload = issued["token"].rsplit(".", 1)[0]
    with pytest.raises(AuthError):
        auth.verify_token(payload + "." + "x" * 32)


def test_malformed_token_rejected(auth):
    for bad in ("", "no-dot", None, "a.b"):
        with pytest.raises(AuthError):
            auth.verify_token(bad)


def test_expired_token_rejected():
    auth = AuthService(secret="unit-test-secret", default_ttl=1)
    issued = auth.issue_token("mona-user", "User", ttl_seconds=1)
    time.sleep(2.1)
    with pytest.raises(AuthError) as exc:
        auth.verify_token(issued["token"])
    assert "expired" in str(exc.value)


def test_unknown_role_rejected(auth):
    with pytest.raises(AuthError):
        auth.issue_token("mona-user", "Superuser")
    with pytest.raises(AuthError):
        auth.issue_token("mona-user", "User", ttl_seconds=0)


def test_role_hierarchy_no_escalation(auth):
    assert auth.can_escalate("User", "Owner") is True
    assert auth.can_escalate("Owner", "User") is False
    assert auth.can_escalate("Admin", "Operator") is False
    assert auth.can_escalate("Operator", "Admin") is True


def test_bearer_header_parsing(auth):
    assert auth.parse_bearer("Bearer abc.def") == "abc.def"
    assert auth.parse_bearer("bearer abc.def") == "abc.def"
    for bad in (None, "", "Token abc", "abc.def"):
        with pytest.raises(AuthError):
            auth.parse_bearer(bad)


def test_authenticate_from_header(auth):
    issued = auth.issue_token("mona-user", "Admin")
    context = auth.authenticate(f"Bearer {issued['token']}")
    assert context.role == "Admin"
    with pytest.raises(AuthError):
        auth.authenticate(None)


def test_policy_low_risk_auto_allow(engine):
    decision = engine.evaluate("browser.search", role="User")
    assert decision.decision == DECISION_ALLOW
    assert decision.allowed is True
    assert decision.requires_human_approval is False


def test_policy_high_risk_requires_approval(engine):
    decision = engine.evaluate("email.send", role="Admin")
    assert decision.decision == DECISION_REQUIRE_APPROVAL
    assert decision.requires_human_approval is True
    assert any("approval" in r for r in decision.reasons)


def test_policy_pre_approved_allows(engine):
    decision = engine.evaluate("email.send", role="Owner", approved=True)
    assert decision.decision == DECISION_ALLOW


def test_policy_denies_bad_role(engine):
    assert engine.evaluate("browser.search", role="Guest").decision == DECISION_DENY
    assert engine.evaluate("email.send", role="User").decision == DECISION_DENY


def test_policy_denies_unknown_tool(engine):
    assert engine.evaluate("no.such.tool", role="Admin").decision == DECISION_DENY


def test_policy_sensitive_intent_escalates_risk(engine):
    decision = engine.evaluate("http_fetch_like", role="Admin")
    assert decision.decision == DECISION_DENY
    risky = engine.classify_risk("files.read", intent="delete everything")
    assert risky == "HIGH"
    safe = engine.classify_risk("files.read", intent="read the report")
    assert safe == "LOW"


def test_policy_decision_shape(engine):
    decision = engine.evaluate("files.write", role="User")
    payload = decision.as_dict()
    assert set(payload) >= {"decision", "tool_name", "role", "risk", "allowed", "requires_human_approval", "reasons"}
    assert payload["details"]["policy_version"] == "2.1"


def test_verify_stage21_complete():
    payload = build_stage21_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert payload["passed"].endswith(f"/{payload['passed'].split('/')[1]}")
    assert payload["checks"]["tampered_token_rejected"] is True
    assert payload["checks"]["forged_signature_rejected"] is True
    assert payload["checks"]["high_risk_requires_approval"] is True
    assert all(payload["checks"].values()), payload["checks"]
    assert payload["auth"]["paid_provider"] is False
