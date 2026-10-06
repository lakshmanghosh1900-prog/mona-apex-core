import time

import pytest

CANONICAL_SPEC = "MONA - Powered by Apex Core"


# ---------- Stage 6.1 - Multi-Model Orchestrator (14) ----------


def test_multi_model_orchestrator_exists():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    assert mo is not None
    assert get_multi_model_orchestrator() is mo


def test_select_model_preferred():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.select_model("any task", preferred="groq-llama")
    assert r["model"] == "groq-llama"
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_select_model_heuristic():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.select_model("analyze this dataset")
    assert r["model"] == "gemini-flash"
    r2 = mo.select_model("search the web for news")
    assert r2["model"] == "groq-llama"


def test_fallback():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.fallback("groq-llama", "task")
    assert r["fallback"] == True
    assert r["model"] is not None
    assert r["model"] != "groq-llama"


def test_set_availability():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r_off = mo.set_availability("claude-haiku", False)
    assert r_off["success"] == True
    assert r_off["available"] == False
    r_on = mo.set_availability("claude-haiku", True)
    assert r_on["available"] == True
    r_bad = mo.set_availability("unknown-model", True)
    assert r_bad["success"] == False


def test_history_count():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    mo.select_model("history task one")
    mo.select_model("history task two")
    h = mo.get_history()
    assert h["count"] >= 2
    assert h["history"][-1]["task"] == "history task two"
    assert h["canonical_spec"] == CANONICAL_SPEC


def test_tool_registry_wired():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    assert mo._get_tool_registry() is not None


def test_apex_core_wired():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    assert mo._get_apex_core() is not None


def test_models_count():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    s = mo.get_stats()
    assert s["total_models"] >= 4
    assert s["available"] >= 4


def test_canonical_spec_model():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.select_model("canonical task")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert mo.get_stats()["canonical_spec"] == CANONICAL_SPEC
    assert mo.get_history()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_isolated_model():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.select_model("zero cost task")
    assert r["zero_cost"] == True
    assert r["isolated"] == True
    assert mo.get_stats()["zero_cost"] == True


def test_stats_total_calls():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    before = mo.get_stats()["total_calls"]
    mo.select_model("counted task")
    after = mo.get_stats()["total_calls"]
    assert after == before + 1
    assert mo.get_stats()["total_failures"] >= 0


def test_stats_wired_model():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    s = mo.get_stats()
    assert "wired" in s
    assert set(s["wired"]) >= {"tool_registry", "apex_core"}
    assert all(s["wired"].values())
    assert "Understand->Plan" in s["dod_ref"]


def test_fallback_chain_length():
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator, MODELS

    mo = get_multi_model_orchestrator()
    s = mo.get_stats()
    assert len(s["fallback_chain"]) >= 4
    assert s["fallback_chain"] == MODELS


# ---------- Stage 6.2 - Advanced Cache (14) ----------


def test_advanced_cache_exists():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    assert cache is not None
    assert get_advanced_cache() is cache


def test_set_cache():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    r = cache.set("part1_set_key", "part1_value", ttl=30, tenant_id="part1_tenant", actor="tester")
    assert r["success"] == True
    assert r["key"] == "part1_set_key"
    assert r["ttl"] == 30
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_get_cache_found():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_get_key", "part1_get_value", ttl=30, tenant_id="part1_tenant", actor="tester")
    r = cache.get("part1_get_key", tenant_id="part1_tenant")
    assert r["found"] == True
    assert r["value"] == "part1_get_value"


def test_cache_hit():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_hit_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    cache.get("part1_hit_key", tenant_id="part1_tenant")
    r = cache.get("part1_hit_key", tenant_id="part1_tenant")
    assert r["hit"] == True
    assert cache.hits >= 1


def test_cache_miss():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    r = cache.get("part1_never_set", tenant_id="part1_tenant")
    assert r["found"] == False
    assert r["reason"] == "Cache miss"
    assert cache.misses >= 1


def test_delete_cache_entry():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_del_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    r = cache.delete("part1_del_key")
    assert r["success"] == True
    assert r["deleted"] == True
    r2 = cache.delete("part1_del_key")
    assert r2["success"] == False


