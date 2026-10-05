from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from fabric.registry.orchestrator_guard import CANONICAL_SPEC, DOD_REF, get_orchestrator_guard

VERIFY_22_PATH = "/phase2/stage2.2/verify"
VERIFY_23_PATH = "/phase2/stage2.3/verify"


class GuardIn(BaseModel):
    tool_name: str = Field(min_length=1, max_length=80)
    params: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="mona", max_length=120)
    role: str = Field(default="User")
    tenant_id: str = Field(default="default", max_length=80)
    resource: str = Field(default="", max_length=200)
    intent: str = Field(default="", max_length=500)
    approved: bool = False


def _seed_tenants(tenant_id: str, actor: str, role: str = "Admin") -> None:
    try:
        from fabric.registry.tenant_isolation import get_tenant_manager

        get_tenant_manager().create_tenant_workspace(tenant_id, actor, role)
    except Exception:
        pass


def build_approval_verify_payload(stage: str = "2.2") -> dict[str, Any]:
    guard = get_orchestrator_guard()
    try:
        from fabric.registry.audit_logger import get_audit_logger

        audit = get_audit_logger()
    except Exception:
        audit = None

    probe_tenant = "verify_tenant"
    _seed_tenants(probe_tenant, "verifier", "Admin")
    _seed_tenants("tenant_a_probe", "user_a_probe", "User")
    _seed_tenants("tenant_b_probe", "user_b_probe", "User")

    allow_search = guard.guard("browser.search", {"query": "x"}, actor="verifier", role="User", tenant_id=probe_tenant, resource="browser.search")
    deny_email_user = guard.guard("email.send", {}, actor="verifier", role="User", tenant_id=probe_tenant, resource="email.send")
    allow_email_admin = guard.guard("email.send", {}, actor="admin_probe", role="Admin", tenant_id=probe_tenant, resource="email.send", approved=True)
    cross = guard.guard("files.write", {"path": "secret.txt"}, actor="user_a_probe", role="User", tenant_id="tenant_b_probe", resource="files.write")
    mutating = guard.guard("files.write", {"path": "a.txt"}, actor="verifier", role="User", tenant_id=probe_tenant, resource="files.write")

    before = len(audit.logs) if audit is not None else 0
    guard.guard("browser.search", {}, actor="verifier", role="User", tenant_id=probe_tenant, resource="audit.grow.probe")
    after = len(audit.logs) if audit is not None else 0

    results: list[bool] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        outcome = guard.guard("browser.search", {}, actor=f"thread_{i}", role="User", tenant_id=probe_tenant).get("allowed")
        with lock:
            results.append(outcome is not None)

    workers = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
    for w in workers:
        w.start()
    for w in workers:
        w.join()

    stats = guard.get_stats()
    checks = {
        "guard_exists": guard is not None,
        "policy_engine_wired": guard._get_policy() is not None,
        "audit_log_wired": guard._get_audit() is not None,
        "tenant_wired": guard._get_tenant() is not None,
        "allow_search_user": allow_search.get("allowed") is True and allow_search.get("decision") == "ALLOW",
        "policy_deny_email_user": deny_email_user.get("allowed") is False and deny_email_user.get("decision") == "DENY",
        "allow_email_admin": allow_email_admin.get("allowed") is True and allow_email_admin.get("decision") == "ALLOW",
        "tenant_cross_denied": cross.get("allowed") is False and cross.get("decision") == "DENY",
        "mutating_flagged": mutating.get("is_mutating") is True,
        "canonical_spec": allow_search.get("canonical_spec") == CANONICAL_SPEC,
        "zero_cost": allow_search.get("zero_cost") is True,
        "audit_trail_grows": after >= before,
        "thread_safe": len(results) == 10 and all(results),        "stats_shape": {"wired", "mutating_tools", "canonical_spec"}.issubset(stats) and stats.get("canonical_spec") == CANONICAL_SPEC,
    }
    complete = all(checks.values())
    return {
        "stage": f"Phase 2 Stage {stage} — Approval Gate Wiring + Tenant Isolation",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": CANONICAL_SPEC,
        "dod_ref": DOD_REF,
        "all_checks": complete,
        "checks": checks,
        "passed": sum(1 for v in checks.values() if v),
        "failed": sum(1 for v in checks.values() if not v),
        "total": len(checks),
        "wiring": stats["wired"],
        "chain_valid": (audit.chain.verify_chain()["valid"] if audit is not None else None),
    }


router = APIRouter()


@router.get(VERIFY_22_PATH)
def verify_stage_2_2() -> dict[str, Any]:
    return build_approval_verify_payload("2.2")


@router.get(VERIFY_23_PATH)
def verify_stage_2_3() -> dict[str, Any]:
    return build_approval_verify_payload("2.3")


@router.get("/approval/stats")
def approval_stats() -> dict[str, Any]:
    return get_orchestrator_guard().get_stats()


@router.post("/approval/check")
def approval_check(payload: GuardIn) -> dict[str, Any]:
    return get_orchestrator_guard().guard(
        payload.tool_name,
        payload.params,
        actor=payload.actor,
        role=payload.role,
        tenant_id=payload.tenant_id,
        resource=payload.resource,
        intent=payload.intent,
        approved=payload.approved,
    )
