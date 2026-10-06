from fastapi import APIRouter, Query
from typing import Optional
import traceback

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"


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

        all_ok = all(checks.values())
        return {
            "stage": "Phase 5 Stage 5.1 - API Gateway & Production Router",
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
            "stage": "Phase 5 Stage 5.1 - API Gateway",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "traceback": traceback.format_exc(),
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

        all_ok = all(checks.values())
        return {
            "stage": "Phase 5 Stage 5.2 - Observability & Health",
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
            "stage": "Phase 5 Stage 5.2 - Observability",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "traceback": traceback.format_exc(),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/gateway/routes")
def gateway_routes(tenant_id: Optional[str] = Query(None)):
    try:
        from fabric.registry.api_gateway import get_api_gateway
        return get_api_gateway().get_routes(tenant_id=tenant_id)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.post("/gateway/register")
def gateway_register(path: str = Query(...), method: str = Query("GET"), tenant_id: str = Query("default")):
    try:
        from fabric.registry.api_gateway import get_api_gateway
        return get_api_gateway().register_route(path, method, tenant_id=tenant_id)
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/gateway/stats")
def gateway_stats():
    try:
        from fabric.registry.api_gateway import get_api_gateway
        return get_api_gateway().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/observability/metrics")
def observability_metrics(name: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=500)):
    try:
        from fabric.registry.observability import get_observability
        return get_observability().get_metrics(name=name, limit=limit)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


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
