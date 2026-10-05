from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

from fabric.registry.fastapi_approval import build_approval_verify_payload
from fabric.registry.orchestrator_guard import (
    CANONICAL_SPEC,
    OrchestratorGuard,
    get_orchestrator_guard,
    reset_orchestrator_guard,
)

TENANT = "pytest_tenant"


def _seed(tenant_id: str, actor: str, role: str = "Admin") -> None:
    try:
        from fabric.registry.tenant_isolation import get_tenant_manager

        get_tenant_manager().create_tenant_workspace(tenant_id, actor, role)
    except Exception:
        pass


@pytest.fixture(scope="module", autouse=True)
def _tenants():
    _seed(TENANT, "verifier", "Admin")
    _seed("pytest_tenant_a", "user_a_pytest", "User")
    _seed("pytest_tenant_b", "user_b_pytest", "User")


@pytest.fixture()
def guard():
    return get_orchestrator_guard()


def test_guard_singleton_and_reset():
    reset_orchestrator_guard()
    g = get_orchestrator_guard()
    assert isinstance(g, OrchestratorGuard)
    assert get_orchestrator_guard() is g


def test_all_layers_wired(guard):
    stats = guard.get_stats()
    assert stats["wired"] == {
        "policy_engine": True,
        "audit_log": True,
        "tenant_isolation": True,
        "approval_gate": True,
    }


def test_allow_low_risk_tool(guard):
    result = guard.guard("browser.search", {"query": "x"}, actor="verifier", role="User", tenant_id=TENANT)
    assert result["allowed"] is True
    assert result["decision"] == "ALLOW"
    assert result["canonical_spec"] == CANONICAL_SPEC
    assert result["zero_cost"] is True


def test_deny_email_send_for_user(guard):
    result = guard.guard("email.send", {}, actor="verifier", role="User", tenant_id=TENANT, resource="email.send")
    assert result["allowed"] is False
    assert result["decision"] == "DENY"


def test_mutating_tool_requires_approval(guard):
    result = guard.guard("files.write", {"path": "a.txt"}, actor="verifier", role="User", tenant_id=TENANT, resource="files.write")
    assert result["is_mutating"] is True
    assert result["decision"] == "REQUIRE_APPROVAL"
    assert result["allowed"] is False


def test_preapproved_mutating_tool_allowed(guard):
    result = guard.guard("files.write", {"path": "a.txt"}, actor="admin_probe", role="Admin", tenant_id=TENANT, resource="files.write", approved=True)
    assert result["allowed"] is True
    assert result["decision"] == "ALLOW"


def test_cross_tenant_denied(guard):
    result = guard.guard("files.write", {"path": "secret.txt"}, actor="user_a_pytest", role="User", tenant_id="pytest_tenant_b", resource="files.write")
    assert result["allowed"] is False
    assert result["decision"] == "DENY"
    assert "tenant" in result["stage"] or "isolation" in result.get("reason", "").lower()


def test_unknown_tool_denied(guard):
    result = guard.guard("no.such.tool", {}, actor="verifier", role="User", tenant_id=TENANT)
    assert result["allowed"] is False
    assert result["decision"] == "DENY"


def test_guard_writes_audit_entries(guard):
    from fabric.registry.audit_logger import get_audit_logger

    audit = get_audit_logger()
    before = len(audit.logs)
    guard.guard("browser.search", {}, actor="verifier", role="User", tenant_id=TENANT, resource="audit.pytest")
    assert len(audit.logs) > before
    assert audit.chain.verify_chain()["valid"] is True
    assert audit.get_stats()["total_logs"] == len(audit.logs)


def test_guard_async_short_circuits_on_allow(guard):
    result = asyncio.run(guard.guard_async("browser.search", {}, actor="verifier", role="User", tenant_id=TENANT))
    assert result["decision"] == "ALLOW"


def test_is_mutating_classifier():
    assert OrchestratorGuard.is_mutating("files.write") is True
    assert OrchestratorGuard.is_mutating("email.send") is True
    assert OrchestratorGuard.is_mutating("code.run") is True
    assert OrchestratorGuard.is_mutating("browser.search") is False
    assert OrchestratorGuard.is_mutating("files.read") is False


def test_thread_safe(guard):
    """Concurrency safety: all 10 threads get a decision and the chain stays valid.

    Unbound actors are expected to be DENIED by tenant isolation - that is correct
    governance, not a concurrency failure.
    """
    from fabric.registry.audit_logger import get_audit_logger

    results: list[Any] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        decision = guard.guard("browser.search", {}, actor=f"thread_{i}", role="User", tenant_id=TENANT).get("decision")
        with lock:
            results.append(decision)

    workers = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    assert len(results) == 10
    assert all(d in ("ALLOW", "DENY", "REQUIRE_APPROVAL") for d in results)
    assert get_audit_logger().chain.verify_chain()["valid"] is True


def test_stats_shape(guard):
    stats = guard.get_stats()
    assert set(stats) >= {"mutating_tools", "wired", "canonical_spec", "zero_cost"}
    assert stats["canonical_spec"] == CANONICAL_SPEC


@pytest.mark.parametrize("stage", ["2.2", "2.3"])
def test_verify_payload_complete(stage):
    payload = build_approval_verify_payload(stage)
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert payload["failed"] == 0
    assert payload["passed"] == payload["total"] == 14
    assert all(payload["checks"].values()), payload["checks"]
