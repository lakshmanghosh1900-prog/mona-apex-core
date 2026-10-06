import pytest

from fabric.registry.orchestrator_core import get_staged_orchestrator


@pytest.fixture()
def orch():
    return get_staged_orchestrator()


def test_orchestrator_exists(orch):
    assert orch is not None


def test_tool_registry_wired(orch):
    assert orch._get_tool_registry() is not None


def test_execution_sandbox_wired(orch):
    assert orch._get_execution_sandbox() is not None


def test_memory_store_wired(orch):
    assert orch._get_memory_store() is not None


def test_guard_wired(orch):
    assert orch._get_guard() is not None


def test_audit_wired(orch):
    assert orch._get_audit() is not None


def test_understand(orch):
    r = orch.understand("search web for cats")
    assert r["understood"] == True
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_plan(orch):
    r = orch.plan("search web for cats")
    assert "tool" in r
    assert "model" in r
    assert r["tool"] == "browser.search"


def test_execute(orch):
    r = orch.execute("search web for test", actor="verifier", tenant_id="verify_tenant")
    assert "tool" in r
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert r["success"] == True


def test_canonical_spec(orch):
    r = orch.execute("test task", actor="verifier", tenant_id="verify_tenant")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_zero_cost_isolated(orch):
    r = orch.execute("test task", actor="verifier", tenant_id="verify_tenant")
    assert r["zero_cost"] == True
    assert r["isolated"] == True


def test_dod_ref(orch):
    r = orch.execute("test task", actor="verifier", tenant_id="verify_tenant")
    assert "dod_ref" in r
    assert "Understand->Plan" in r["dod_ref"]


def test_stats(orch):
    s = orch.get_stats()
    assert "total_runs" in s
    assert "wired" in s
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"
    assert all(s["wired"].values())


def test_self_heal(orch):
    r = orch.execute("analyze complex data", actor="verifier", tenant_id="verify_tenant")
    assert "retries" in r
    assert "verify_ok" in r
    assert isinstance(r["retries"], int)
