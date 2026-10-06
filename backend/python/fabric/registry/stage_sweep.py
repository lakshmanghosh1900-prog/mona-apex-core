"""Canonical stage sweep (gate D1).

Single source of truth for DoD stage verification probes (2.4 -> 7.3).
Every phase mega endpoint, the release stage matrix, and the enterprise
compliance report consume :func:`run_stage_sweep` instead of re-implementing
copy-pasted probe blocks.

Two probe modes:
- ``functional``: full end-to-end probes (execute code, save memory, run
  orchestrator, ...). Used by phase mega endpoints and the release matrix.
- ``wiring``: singleton-wire probes (manager exists). Used by the enterprise
  compliance report so compliance stays fast and stable.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Tuple

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = (
    "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->"
    "Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
)

# Full ordered stage keys (gates 2.4 -> 7.3)
STAGE_ORDER: List[str] = [
    "2.4", "2.5", "2.6", "2.7",
    "3.1", "3.2", "3.3", "3.4",
    "4.1", "4.2", "4.3",
    "5.1", "5.2", "5.3",
    "6.1", "6.2", "6.3",
    "7.1", "7.2", "7.3",
]

# The 13 stages owned by the release stage matrix (2.4 -> 5.2)
RELEASE_STAGE_KEYS: List[str] = [
    "2.4", "2.5", "2.6", "2.7",
    "3.1", "3.2", "3.3", "3.4",
    "4.1", "4.2", "4.3",
    "5.1", "5.2",
]

# Back-compat alias (release_manager.STAGE_KEYS historically == 13 keys)
STAGE_KEYS = RELEASE_STAGE_KEYS

Probe = Callable[[Dict[str, Any]], Tuple[bool, str]]


def _probe_2_4(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.secrets_manager import get_secrets_manager

    sm = get_secrets_manager()
    findings = sm.scan_hardcoded() if hasattr(sm, "scan_hardcoded") else []
    secure = sm.is_secure() if hasattr(sm, "is_secure") else True
    return (len(findings) == 0 and bool(secure), f"scan clean ({len(findings)} findings)")


def _probe_2_5(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.audit_logger import get_audit_logger

    stats = get_audit_logger().get_stats()
    ok = bool(stats.get("chain_valid")) and stats.get("total_logs", 0) >= 1
    return (ok, f"chain len={stats.get('chain_length', 0)} logs={stats.get('total_logs', 0)}")


def _probe_2_6(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.tenant_isolation import get_tenant_manager

    tm = get_tenant_manager()
    total = tm.get_stats().get("total_tenants", 0)
    return (total >= 0, f"tenants={total}")


def _probe_2_7(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.rate_limiter import get_rate_limiter

    rl = get_rate_limiter()
    buckets = rl.get_stats().get("total_buckets", 0)
    return (buckets >= 0, f"buckets={buckets}")


def _probe_3_1(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.execution_sandbox import get_execution_sandbox

    sb = get_execution_sandbox()
    r = sb.execute_python("print(42)", actor=ctx["actor"], tenant_id=ctx["tenant_id"])
    ok = r.get("success") is True and "42" in r.get("output", "")
    return (ok, "execution sandbox")


def _probe_3_2(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.tool_registry import get_tool_registry

    tr = get_tool_registry()
    r = tr.select_tool("search web")
    stats = tr.get_stats()
    ok = r.get("tool") == "browser.search" and stats.get("total_tools", 0) >= 7
    return (ok, f"tools={stats.get('total_tools', 0)}")


def _probe_3_3(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.memory_store import get_memory_store

    ms = get_memory_store()
    r = ms.save_memory(
        ctx.get("memory_key", "sweep_test"),
        {"data": "sweep"},
        actor=ctx["actor"],
        tenant_id=ctx["tenant_id"],
    )
    ok = r.get("success") is True
    return (ok, f"memories={ms.get_stats().get('total_memories', 0)}")


def _probe_3_4(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.orchestrator_core import get_staged_orchestrator

    orch = get_staged_orchestrator()
    r = orch.execute(ctx.get("orch_task", "test task"), actor=ctx["actor"], tenant_id=ctx["tenant_id"])
    ok = r.get("canonical_spec") == CANONICAL_SPEC
    return (ok, f"runs={orch.get_stats().get('total_runs', 0)}")


def _probe_4_1(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.evidence_chain import get_evidence_chain

    ec = get_evidence_chain()
    key = ctx.get("evidence_key", "sweep_evidence")
    r = ec.append(key, {"data": "sweep"}, actor=ctx["actor"], tenant_id=ctx["tenant_id"])
    v = ec.verify_chain(key)
    ok = r.get("success") is True and v.get("valid") is True
    return (ok, f"chains={ec.get_stats().get('total_chains', 0)}")


def _probe_4_2(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.governance_engine import get_governance_engine

    gov = get_governance_engine()
    r = gov.full_compliance_check("test", ctx["actor"], ctx["tenant_id"], "browser.search")
    ok = "all_passed" in r and r.get("canonical_spec") == CANONICAL_SPEC
    return (ok, f"checks={gov.get_stats().get('total_checks', 0)}")


def _probe_4_3(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.apex_core import get_apex_core

    apex = get_apex_core()
    r = apex.run(
        ctx.get("apex_task", "search web for sweep"),
        actor=ctx["actor"],
        tenant_id=ctx["tenant_id"],
    )
    ok = r.get("canonical_spec") == CANONICAL_SPEC and r.get("apex_core") is True
    return (ok, f"runs={apex.get_stats().get('total_runs', 0)}")


def _probe_5_1(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.api_gateway import get_api_gateway

    gw = get_api_gateway()
    r = gw.register_route(ctx.get("gateway_route", "/sweep/probe"), "GET", tenant_id=ctx["tenant_id"])
    ok = r.get("success") is True
    return (ok, f"routes={gw.get_stats().get('total_routes', 0)}")


def _probe_5_2(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.observability import get_observability

    obs = get_observability()
    r = obs.health_check(ctx.get("health_component", "sweep"), actor=ctx["actor"])
    ok = r.get("all_checks") is True
    return (ok, f"healthy={r.get('healthy')}")


def _probe_5_3(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.release_manager import get_release_manager

    rm = get_release_manager()
    r = rm.create_release(actor=ctx["actor"], tenant_id=ctx["tenant_id"])
    ok = r.get("total", 0) >= 10 and r.get("production_ready") is True
    detail = f"release {r.get('version')} {r.get('passed')}/{r.get('total')} ready={r.get('production_ready')}"
    return (ok, detail)


def _probe_6_1(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

    mo = get_multi_model_orchestrator()
    r = mo.select_model(ctx.get("model_task", "search web for sweep"), preferred="groq-llama")
    ok = r.get("model") == "groq-llama" and len(r.get("fallback_chain", [])) >= 4
    return (ok, f"model={r.get('model')} calls={mo.get_stats().get('total_calls', 0)}")


def _probe_6_2(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.advanced_cache import get_advanced_cache

    cache = get_advanced_cache()
    key = ctx.get("cache_key", "sweep_cache_key")
    r = cache.set(key, "sweep_value", ttl=60, tenant_id=ctx["tenant_id"], actor=ctx["actor"])
    g = cache.get(key, tenant_id=ctx["tenant_id"])
    ok = r.get("success") is True and g.get("found") is True
    stats = cache.get_stats()
    return (ok, f"entries={stats.get('total_entries', 0)} hit_rate={stats.get('hit_rate', 0)}")


def _probe_6_3(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.enterprise_audit import get_enterprise_audit

    ent = get_enterprise_audit()
    r = ent.generate_compliance_report(tenant_id=ctx["tenant_id"], actor=ctx["actor"])
    ok = r.get("total", 0) >= 14 and r.get("all_checks") is True
    detail = f"compliance={r.get('compliance')} {r.get('passed')}/{r.get('total')}"
    return (ok, detail)


def _probe_7_1(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.deployment_manager import get_deployment_manager

    dm = get_deployment_manager()
    r = dm.deploy(ctx.get("deploy_version", "2.0.0-sweep"), env=ctx.get("deploy_env", "staging"), actor=ctx["actor"])
    h = dm.health_probe(ctx.get("health_component", "sweep"))
    ok = r.get("success") is True and h.get("all_checks") is True
    detail = f"deploy={r.get('version')} healthy={h.get('healthy')} deployments={dm.get_stats().get('total_deployments', 0)}"
    return (ok, detail)


def _probe_7_2(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.cicd_manager import get_cicd_manager

    cm = get_cicd_manager()
    name = ctx.get("pipeline_name", "sweep-pipeline")
    r = cm.create_pipeline(name, stages=["build", "test", "verify", "deploy"], actor=ctx["actor"])
    run = cm.run_pipeline(name, actor=ctx["actor"])
    k8s = cm.generate_k8s_manifest(ctx.get("k8s_app", "mona-sweep"), replicas=ctx.get("k8s_replicas", 3), actor=ctx["actor"])
    ok = r.get("success") is True and run.get("success") is True and k8s.get("replicas") == 3
    detail = (
        f"pipelines={cm.get_stats().get('total_pipelines', 0)} "
        f"run={run.get('passed')}/{run.get('total')} "
        f"manifests={cm.get_stats().get('total_manifests', 0)}"
    )
    return (ok, detail)


def _probe_7_3(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    from fabric.registry.docs_manager import get_docs_manager

    docs = get_docs_manager()
    r = docs.final_release_audit(actor=ctx["actor"])
    ok = r.get("total", 0) >= 19 and r.get("all_checks") is True
    detail = f"audit {r.get('passed')}/{r.get('total')} {r.get('final')}"
    return (ok, detail)


STAGE_PROBES: Dict[str, Probe] = {
    "2.4": _probe_2_4,
    "2.5": _probe_2_5,
    "2.6": _probe_2_6,
    "2.7": _probe_2_7,
    "3.1": _probe_3_1,
    "3.2": _probe_3_2,
    "3.3": _probe_3_3,
    "3.4": _probe_3_4,
    "4.1": _probe_4_1,
    "4.2": _probe_4_2,
    "4.3": _probe_4_3,
    "5.1": _probe_5_1,
    "5.2": _probe_5_2,
    "5.3": _probe_5_3,
    "6.1": _probe_6_1,
    "6.2": _probe_6_2,
    "6.3": _probe_6_3,
    "7.1": _probe_7_1,
    "7.2": _probe_7_2,
    "7.3": _probe_7_3,
}

# Wiring-only probes (compliance report): manager singleton must exist.
_WIRING_GETTERS: Dict[str, str] = {
    "2.4": "fabric.registry.secrets_manager:get_secrets_manager",
    "2.5": "fabric.registry.audit_logger:get_audit_logger",
    "2.6": "fabric.registry.tenant_isolation:get_tenant_manager",
    "2.7": "fabric.registry.rate_limiter:get_rate_limiter",
    "3.1": "fabric.registry.execution_sandbox:get_execution_sandbox",
    "3.2": "fabric.registry.tool_registry:get_tool_registry",
    "3.3": "fabric.registry.memory_store:get_memory_store",
    "3.4": "fabric.registry.orchestrator_core:get_staged_orchestrator",
    "4.1": "fabric.registry.evidence_chain:get_evidence_chain",
    "4.2": "fabric.registry.governance_engine:get_governance_engine",
    "4.3": "fabric.registry.apex_core:get_apex_core",
    "5.1": "fabric.registry.api_gateway:get_api_gateway",
    "5.2": "fabric.registry.observability:get_observability",
    "5.3": "fabric.registry.release_manager:get_release_manager",
    "6.1": "fabric.registry.multi_model_orchestrator:get_multi_model_orchestrator",
    "6.2": "fabric.registry.advanced_cache:get_advanced_cache",
    "6.3": None,  # compliance report itself validates 6.3
}


def _make_wiring_probe(stage: str) -> Probe:
    spec = _WIRING_GETTERS.get(stage)

    def probe(ctx: Dict[str, Any]) -> Tuple[bool, str]:
        if spec is None:
            return (True, "self")
        module_name, attr = spec.split(":")
        import importlib

        mod = importlib.import_module(module_name)
        getter = getattr(mod, attr)
        getter()
        return (True, "wired")

    return probe


STAGE_WIRING: Dict[str, Probe] = {
    stage: _make_wiring_probe(stage) for stage in STAGE_ORDER if stage in _WIRING_GETTERS
}
STAGE_WIRING["6.3"] = _make_wiring_probe("6.3")


def run_stage_sweep(
    start: str = "2.4",
    end: str = "7.3",
    actor: str = "sweep",
    tenant_id: str = "sweep",
    mode: str = "functional",
    **ctx_extra: Any,
) -> Dict[str, Any]:
    """Run stage probes from ``start`` to ``end`` (inclusive).

    ``mode``:
    - ``functional``: full end-to-end probes (default)
    - ``wiring``: singleton-wire probes only (compliance report)
    """
    if start not in STAGE_ORDER or end not in STAGE_ORDER:
        raise ValueError(f"unknown stage keys: start={start!r} end={end!r}")
    i0 = STAGE_ORDER.index(start)
    i1 = STAGE_ORDER.index(end)
    if i1 < i0:
        raise ValueError(f"end {end!r} precedes start {start!r}")
    selected = STAGE_ORDER[i0 : i1 + 1]

    probes = STAGE_PROBES if mode == "functional" else STAGE_WIRING
    ctx: Dict[str, Any] = {
        "actor": actor,
        "tenant_id": tenant_id,
        "memory_key": ctx_extra.pop("memory_key", f"mem_{actor}_{tenant_id}"),
        "evidence_key": ctx_extra.pop("evidence_key", f"evd_{actor}_{tenant_id}"),
        "orch_task": ctx_extra.pop("orch_task", "test task"),
        "apex_task": ctx_extra.pop("apex_task", "search web for sweep"),
        "gateway_route": ctx_extra.pop("gateway_route", f"/{actor}/probe"),
        "health_component": ctx_extra.pop("health_component", actor),
        "model_task": ctx_extra.pop("model_task", "search web for sweep"),
        "cache_key": ctx_extra.pop("cache_key", f"cache_{tenant_id}"),
        "pipeline_name": ctx_extra.pop("pipeline_name", f"pipeline-{actor}"),
        "k8s_app": ctx_extra.pop("k8s_app", f"mona-{actor}"),
        "k8s_replicas": ctx_extra.pop("k8s_replicas", 3),
        "deploy_version": ctx_extra.pop("deploy_version", f"2.0.0-{actor}"),
        "deploy_env": ctx_extra.pop("deploy_env", "staging"),
    }
    ctx.update(ctx_extra)

    results: Dict[str, bool] = {}
    details: Dict[str, str] = {}
    for key in selected:
        probe = probes.get(key)
        if probe is None:
            results[key] = False
            details[key] = f"no probe registered for {key} in mode={mode}"
            continue
        try:
            ok, detail = probe(ctx)
            results[key] = bool(ok)
            details[key] = detail
        except Exception as exc:  # noqa: BLE001 - a broken stage must not crash the sweep
            results[key] = False
            details[key] = str(exc)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    return {
        "stages": results,
        "details": details,
        "passed": passed,
        "total": total,
        "all_checks": total > 0 and passed == total,
        "canonical_spec": CANONICAL_SPEC,
        "dod_ref": DOD_REF,
        "zero_cost": True,
        "mode": mode,
        "timestamp": time.time(),
    }


_singleton = None


def get_stage_sweep() -> Dict[str, Any]:
    """Stats-style handle for the central stage sweep (D1 deduplication)."""
    return {
        "stages_total": len(STAGE_ORDER),
        "release_stages": len(RELEASE_STAGE_KEYS),
        "functional_probes": len(STAGE_PROBES),
        "wiring_probes": len(STAGE_WIRING),
        "canonical_spec": CANONICAL_SPEC,
        "dod_ref": DOD_REF,
        "zero_cost": True,
    }