def test_ttl_expiry():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_ttl_key", "v", ttl=1, tenant_id="part1_tenant", actor="tester")
    time.sleep(1.1)
    r = cache.get("part1_ttl_key", tenant_id="part1_tenant")
    assert r["found"] == False
    assert r["reason"] == "Expired"


def test_clear_expired():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_clear_key", "v", ttl=1, tenant_id="part1_tenant", actor="tester")
    time.sleep(1.1)
    r = cache.clear_expired()
    assert "cleared" in r
    assert "remaining" in r
    assert r["cleared"] >= 1


def test_memory_store_wired():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    assert cache._get_memory_store() is not None


def test_canonical_spec_cache():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    r = cache.set("part1_canonical_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert cache.get_stats()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_cache():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    r = cache.set("part1_zero_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    assert r["zero_cost"] == True
    assert cache.get_stats()["zero_cost"] == True


def test_stats_total_entries():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_stats_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    s = cache.get_stats()
    assert "total_entries" in s
    assert s["total_entries"] >= 1
    assert "Understand->Plan" in s["dod_ref"]


def test_stats_wired_cache():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    s = cache.get_stats()
    assert "wired" in s
    assert "memory_store" in s["wired"]
    assert all(s["wired"].values())
    assert s["zero_cost"] == True


def test_hit_rate():
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    cache.set("part1_rate_key", "v", ttl=30, tenant_id="part1_tenant", actor="tester")
    cache.get("part1_rate_key", tenant_id="part1_tenant")
    cache.get("part1_rate_missing", tenant_id="part1_tenant")
    s = cache.get_stats()
    assert "hit_rate" in s
    assert s["hits"] >= 1
    assert s["misses"] >= 1
    assert 0 <= s["hit_rate"] <= 100


# ---------- Stage 6.3 - Enterprise Audit Dashboard (14) ----------


def test_enterprise_audit_exists():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    assert ent is not None
    assert get_enterprise_audit() is ent


def test_record_enterprise_event():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.record_enterprise_event("unit.event", "tester", "ent_tenant", {"k": "v"}, severity="WARN")
    assert r["success"] == True
    assert r["event"] == "unit.event"
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert any(a["event"] == "unit.event" for a in ent.audits)



def test_generate_compliance_report():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    assert "report" in r
    assert "stages" in r
    assert r["success"] == True


def test_compliance_stages_total():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    assert r["total"] >= 14
    assert r["total"] == len(r["stages"])
    assert "6.3" in r["stages"]
    assert r["passed"] == r["total"]


def test_get_reports():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    h = ent.get_reports()
    assert h["count"] >= 1
    assert h["reports"][-1]["compliance"] == "COMPLIANT"
    assert h["canonical_spec"] == CANONICAL_SPEC


def test_audit_logger_wired():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    assert ent._get_audit_logger() is not None


def test_governance_wired():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    assert ent._get_governance() is not None


def test_release_manager_wired():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    assert ent._get_release_manager() is not None


def test_compliance_field():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    assert r["compliance"] == "COMPLIANT"
    assert r["report"]["compliance"] == "COMPLIANT"
    assert r["production_ready"] == True
    assert r["all_checks"] == True


def test_canonical_spec_enterprise():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert ent.get_stats()["canonical_spec"] == CANONICAL_SPEC
    assert ent.get_reports()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_enterprise():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id="ent_tenant", actor="tester")
    assert r["zero_cost"] == True
    assert ent.get_stats()["zero_cost"] == True


def test_stats_total_audits():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    before = ent.get_stats()["total_audits"]
    ent.record_enterprise_event("stats.event", "tester", "ent_tenant")
    after = ent.get_stats()["total_audits"]
    assert after == before + 1
    assert ent.get_stats()["total_reports"] >= 1


def test_stats_wired_enterprise():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    s = ent.get_stats()
    assert "wired" in s
    assert set(s["wired"]) >= {"audit_logger", "governance", "release_manager"}
    assert all(s["wired"].values())
    assert s["compliant"] >= 1
    assert s["non_compliant"] == 0


def test_stats_dod_ref():
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    s = ent.get_stats()
    assert "Understand->Plan" in s["dod_ref"]
    assert s["zero_cost"] == True
    assert s["canonical_spec"] == CANONICAL_SPEC
