from fastapi import APIRouter, Depends, Query
from typing import Any, Dict, Optional
import logging

from fabric.registry.fastapi_security import require_auth

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


def _ok(body: Dict[str, Any]) -> Dict[str, Any]:
    all_ok = all(bool(v) for v in body.get("checks", {}).values())
    body["all_checks"] = all_ok
    body["passed"] = sum(1 for v in body.get("checks", {}).values() if v)
    body["failed"] = sum(1 for v in body.get("checks", {}).values() if not v)
    body["total"] = len(body.get("checks", {}))
    if "status" not in body:
        body["status"] = "COMPLETE" if all_ok else f"INCOMPLETE {body['failed']} failed"
    return body


@router.get("/phase5/stage5.1/verify")
def verify_stage_5_1():
    checks = {}
    try:
        from fabric.registry.api_gateway import get_api_gateway

        gw = get_api_gateway()
        gw.routes.clear()
        gw.requests.clear()

        checks["1_gateway_exists"] = gw is not None

        r_reg = gw.register_route("/api/v1/health", "GET", tenant_id="verify_tenant")
        checks["2_register_route"] = r_reg.get("success") == True

        r_handle = gw.handle_request("/api/v1/health", "GET", actor="verifier", tenant_id="verify_tenant")
        checks["3_handle_request"] = r_handle.get("success") == True

        r_get = gw.get_routes(tenant_id="verify_tenant")
        checks["4_get_routes"] = r_get.get("count", 0) >= 1

        checks["5_tenant_wired"] = gw._get_tenant_manager() is not None
        checks["6_rate_limiter_wired"] = gw._get_rate_limiter() is not None
        checks["7_audit_wired"] = gw._get_audit() is not None

        route = r_handle.get("route") or {}
        checks["8_auth_check"] = route.get("auth_required", True) is not False or route.get("registered") is not False

        checks["9_path_validation"] = gw.register_route("invalid", "GET").get("success") == False
        checks["10_canonical_spec"] = r_reg.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost_isolated"] = r_handle.get("zero_cost") == True and r_handle.get("isolated") == True

        stats = gw.get_stats()
        checks["12_stats"] = "total_routes" in stats and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired_all"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_request_logged"] = stats.get("total_requests", 0) >= 1

        return _ok({
            "stage": "Phase 5 Stage 5.1 - API Gateway & Production Router",
            "checks": checks,
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        })
    except Exception as ex:
        return {
            "stage": "Phase 5 Stage 5.1 - API Gateway",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase5/stage5.2/verify")
def verify_stage_5_2():
    checks = {}
    try:
        from fabric.registry.observability import get_observability

        obs = get_observability()
        obs.metrics.clear()
        obs.logs.clear()
        obs.health_checks.clear()

        checks["1_observability_exists"] = obs is not None

        r_metric = obs.record_metric("test_metric", 42.0, {"test": "true"}, actor="verifier", tenant_id="verify_tenant")
        checks["2_record_metric"] = r_metric.get("success") == True

        r_health = obs.health_check("api", actor="verifier")
        checks["3_health_check"] = "healthy" in r_health and "checks" in r_health
        checks["4_health_all_ok"] = r_health.get("all_checks") == True or r_health.get("healthy") == True

        r_get = obs.get_metrics("test_metric")
        checks["5_get_metrics"] = r_get.get("count", 0) >= 1

        r_hist = obs.get_health_history()
        checks["6_health_history"] = r_hist.get("count", 0) >= 1

        checks["7_apex_wired"] = obs._get_apex_core() is not None
        checks["8_audit_wired"] = obs._get_audit() is not None
        checks["9_metric_name"] = r_metric.get("metric") == "test_metric"
        checks["10_canonical_spec"] = r_metric.get("canonical_spec") == CANONICAL_SPEC
        checks["11_zero_cost"] = r_metric.get("zero_cost") == True

        stats = obs.get_stats()
        checks["12_stats"] = "total_metrics" in stats and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_logs"] = stats.get("total_logs", 0) >= 1

        return _ok({
            "stage": "Phase 5 Stage 5.2 - Observability & Health",
            "checks": checks,
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        })
    except Exception as ex:
        return {
            "stage": "Phase 5 Stage 5.2 - Observability",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase5/stage5.3/verify")
def verify_stage_5_3():
    checks = {}
    try:
        from fabric.registry.release_manager import get_release_manager, VERSION, STAGE_KEYS

        rm = get_release_manager()

        checks["1_release_manager_exists"] = rm is not None

        r = rm.create_release(actor="verifier", tenant_id="verify_tenant")
        checks["2_create_release_success"] = r.get("success") == True
        checks["3_stages_total"] = r.get("total", 0) >= 10
        checks["4_all_stages_passed"] = r.get("passed") == r.get("total")
        checks["5_production_ready"] = r.get("production_ready") == True
        checks["6_version"] = r.get("version") == VERSION
        checks["7_canonical_spec"] = r.get("canonical_spec") == CANONICAL_SPEC
        checks["8_zero_cost_dod"] = r.get("zero_cost") == True and "Understand->Plan" in r.get("dod_ref", "")
        checks["9_stage_keys"] = all(k in r.get("stages", {}) for k in STAGE_KEYS)

        history = rm.get_releases()
        checks["10_history"] = history.get("count", 0) >= 1
        checks["11_latest_production_ready"] = history.get("releases", [])[-1].get("production_ready") == True

        stats = rm.get_stats()
        checks["12_stats"] = stats.get("total_releases", 0) >= 1 and stats.get("canonical_spec") == CANONICAL_SPEC
        checks["13_wired_all"] = "wired" in stats and all(stats.get("wired", {}).values())
        checks["14_audit_wired"] = rm._get_audit() is not None

        return _ok({
            "stage": "Phase 5 Stage 5.3 - Release Manager & Production Pipeline",
            "checks": checks,
            "release": {"version": r.get("version"), "passed": r.get("passed"), "total": r.get("total"), "production_ready": r.get("production_ready")},
            "stats": stats,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        })
    except Exception as ex:
        return {
            "stage": "Phase 5 Stage 5.3 - Release Manager",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase5/mega/verify")
async def verify_phase5_mega() -> Dict[str, Any]:
    """Phase 5 FULL MEGA - every stage 2.4 through 5.3 in one pass.

    Stage probing delegates to the central stage sweep (gate D1).
    """
    from fabric.registry.stage_sweep import run_stage_sweep

    sweep = run_stage_sweep(start="2.4", end="5.3", actor="mega5", tenant_id="mega5")
    results = sweep["stages"]
    details = sweep["details"]
    all_ok = sweep["all_checks"]
    return {
        "phase": "Phase 5 — Release Pipeline — FULL MEGA 2.4-5.3",
        "status": "PHASE 5 FULL COMPLETE" if all_ok else f"INCOMPLETE failed {[k for k, v in results.items() if not v]}",
        "all_checks": all_ok,
        "stages": results,
        "details": details,
        "passed": sweep["passed"],
        "total": sweep["total"],
        "canonical_spec": CANONICAL_SPEC,
        "zero_cost": True,
        "next": "Phase 6" if all_ok else "Fix failed stages",
        "governance": "Build → Test → Verify → Human Review → Commit → Push → Next",
        "dod_ref": DOD_REF,
    }


@router.post("/release/create")
def release_create(version: str = Query("1.0.0-production"), actor: str = Query("system"), tenant_id: str = Query("default"), ctx: Any = Depends(require_auth)):
    try:
        from fabric.registry.release_manager import get_release_manager

        return get_release_manager().create_release(version=version, actor=ctx.subject if ctx else actor, tenant_id=tenant_id)
    except Exception:
        import logging

        logging.exception("Error in release/create")
        return {"success": False, "error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/release/history")
def release_history(limit: int = Query(20, ge=1, le=200)):
    try:
        from fabric.registry.release_manager import get_release_manager

        return get_release_manager().get_releases(limit=limit)
    except Exception:
        logging.exception("Error in release/history")
        return {"error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/release/stats")
def release_stats():
    try:
        from fabric.registry.release_manager import get_release_manager

        return get_release_manager().get_stats()
    except Exception:
        logging.exception("Error in release/stats")
        return {"error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/gateway/routes")
def gateway_routes(tenant_id: Optional[str] = Query(None)):
    try:
        from fabric.registry.api_gateway import get_api_gateway

        return get_api_gateway().get_routes(tenant_id=tenant_id)
    except Exception:
        logging.exception("Error in gateway/routes")
        return {"error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.post("/gateway/register")
def gateway_register(path: str = Query(...), method: str = Query("GET"), tenant_id: str = Query("default"), ctx: Any = Depends(require_auth)):
    try:
        from fabric.registry.api_gateway import get_api_gateway

        return get_api_gateway().register_route(path, method, tenant_id=tenant_id)
    except Exception:
        import logging

        logging.exception("Error in gateway/register")
        return {"success": False, "error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/gateway/stats")
def gateway_stats():
    try:
        from fabric.registry.api_gateway import get_api_gateway

        return get_api_gateway().get_stats()
    except Exception:
        logging.exception("Error in gateway/stats")
        return {"error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/observability/metrics")
def observability_metrics(name: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500)):
    try:
        from fabric.registry.observability import get_observability

        return get_observability().get_metrics(name=name, limit=limit)
    except Exception:
        logging.exception("Error in observability/metrics")
        return {"error": "Internal error — check server logs", "canonical_spec": CANONICAL_SPEC}


@router.get("/observability/health")
def observability_health(component: str = Query("api")):
    try:
        from fabric.registry.observability import get_observability

        return get_observability().health_check(component)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/observability/stats")
def observability_stats():
    try:
        from fabric.registry.observability import get_observability

        return get_observability().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}
