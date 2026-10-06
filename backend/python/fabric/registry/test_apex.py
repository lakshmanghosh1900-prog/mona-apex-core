import pytest

# ---------------------------------------------------------------------------
# Stage 4.1 — Evidence Chain & Report Generator (14)
# ---------------------------------------------------------------------------


def test_evidence_chain_exists():
    from fabric.registry.evidence_chain import get_evidence_chain
    assert get_evidence_chain() is not None


def test_report_generator_exists():
    from fabric.registry.report_generator import get_report_generator
    assert get_report_generator() is not None


def test_append_evidence():
    from fabric.registry.evidence_chain import get_evidence_chain
    r = get_evidence_chain().append("test_41", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    assert r["success"] == True
    assert "hash" in r
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_get_chain():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    ec.append("test_41_get", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    r = ec.get_chain("test_41_get", tenant_id="verify_tenant")
    assert r["found"] == True
    assert r["length"] >= 1


def test_verify_chain_valid():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    ec.append("test_41_verify", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    assert ec.verify_chain("test_41_verify")["valid"] == True


def test_append_second():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    r1 = ec.append("test_41_second", {"data": "first"}, actor="verifier", tenant_id="verify_tenant")
    r2 = ec.append("test_41_second", {"data": "second"}, actor="verifier", tenant_id="verify_tenant")
    assert r2["success"] == True
    assert r2["prev_hash"] == r1["hash"]


def test_chain_length_2():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    ec.append("test_41_len", {"data": "1"}, actor="verifier", tenant_id="verify_tenant")
    ec.append("test_41_len", {"data": "2"}, actor="verifier", tenant_id="verify_tenant")
    assert ec.get_chain("test_41_len", tenant_id="verify_tenant")["length"] == 2


def test_tamper_detected():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    ec.append("test_41_tamper", {"data": "honest"}, actor="verifier", tenant_id="verify_tenant")
    ec.chains["test_41_tamper"][0]["evidence"] = {"data": "forged"}
    assert ec.verify_chain("test_41_tamper")["valid"] == False


def test_generate_report():
    from fabric.registry.evidence_chain import get_evidence_chain
    from fabric.registry.report_generator import get_report_generator
    get_evidence_chain().append("test_41_report", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    r = get_report_generator().generate("test_41_report", actor="verifier", tenant_id="verify_tenant")
    assert r["success"] == True
    assert r["evidence_blocks"] >= 1


def test_get_report():
    from fabric.registry.evidence_chain import get_evidence_chain
    from fabric.registry.report_generator import get_report_generator
    get_evidence_chain().append("test_41_getrep", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    get_report_generator().generate("test_41_getrep", actor="verifier", tenant_id="verify_tenant")
    assert get_report_generator().get_report("test_41_getrep", tenant_id="verify_tenant")["found"] == True


def test_canonical_spec_41():
    from fabric.registry.evidence_chain import get_evidence_chain
    r = get_evidence_chain().append("test_41_canon", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"


def test_zero_cost_41():
    from fabric.registry.evidence_chain import get_evidence_chain
    r = get_evidence_chain().append("test_41_zc", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    assert r["zero_cost"] == True


def test_stats_41():
    from fabric.registry.evidence_chain import get_evidence_chain
    from fabric.registry.report_generator import get_report_generator
    es = get_evidence_chain().get_stats()
    rs = get_report_generator().get_stats()
    assert "total_chains" in es
    assert "total_blocks" in es
    assert "total_reports" in rs
    assert es["canonical_spec"] == "MONA - Powered by Apex Core"
    assert es["zero_cost"] == True
    assert rs["zero_cost"] == True


def test_tenant_isolation_41():
    from fabric.registry.evidence_chain import get_evidence_chain
    ec = get_evidence_chain()
    ec.append("test_41_iso", {"data": "test"}, actor="verifier", tenant_id="verify_tenant")
    r = ec.get_chain("test_41_iso", tenant_id="other_tenant")
    assert r["found"] == False
    assert "Tenant isolation" in r["reason"]


# ---------------------------------------------------------------------------
# Stage 4.2 — Governance Engine (14)
# ---------------------------------------------------------------------------


def test_governance_engine_exists():
    from fabric.registry.governance_engine import get_governance_engine
    assert get_governance_engine() is not None


def test_tenant_manager_wired():
    from fabric.registry.governance_engine import get_governance_engine
    assert get_governance_engine()._get_tenant_manager() is not None


def test_guard_wired():
    from fabric.registry.governance_engine import get_governance_engine
    assert get_governance_engine()._get_guard() is not None


def test_audit_wired():
    from fabric.registry.governance_engine import get_governance_engine
    assert get_governance_engine()._get_audit() is not None


def test_check_tenant():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().check_tenant("verify_tenant")
    assert r["check"] == "tenant"
    assert r["passed"] == True


def test_check_permission():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().check_permission("browser.search", "verifier", "verify_tenant")
    assert r["check"] == "permission"
    assert "passed" in r
    assert r["passed"] == True


def test_check_audit():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().check_audit()
    assert r["check"] == "audit"
    assert "passed" in r


def test_check_secrets():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().check_secrets()
    assert r["check"] == "secrets"
    assert "passed" in r


def test_check_rate_limit():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().check_rate_limit("verify_tenant", "verifier")
    assert r["check"] == "rate_limit"
    assert r["passed"] == True


def test_full_compliance():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().full_compliance_check("search web", "verifier", "verify_tenant", "browser.search")
    assert "all_passed" in r
    assert "checks" in r
    assert r["total"] == 5
    assert r["all_passed"] == True


def test_canonical_spec_42():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().full_compliance_check("test", "verifier", "verify_tenant", "browser.search")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert "Resume Later" in r["dod_ref"]


def test_zero_cost_42():
    from fabric.registry.governance_engine import get_governance_engine
    r = get_governance_engine().full_compliance_check("test", "verifier", "verify_tenant", "browser.search")
    assert r["zero_cost"] == True


def test_stats_42():
    from fabric.registry.governance_engine import get_governance_engine
    s = get_governance_engine().get_stats()
    assert "total_checks" in s
    assert "wired" in s
    assert "passed" in s
    assert "failed" in s
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"


def test_history_recorded():
    from fabric.registry.governance_engine import get_governance_engine
    gov = get_governance_engine()
    gov.compliance_history.clear()
    gov.full_compliance_check("test", "verifier", "verify_tenant", "browser.search")
    assert len(gov.compliance_history) >= 1


# ---------------------------------------------------------------------------
# Stage 4.3 — Apex Core End-to-End (14)
# ---------------------------------------------------------------------------


def test_apex_core_exists():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core() is not None


def test_tool_registry_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_tool_registry() is not None


def test_execution_sandbox_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_execution_sandbox() is not None


def test_memory_store_wired_apex():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_memory_store() is not None


def test_evidence_chain_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_evidence_chain() is not None


def test_report_generator_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_report_generator() is not None


def test_governance_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_governance_engine() is not None


def test_orchestrator_wired():
    from fabric.registry.apex_core import get_apex_core
    assert get_apex_core()._get_orchestrator() is not None


def test_run_task():
    from fabric.registry.apex_core import get_apex_core
    r = get_apex_core().run("search web for apex test", actor="verifier", tenant_id="verify_tenant")
    assert r["task_id"] is not None
    assert "tool" in r
    assert r["success"] == True
    assert r["governance"]["all_passed"] == True


def test_canonical_dod():
    from fabric.registry.apex_core import get_apex_core
    r = get_apex_core().run("test apex canonical", actor="verifier", tenant_id="verify_tenant")
    assert r["canonical_spec"] == "MONA - Powered by Apex Core"
    assert "dod_ref" in r
    assert "Understand->Plan" in r["dod_ref"]


def test_zero_cost_isolated_apex():
    from fabric.registry.apex_core import get_apex_core
    r = get_apex_core().run("test apex zero", actor="verifier", tenant_id="verify_tenant")
    assert r["zero_cost"] == True
    assert r["isolated"] == True
    assert r["apex_core"] == True


def test_evidence_report_generated():
    from fabric.registry.apex_core import get_apex_core
    r = get_apex_core().run("test apex evidence", actor="verifier", tenant_id="verify_tenant")
    assert r["evidence_chain"] is not None
    assert r["report"] is not None
    assert r["report"]["success"] == True


def test_stats_apex():
    from fabric.registry.apex_core import get_apex_core
    s = get_apex_core().get_stats()
    assert "total_runs" in s
    assert "wired" in s
    assert s["canonical_spec"] == "MONA - Powered by Apex Core"
    assert s["zero_cost"] == True
    assert all(s["wired"].values())


def test_governance_inside_run():
    from fabric.registry.apex_core import get_apex_core
    r = get_apex_core().run("test apex gov", actor="verifier", tenant_id="verify_tenant")
    assert r["governance"] is not None
    assert "checks" in r["governance"]
    # denial still returns a complete, auditable document
    assert r["evidence_chain"] is not None
    assert r["report"] is not None
