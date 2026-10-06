from fabric.registry.state_root import state_dir
import time
import threading
import pathlib
import json
from typing import Dict, List, Optional

MEMORY_ROOT = state_dir("memory")
ENT_ROOT = MEMORY_ROOT / "enterprise_audit"
ENT_ROOT.mkdir(parents=True, exist_ok=True)

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class EnterpriseAudit:
    """Stage 6.3 - enterprise audit dashboard: event log plus a 17-stage
    compliance report covering 2.4 -> 6.3. Zero-cost, stdlib only."""

    def __init__(self):
        self.audits: List[Dict] = []
        self.compliance_reports: List[Dict] = []
        self._lock = threading.RLock()
        self._audit_logger = None
        self._governance = None
        self._release_manager = None

    def _get_audit_logger(self):
        if self._audit_logger is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit_logger = get_audit_logger()
            except Exception:
                self._audit_logger = None
        return self._audit_logger

    def _get_governance(self):
        if self._governance is None:
            try:
                from fabric.registry.governance_engine import get_governance_engine
                self._governance = get_governance_engine()
            except Exception:
                self._governance = None
        return self._governance

    def _get_release_manager(self):
        if self._release_manager is None:
            try:
                from fabric.registry.release_manager import get_release_manager
                self._release_manager = get_release_manager()
            except Exception:
                self._release_manager = None
        return self._release_manager

    def record_enterprise_event(self, event: str, actor: str, tenant_id: str, detail: Dict = None, severity: str = "INFO") -> Dict:
        if not event:
            return {"success": False, "reason": "Invalid event", "canonical_spec": CANONICAL_SPEC}
        with self._lock:
            entry = {
                "event": event,
                "actor": actor,
                "tenant_id": tenant_id,
                "detail": detail or {},
                "severity": severity,
                "timestamp": time.time(),
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
            }
            self.audits.append(entry)
        audit = self._get_audit_logger()
        if audit:
            try:
                if hasattr(audit, "record"):
                    audit.record(event, actor=actor, role="User", decision="ALLOW", detail={"tenant_id": tenant_id, **(detail or {})})
                else:
                    audit.log(
                        event,
                        actor,
                        "User",
                        {"tenant_id": tenant_id, "severity": severity, **(detail or {})},
                        {"success": True, "event": event, "severity": severity},
                        approved=True,
                        policy_decision="ALLOW",
                    )
            except Exception:
                pass
        return {"success": True, "event": event, "severity": severity, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def generate_compliance_report(self, tenant_id: str = "default", actor: str = "system") -> Dict:
        """Enterprise compliance report (D1): delegates to the central stage
        sweep in wiring mode for stages 2.4 -> 6.3 instead of re-implementing
        per-stage try/except blocks."""
        from fabric.registry.stage_sweep import run_stage_sweep

        sweep = run_stage_sweep(
            start="2.4",
            end="6.3",
            actor=actor,
            tenant_id=tenant_id,
            mode="wiring",
        )
        stage_results: Dict[str, bool] = dict(sweep["stages"])

        all_ok = all(stage_results.values())
        report = {
            "tenant_id": tenant_id,
            "actor": actor,
            "stages": stage_results,
            "all_ok": all_ok,
            "passed": sum(1 for v in stage_results.values() if v),
            "total": len(stage_results),
            "compliance": "COMPLIANT" if all_ok else "NON_COMPLIANT",
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
        }
        with self._lock:
            self.compliance_reports.append(report)
        return {
            "success": all_ok,
            "report": report,
            "compliance": report["compliance"],
            "passed": report["passed"],
            "total": report["total"],
            "stages": stage_results,
            "all_checks": all_ok,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
            "production_ready": all_ok,
        }

    def get_reports(self, limit: int = 20) -> Dict:
        with self._lock:
            return {
                "count": len(self.compliance_reports),
                "reports": self.compliance_reports[-limit:],
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
            }

    def get_stats(self) -> Dict:
        with self._lock:
            wired = {
                "audit_logger": self._get_audit_logger() is not None,
                "governance": self._get_governance() is not None,
                "release_manager": self._get_release_manager() is not None,
            }
            return {
                "total_audits": len(self.audits),
                "total_reports": len(self.compliance_reports),
                "compliant": sum(1 for r in self.compliance_reports if r.get("all_ok")),
                "non_compliant": sum(1 for r in self.compliance_reports if not r.get("all_ok")),
                "wired": wired,
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "dod_ref": DOD_REF,
            }


_singleton = None
_lock = threading.Lock()


def get_enterprise_audit() -> EnterpriseAudit:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = EnterpriseAudit()
    return _singleton
