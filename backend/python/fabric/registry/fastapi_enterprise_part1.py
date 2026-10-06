from fastapi import APIRouter
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
            "traceback": traceback.format_exc(),
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
            "traceback": traceback.format_exc(),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }
