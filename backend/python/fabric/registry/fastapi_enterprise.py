from fastapi import APIRouter, Query
from typing import Dict, Optional
import time
import traceback

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


@router.get("/phase6/stage6.1/verify")
def verify_stage_6_1():
    checks = {}
    try:
        from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator, MODELS

        mo = get_multi_model_orchestrator()
        mo.history.clear()
        for m in MODELS:
            mo.set_availability(m, True)

        checks["1_exists"] = mo is not None

        r_pref = mo.select_model("any task", preferred="groq-llama")
        checks["2_select_model"] = r_pref.get("model") == "groq-llama"

        r_heur = mo.select_model("analyze this dataset for trends")
        checks["3_heuristic"] = r_heur.get("model") == "gemini-flash"

        r_fb = mo.fallback("groq-llama", "task after failure")
        checks["4_fallback"] = r_fb.get("fallback") == True and r_fb.get("model") is not None

        r_off = mo.set_availability("claude-haiku", False)
        r_on = mo.set_availability("claude-haiku", True)
        checks["5_set_availability"] = (
            r_off.get("success") == True and r_off.get("available") == False and r_on.get("available") == True
        )

        hist = mo.get_history()
        checks["6_history"] = hist.get("count", 0) >= 2

        checks["7_tool_registry_wired"] = mo._get_tool_registry() is not None
        checks["8_apex_wired"] = mo._get_apex_core() is not None

        stats = mo.get_stats()
        checks["9_models_count"] = stats.get("total_models", 0) >= 4
        checks["10_canonical_spec"] = r_pref.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost_isolated"] = r_pref.get("zero_cost") == True and r_pref.get("isolated") == True
        checks["12_stats_total_calls"] = stats.get("total_calls", 0) >= 2
        checks["13_wired"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_fallback_chain"] = len(stats.get("fallback_chain", [])) >= 4

        all_ok = all(checks.values())
        return {
            "stage": "Phase 6 Stage 6.1 - Multi-Model Orchestrator",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 6 Stage 6.1 - Multi-Model Orchestrator",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase6/stage6.2/verify")
def verify_stage_6_2():
    checks = {}
    try:
        from fabric.registry.advanced_cache import get_advanced_cache

        cache = get_advanced_cache()

        checks["1_exists"] = cache is not None

        r_set = cache.set("verify_key", "verify_value", ttl=30, tenant_id="verify_tenant", actor="verifier")
        checks["2_set_cache"] = r_set.get("success") == True

        r_get = cache.get("verify_key", tenant_id="verify_tenant")
        checks["3_get_cache"] = r_get.get("found") == True and r_get.get("value") == "verify_value"

        r_hit = cache.get("verify_key", tenant_id="verify_tenant")
        checks["4_cache_hit"] = r_hit.get("hit") == True

        r_miss = cache.get("non_existent_key", tenant_id="verify_tenant")
        checks["5_cache_miss"] = r_miss.get("found") == False

        r_del = cache.delete("verify_key")
        checks["6_delete"] = r_del.get("success") == True and r_del.get("deleted") == True

        cache.set("ttl_key", "ttl_value", ttl=1, tenant_id="verify_tenant", actor="verifier")
        time.sleep(1.1)
        r_ttl = cache.get("ttl_key", tenant_id="verify_tenant")
        checks["7_ttl_expiry"] = r_ttl.get("found") == False and r_ttl.get("reason") == "Expired"

        r_clear = cache.clear_expired()
        checks["8_clear_expired"] = "cleared" in r_clear and "remaining" in r_clear

        checks["9_memory_store_wired"] = cache._get_memory_store() is not None
        checks["10_canonical_spec"] = r_set.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost"] = r_set.get("zero_cost") == True

        stats = cache.get_stats()
        checks["12_stats_total_entries"] = "total_entries" in stats and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_hit_rate"] = "hit_rate" in stats and stats.get("hits", 0) >= 1 and stats.get("misses", 0) >= 1

        all_ok = all(checks.values())
        return {
            "stage": "Phase 6 Stage 6.2 - Advanced Cache",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 6 Stage 6.2 - Advanced Cache",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase6/stage6.3/verify")
def verify_stage_6_3():
    checks = {}
    try:
        from fabric.registry.enterprise_audit import get_enterprise_audit

        ent = get_enterprise_audit()

        checks["1_exists"] = ent is not None

        r_event = ent.record_enterprise_event("verify.event", "verifier", "verify_tenant", {"source": "verify"}, severity="INFO")
        checks["2_record_event"] = r_event.get("success") == True

        r_comp = ent.generate_compliance_report(tenant_id="verify_tenant", actor="verifier")
        checks["3_generate_compliance"] = bool(r_comp.get("report")) and bool(r_comp.get("stages"))
        checks["4_stages_total"] = r_comp.get("total", 0) >= 14
        checks["5_compliance_pass"] = r_comp.get("passed") == r_comp.get("total")

        reports = ent.get_reports()
        checks["6_get_reports"] = reports.get("count", 0) >= 1

        checks["7_audit_logger_wired"] = ent._get_audit_logger() is not None
        checks["8_governance_wired"] = ent._get_governance() is not None
        checks["9_release_wired"] = ent._get_release_manager() is not None
        checks["10_compliance_field"] = r_comp.get("compliance") == "COMPLIANT"
        checks["11_canonical_spec"] = r_comp.get("canonical_spec") == CANONICAL_SPEC
        checks["12_zero_cost"] = r_comp.get("zero_cost") == True

        stats = ent.get_stats()
        checks["13_stats"] = stats.get("total_audits", 0) >= 1 and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["14_wired_dod"] = "wired" in stats and all(stats.get("wired", {}).values()) and "Understand->Plan" in stats.get("dod_ref", "")

        all_ok = all(checks.values())
        return {
            "stage": "Phase 6 Stage 6.3 - Enterprise Audit Dashboard",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "compliance": r_comp.get("compliance"),
            "stages": r_comp.get("total"),
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 6 Stage 6.3 - Enterprise Audit Dashboard",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.post("/enterprise/select-model")
def enterprise_select_model(task: str = Query(...), preferred: Optional[str] = Query(None)):
    try:
        from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

        return get_multi_model_orchestrator().select_model(task, preferred=preferred)
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.post("/enterprise/cache/set")
def enterprise_cache_set(key: str = Query(...), value: str = Query(...), ttl: int = Query(3600, ge=1), tenant_id: str = Query("default")):
    try:
        from fabric.registry.advanced_cache import get_advanced_cache

        return get_advanced_cache().set(key, value, ttl=ttl, tenant_id=tenant_id, actor="api")
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/enterprise/cache/get/{key}")
def enterprise_cache_get(key: str, tenant_id: str = Query("default")):
    try:
        from fabric.registry.advanced_cache import get_advanced_cache

        return get_advanced_cache().get(key, tenant_id=tenant_id)
    except Exception as e:
        return {"found": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.post("/enterprise/audit/event")
def enterprise_audit_event(event: str = Query(...), actor: str = Query("api"), tenant_id: str = Query("default"), severity: str = Query("INFO")):
    try:
        from fabric.registry.enterprise_audit import get_enterprise_audit

        return get_enterprise_audit().record_enterprise_event(event, actor, tenant_id, severity=severity)
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/enterprise/compliance/report")
def enterprise_compliance_report(tenant_id: str = Query("default"), actor: str = Query("api")):
    try:
        from fabric.registry.enterprise_audit import get_enterprise_audit

        return get_enterprise_audit().generate_compliance_report(tenant_id=tenant_id, actor=actor)
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/enterprise/stats")
def enterprise_stats():
    try:
        from fabric.registry.enterprise_audit import get_enterprise_audit

        return get_enterprise_audit().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/phase6/mega/verify")
async def verify_phase6_mega():
    """Phase 6 FULL MEGA - every stage 2.4 through 6.3 in one pass.

    Stage probing delegates to the central stage sweep (gate D1).
    """
    from fabric.registry.stage_sweep import run_stage_sweep

    sweep = run_stage_sweep(start="2.4", end="6.3", actor="mega6", tenant_id="mega6")
    results = sweep["stages"]
    details = sweep["details"]
    all_ok = sweep["all_checks"]
    return {
        "phase": "Phase 6 — Enterprise Scale — FULL MEGA 2.4-6.3",
        "status": "PHASE 6 FULL COMPLETE ENTERPRISE READY" if all_ok else f"INCOMPLETE failed {[k for k, v in results.items() if not v]}",
        "all_checks": all_ok,
        "stages": results,
        "details": details,
        "passed": sweep["passed"],
        "total": sweep["total"],
        "canonical_spec": CANONICAL_SPEC,
        "zero_cost": True,
        "next": "MONA - Powered by Apex Core" if all_ok else "Fix failed stages",
        "governance": "Build → Test → Verify → Human Review → Commit → Push → Next",
        "dod_ref": DOD_REF,
    }
