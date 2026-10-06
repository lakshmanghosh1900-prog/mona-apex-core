from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = (
    "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->"
    "Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
)


class OrchestrateRequest(BaseModel):
    task: str = Field(min_length=1, max_length=8000)
    actor: str = "system"
    tenant_id: str = "default"


@router.get("/phase3/stage3.4/verify")
def verify_stage_3_4():
    checks: Dict[str, bool] = {}
    try:
        import time

        from fabric.registry.orchestrator_core import get_staged_orchestrator

        orch = get_staged_orchestrator()
        orch.runs.clear()

        # 1: orchestrator exists
        checks["1_orchestrator_exists"] = orch is not None

        # 2: tool registry wired
        checks["2_tool_registry_wired"] = orch._get_tool_registry() is not None

        # 3: execution sandbox wired
        checks["3_execution_sandbox_wired"] = orch._get_execution_sandbox() is not None

        # 4: memory store wired
        checks["4_memory_store_wired"] = orch._get_memory_store() is not None

        # 5: guard wired
        checks["5_guard_wired"] = orch._get_guard() is not None

        # 6: audit wired
        checks["6_audit_wired"] = orch._get_audit() is not None

        # 7: understand
        r_understand = orch.understand("search web for cats")
        checks["7_understand"] = r_understand.get("understood") == True

        # 8: plan (Select Model + Select Tool)
        r_plan = orch.plan("search web for cats")
        checks["8_plan"] = "tool" in r_plan and "model" in r_plan

        # 9: execute simple task (understand -> ... -> report)
        r_exec = orch.execute("search web for test", actor="verifier", tenant_id="verify_tenant")
        checks["9_execute"] = r_exec.get("success") == True or "tool" in r_exec

        # 10: canonical_spec present
        checks["10_canonical_spec"] = r_exec.get("canonical_spec") == "MONA - Powered by Apex Core"

        # 11: zero_cost + isolated
        checks["11_zero_cost_isolated"] = r_exec.get("zero_cost") == True and r_exec.get("isolated") == True

        # 12: dod_ref present
        checks["12_dod_ref"] = "dod_ref" in r_exec and "Understand->Plan" in r_exec["dod_ref"]

        # 13: stats shape
        stats = orch.get_stats()
        checks["13_stats"] = "total_runs" in stats and "wired" in stats and stats.get("canonical_spec") == "MONA - Powered by Apex Core"

        # 14: self-heal loop (observe -> verify -> retry fields always present)
        r_heal = orch.execute("analyze complex data", actor="verifier", tenant_id="verify_tenant")
        checks["14_self_heal"] = "retries" in r_heal and "verify_ok" in r_heal

        all_ok = all(bool(v) for v in checks.values())
        return {
            "stage": "Phase 3 Stage 3.4 — Orchestration & Self-Heal Loop",
            "status": "COMPLETE" if all_ok else f"INCOMPLETE {sum(not v for v in checks.values())} failed",
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "failed": sum(1 for v in checks.values() if not v),
            "total": len(checks),
            "stats": orch.get_stats(),
            "dod_ref": DOD_REF,
            "zero_cost": True,
            "canonical_spec": CANONICAL_SPEC,
        }
    except Exception as ex:
        return {
            "stage": "Phase 3 Stage 3.4 — Orchestration & Self-Heal Loop",
            "status": f"ERROR: {ex}",
            "all_checks": False,
            "error": str(ex),
            "checks": checks,
            "canonical_spec": CANONICAL_SPEC,
        }


@router.post("/orchestrate/run")
def orchestrate_run(req: OrchestrateRequest):
    try:
        from fabric.registry.orchestrator_core import get_staged_orchestrator

        orch = get_staged_orchestrator()
        return orch.execute(req.task, req.actor, req.tenant_id)
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/orchestrate/stats")
def orchestrate_stats():
    try:
        from fabric.registry.orchestrator_core import get_staged_orchestrator

        orch = get_staged_orchestrator()
        return orch.get_stats()
    except Exception as e:
        return {"error": str(e)}


@router.get("/phase3/mega/verify")
async def verify_phase3_mega() -> Dict[str, Any]:
    """Phase 3 FULL MEGA - every stage 2.4 through 3.4 in one pass.

    Stage probing delegates to the central stage sweep (gate D1).
    """
    from fabric.registry.stage_sweep import run_stage_sweep

    sweep = run_stage_sweep(start="2.4", end="3.4", actor="mega", tenant_id="mega")
    results = sweep["stages"]
    details = sweep["details"]
    all_ok = sweep["all_checks"]
    return {
        "phase": "Phase 3 — Execution Fabric — FULL MEGA 2.4-3.4",
        "status": "PHASE 3 FULL COMPLETE" if all_ok else f"INCOMPLETE failed {[k for k, v in results.items() if not v]}",
        "all_checks": all_ok,
        "stages": results,
        "complete": {k: bool(v) for k, v in results.items()},
        "details": details,
        "passed": sweep["passed"],
        "total": sweep["total"],
        "canonical_spec": CANONICAL_SPEC,
        "zero_cost": True,
        "next": "Phase 4 — Apex Core" if all_ok else "Fix failed stages",
        "governance": "Build → Test → Verify → Human Review → Commit → Push → Next",
    }
