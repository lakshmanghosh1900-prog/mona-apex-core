from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class ApexRunRequest(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    actor: str = "system"
    tenant_id: str = "default"


@router.get("/phase4/stage4.1/verify")
def verify_stage_4_1():
    checks: Dict[str, bool] = {}
    try:
        from fabric.registry.evidence_chain import get_evidence_chain
        from fabric.registry.report_generator import get_report_generator

        ec = get_evidence_chain()
        rg = get_report_generator()
        ec.chains.clear()
        rg.reports.clear()

        # 1: evidence_chain exists
        checks["1_evidence_chain_exists"] = ec is not None

        # 2: report_generator exists
        checks["2_report_generator_exists"] = rg is not None

        # 3: append evidence
        r_append = ec.append("test_task_41", {"data": "test evidence"}, actor="verifier", tenant_id="verify_tenant")
        checks["3_append_evidence"] = r_append.get("success") == True and "hash" in r_append

        # 4: get chain
        r_get = ec.get_chain("test_task_41", tenant_id="verify_tenant")
        checks["4_get_chain"] = r_get.get("found") == True and r_get.get("length", 0) >= 1

        # 5: verify chain valid
        r_verify = ec.verify_chain("test_task_41")
        checks["5_verify_chain_valid"] = r_verify.get("valid") == True

        # 6: append second block links to first
        r_append2 = ec.append("test_task_41", {"data": "second evidence"}, actor="verifier", tenant_id="verify_tenant")
        checks["6_append_second"] = r_append2.get("success") == True and r_append2.get("prev_hash") == r_append.get("hash")

        # 7: chain length 2
        r_get2 = ec.get_chain("test_task_41", tenant_id="verify_tenant")
        checks["7_chain_length_2"] = r_get2.get("length", 0) == 2

        # 8: generate report
        r_report = rg.generate("test_task_41", actor="verifier", tenant_id="verify_tenant")
        checks["8_generate_report"] = r_report.get("success") == True

        # 9: get report
        r_get_report = rg.get_report("test_task_41", tenant_id="verify_tenant")
        checks["9_get_report"] = r_get_report.get("found") == True

        # 10: canonical_spec
        checks["10_canonical_spec"] = r_append.get("canonical_spec") == CANONICAL_SPEC and r_report.get("canonical_spec") == CANONICAL_SPEC

        # 11: zero_cost
        checks["11_zero_cost"] = r_append.get("zero_cost") == True and r_report.get("zero_cost") == True

        # 12: stats shape
        ec_stats = ec.get_stats()
        rg_stats = rg.get_stats()
        checks["12_stats"] = "total_chains" in ec_stats and "total_reports" in rg_stats and ec_stats.get("canonical_spec") == CANONICAL_SPEC

        # 13: tenant isolation - cross-tenant read denied
        r_cross = ec.get_chain("test_task_41", tenant_id="other_tenant")
        checks["13_tenant_isolation"] = r_cross.get("found") == False

        # 14: audit integration - appends land in the audit trail
        try:
            from fabric.registry.audit_logger import get_audit_logger

            trail = get_audit_logger().get_trail(tool_name="evidence_chain.append", limit=5)
            checks["14_audit_integration"] = isinstance(trail, dict) and trail.get("count", 0) >= 1
        except Exception:
            checks["14_audit_integration"] = ec._get_audit() is not None

        all_ok = all(bool(v) for v in checks.values())
        return {
            "stage": "Phase 4 Stage 4.1 — Evidence Chain & Report Generator",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 4 Stage 4.1 — Evidence Chain & Report Generator",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase4/stage4.2/verify")
def verify_stage_4_2():
    checks: Dict[str, bool] = {}
    try:
        from fabric.registry.governance_engine import get_governance_engine

        gov = get_governance_engine()
        gov.compliance_history.clear()

        # 1: governance_engine exists
        checks["1_governance_exists"] = gov is not None

        # 2: tenant_manager wired
        checks["2_tenant_manager_wired"] = gov._get_tenant_manager() is not None

        # 3: guard wired
        checks["3_guard_wired"] = gov._get_guard() is not None

        # 4: audit wired
        checks["4_audit_wired"] = gov._get_audit() is not None

        # 5: check_tenant valid
        r_tenant = gov.check_tenant("verify_tenant")
        checks["5_check_tenant"] = r_tenant.get("check") == "tenant" and r_tenant.get("passed") == True

        # 6: check_permission
        r_perm = gov.check_permission("browser.search", "verifier", "verify_tenant")
        checks["6_check_permission"] = r_perm.get("check") == "permission" and "passed" in r_perm

        # 7: check_audit
        r_audit = gov.check_audit()
        checks["7_check_audit"] = r_audit.get("check") == "audit" and "passed" in r_audit

        # 8: check_secrets
        r_secrets = gov.check_secrets()
        checks["8_check_secrets"] = r_secrets.get("check") == "secrets" and "passed" in r_secrets

        # 9: check_rate_limit
        r_rate = gov.check_rate_limit("verify_tenant", "verifier")
        checks["9_check_rate_limit"] = r_rate.get("check") == "rate_limit" and "passed" in r_rate

        # 10: full_compliance_check
        r_full = gov.full_compliance_check("search web for test", "verifier", "verify_tenant", "browser.search")
        checks["10_full_compliance"] = "all_passed" in r_full and "checks" in r_full

        # 11: canonical_spec
        checks["11_canonical_spec"] = r_full.get("canonical_spec") == CANONICAL_SPEC

        # 12: zero_cost
        checks["12_zero_cost"] = r_full.get("zero_cost") == True

        # 13: stats shape
        stats = gov.get_stats()
        checks["13_stats"] = "total_checks" in stats and "wired" in stats and stats.get("canonical_spec") == CANONICAL_SPEC

        # 14: history recorded
        checks["14_history_recorded"] = len(gov.compliance_history) >= 1

        all_ok = all(bool(v) for v in checks.values())
        return {
            "stage": "Phase 4 Stage 4.2 — Governance Engine",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 4 Stage 4.2 — Governance Engine",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.get("/phase4/stage4.3/verify")
def verify_stage_4_3():
    checks: Dict[str, bool] = {}
    try:
        from fabric.registry.apex_core import get_apex_core

        apex = get_apex_core()
        apex.runs.clear()

        # 1: apex_core exists
        checks["1_apex_core_exists"] = apex is not None

        # 2: tool registry wired
        checks["2_tool_registry_wired"] = apex._get_tool_registry() is not None

        # 3: execution sandbox wired
        checks["3_execution_sandbox_wired"] = apex._get_execution_sandbox() is not None

        # 4: memory store wired
        checks["4_memory_store_wired"] = apex._get_memory_store() is not None

        # 5: evidence chain wired
        checks["5_evidence_chain_wired"] = apex._get_evidence_chain() is not None

        # 6: report generator wired
        checks["6_report_generator_wired"] = apex._get_report_generator() is not None

        # 7: governance engine wired
        checks["7_governance_wired"] = apex._get_governance_engine() is not None

        # 8: orchestrator wired
        checks["8_orchestrator_wired"] = apex._get_orchestrator() is not None

        # 9: run end-to-end task
        r_run = apex.run("search web for apex test", actor="verifier", tenant_id="verify_tenant")
        checks["9_run_task"] = r_run.get("task_id") is not None and "tool" in r_run

        # 10: canonical_spec + dod_ref
        checks["10_canonical_dod"] = r_run.get("canonical_spec") == CANONICAL_SPEC and "dod_ref" in r_run and "Understand->Plan" in r_run["dod_ref"]

        # 11: zero_cost + isolated + apex_core
        checks["11_zero_cost_isolated"] = r_run.get("zero_cost") == True and r_run.get("isolated") == True and r_run.get("apex_core") == True

        # 12: evidence_chain + report generated
        checks["12_evidence_report"] = r_run.get("evidence_chain") is not None and r_run.get("report") is not None

        # 13: stats shape - all 9 wired
        stats = apex.get_stats()
        checks["13_stats"] = "total_runs" in stats and "wired" in stats and stats.get("canonical_spec") == CANONICAL_SPEC and all(stats["wired"].values())

        # 14: governance check inside run
        checks["14_governance_inside"] = r_run.get("governance") is not None

        all_ok = all(bool(v) for v in checks.values())
        return {
            "stage": "Phase 4 Stage 4.3 — Apex Core End-to-End",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
    except Exception as ex:
        return {
            "stage": "Phase 4 Stage 4.3 — Apex Core End-to-End",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.post("/apex/run")
def apex_run(req: ApexRunRequest):
    try:
        from fabric.registry.apex_core import get_apex_core

        return get_apex_core().run(req.task, req.actor, req.tenant_id)
    except Exception as e:
        return {"success": False, "error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/apex/stats")
def apex_stats():
    try:
        from fabric.registry.apex_core import get_apex_core

        return get_apex_core().get_stats()
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/apex/evidence/{task_id}")
def apex_evidence(task_id: str, tenant_id: str = Query("default")):
    try:
        from fabric.registry.evidence_chain import get_evidence_chain

        ec = get_evidence_chain()
        return {"chain": ec.get_chain(task_id, tenant_id=tenant_id), "verify": ec.verify_chain(task_id)}
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/apex/report/{task_id}")
def apex_report(task_id: str, tenant_id: str = Query("default")):
    try:
        from fabric.registry.report_generator import get_report_generator

        return get_report_generator().get_report(task_id, tenant_id=tenant_id)
    except Exception as e:
        return {"error": str(e), "canonical_spec": CANONICAL_SPEC}


@router.get("/phase4/mega/verify")
async def verify_phase4_mega() -> Dict[str, Any]:
    """Phase 4 FULL MEGA - every stage 2.4 through 4.3 in one pass.

    Stage probing delegates to the central stage sweep (gate D1).
    """
    from fabric.registry.stage_sweep import run_stage_sweep

    sweep = run_stage_sweep(start="2.4", end="4.3", actor="mega", tenant_id="mega")
    results = sweep["stages"]
    details = sweep["details"]
    all_ok = sweep["all_checks"]
    return {
        "phase": "Phase 4 — Apex Core — FULL MEGA 2.4-4.3",
        "status": "PHASE 4 FULL COMPLETE" if all_ok else f"INCOMPLETE failed {[k for k, v in results.items() if not v]}",
        "all_checks": all_ok,
        "stages": results,
        "details": details,
        "passed": sweep["passed"],
        "total": sweep["total"],
        "canonical_spec": CANONICAL_SPEC,
        "zero_cost": True,
        "next": "Production Ready" if all_ok else "Fix failed stages",
        "governance": "Build → Test → Verify → Human Review → Commit → Push → Next",
    }
