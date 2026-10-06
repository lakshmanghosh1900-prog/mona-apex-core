import pytest

CANONICAL_SPEC = "MONA - Powered by Apex Core"


# ---------- Stage 5.1 - API Gateway (14) ----------


def test_gateway_exists():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    assert gw is not None
    assert get_api_gateway() is gw


def test_register_route_success():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.register_route("/api/v1/test_register", "GET", tenant_id="part1_tenant")
    assert r["success"] == True
    assert r["route"] == "GET:/api/v1/test_register"
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_register_route_invalid_path():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.register_route("invalid", "GET")
    assert r["success"] == False
    assert "start with" in r["reason"]
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_handle_request_success():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    gw.register_route("/api/v1/test_handle", "GET", tenant_id="part1_tenant")
    r = gw.handle_request("/api/v1/test_handle", "GET", actor="tester", tenant_id="part1_tenant")
    assert r["success"] == True
    assert r["path"] == "/api/v1/test_handle"
    assert r["method"] == "GET"
    assert r["tenant_id"] == "part1_tenant"


def test_handle_request_unregistered_route():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.handle_request("/api/v1/never_registered", "GET", actor="tester", tenant_id="default")
    assert r["success"] == True
    assert r["route"].get("registered") is False


def test_get_routes_tenant_filter():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    gw.register_route("/api/v1/tenant_scoped", "GET", tenant_id="part1_scoped")
    r = gw.get_routes(tenant_id="part1_scoped")
    assert r["count"] >= 1
    assert all(item.get("tenant_id") == "part1_scoped" for item in r["routes"])


def test_get_routes_all():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    gw.register_route("/api/v1/all_routes", "POST", tenant_id="default")
    r = gw.get_routes()
    assert r["count"] >= 2
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_request_logged():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    before = gw.get_stats()["total_requests"]
    gw.handle_request("/api/v1/log_me", "GET", actor="tester", tenant_id="default")
    after = gw.get_stats()["total_requests"]
    assert after == before + 1


def test_canonical_spec_gateway():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.register_route("/api/v1/canonical", "GET", tenant_id="default")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert gw.get_stats()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_isolated():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.handle_request("/api/v1/zero_cost", "GET", actor="tester", tenant_id="default")
    assert r["zero_cost"] == True
    assert r["isolated"] == True
    assert gw.get_stats()["zero_cost"] == True


def test_stats_total_routes():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    gw.register_route("/api/v1/stats_route", "GET", tenant_id="default")
    s = gw.get_stats()
    assert "total_routes" in s
    assert s["total_routes"] >= 3
    assert "total_requests" in s


def test_stats_wired_all():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    s = gw.get_stats()
    assert "wired" in s
    assert set(s["wired"]) >= {"tenant_manager", "rate_limiter", "audit"}
    assert all(s["wired"].values())
    assert s["stack"] == "zero-cost"
    assert "Understand->Plan" in s["dod_ref"]


def test_tenant_manager_wired():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    assert gw._get_tenant_manager() is not None


def test_rate_limiter_wired():
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    assert gw._get_rate_limiter() is not None
    assert gw._get_audit() is not None


# ---------- Stage 5.2 - Observability (14) ----------


def test_observability_exists():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    assert obs is not None
    assert get_observability() is obs


def test_record_metric_success():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.record_metric("part1_metric", 7.5, {"k": "v"}, actor="tester", tenant_id="part1_tenant")
    assert r["success"] == True
    assert r["metric"] == "part1_metric"
    assert r["value"] == 7.5


def test_health_check_shape():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.health_check("api", actor="tester")
    assert "healthy" in r
    assert "checks" in r
    assert "tool_registry" in r["checks"]
    assert r["total"] == len(r["checks"])


def test_health_all_ok():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.health_check("api", actor="tester")
    assert r["all_checks"] == True
    assert r["healthy"] == True
    assert all(r["checks"].values())


def test_get_metrics_count():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    obs.record_metric("part1_query_metric", 1.0, actor="tester", tenant_id="default")
    r = obs.get_metrics("part1_query_metric")
    assert r["count"] >= 1
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_health_history():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    obs.health_check("api", actor="tester")
    r = obs.get_health_history()
    assert r["count"] >= 1
    assert r["checks"][-1]["component"] == "api"


def test_apex_wired():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    assert obs._get_apex_core() is not None


def test_audit_wired():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    assert obs._get_audit() is not None


def test_metric_name_echo():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.record_metric("part1_echo_metric", 3.0, actor="tester", tenant_id="default")
    assert r["metric"] == "part1_echo_metric"
    assert r["canonical_spec"] == CANONICAL_SPEC


def test_canonical_spec_observability():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.record_metric("part1_canonical_metric", 1.0, actor="tester", tenant_id="default")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert obs.get_stats()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_observability():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.record_metric("part1_zero_cost", 0.0, actor="tester", tenant_id="default")
    assert r["zero_cost"] == True
    assert obs.get_stats()["zero_cost"] == True


def test_stats_observability():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    s = obs.get_stats()
    assert "total_metrics" in s
    assert "metric_names" in s
    assert "total_health_checks" in s
    assert "wired" in s
    assert s["total_metrics"] >= 1
    assert s["total_logs"] >= 1
    assert "Understand->Plan" in s["dod_ref"]


def test_stats_wired_observability():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    s = obs.get_stats()
    assert all(s["wired"].values())
    assert s["stack"] == "zero-cost"


def test_logs_recorded_observability():
    from fabric.registry.observability import get_observability

    obs = get_observability()
    obs.record_metric("part1_logged_metric", 2.5, actor="tester", tenant_id="default")
    s = obs.get_stats()
    assert s["total_logs"] >= 1
    assert any(l.get("name") == "part1_logged_metric" for l in obs.logs)


# ---------- Stage 5.3 - Release Manager (14) ----------


def test_release_manager_exists():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    assert rm is not None
    assert get_release_manager() is rm


def test_create_release_success():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["success"] == True
    assert r["version"] == "1.0.0-production"


def test_create_release_stages_total():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["total"] >= 10
    assert r["passed"] <= r["total"]


def test_create_release_all_stages_passed():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    failed = [k for k, v in r["stages"].items() if not v]
    assert r["passed"] == r["total"], f"failed stages: {failed}"
    assert r["production_ready"] == True


def test_create_release_production_ready():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["production_ready"] == True
    assert r["isolated"] == True


def test_create_release_stage_keys():
    from fabric.registry.release_manager import get_release_manager, STAGE_KEYS

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    for key in STAGE_KEYS:
        assert key in r["stages"], f"missing stage {key}"
    assert len(STAGE_KEYS) == 13


def test_release_version_field():
    from fabric.registry.release_manager import get_release_manager, VERSION

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["version"] == VERSION
    assert rm.get_stats()["version"] == VERSION


def test_canonical_spec_release():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["canonical_spec"] == CANONICAL_SPEC
    assert rm.get_stats()["canonical_spec"] == CANONICAL_SPEC
    assert rm.get_releases()["canonical_spec"] == CANONICAL_SPEC


def test_zero_cost_dod_release():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    assert r["zero_cost"] == True
    assert "Understand->Plan" in r["dod_ref"]
    assert rm.get_stats()["zero_cost"] == True


def test_release_history():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    rm.create_release(actor="tester", tenant_id="release_test")
    h = rm.get_releases()
    assert h["count"] >= 1
    assert h["releases"][-1]["version"] == "1.0.0-production"
    assert h["releases"][-1]["production_ready"] == True


def test_stats_total_releases():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    before = rm.get_stats()["total_releases"]
    rm.create_release(actor="tester", tenant_id="release_test")
    after = rm.get_stats()["total_releases"]
    assert after == before + 1
    assert rm.get_stats()["production_ready"] >= 1


def test_stats_wired_release():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    s = rm.get_stats()
    assert "wired" in s
    assert set(s["wired"]) >= {"audit", "tool_registry", "api_gateway", "observability", "apex_core"}
    assert all(s["wired"].values())
    assert s["wired_all"] == True
    assert s["stack"] == "zero-cost"
    assert "Understand->Plan" in s["dod_ref"]


def test_audit_wired_release():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    assert rm._get_audit() is not None


def test_release_recorded_latest():
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor="tester", tenant_id="release_test")
    latest = rm.get_releases()["releases"][-1]
    assert latest["passed"] == r["passed"]
    assert latest["total"] == r["total"]
    assert latest["production_ready"] == True
    assert latest["zero_cost"] == True
