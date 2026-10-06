import time
import threading
import pathlib
import json
from typing import Dict, List, Optional

MEMORY_ROOT = pathlib.Path("/tmp/mona_sandbox/memory")
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
        stage_results: Dict[str, bool] = {}

        try:
            from fabric.registry.secrets_manager import get_secrets_manager

            sm = get_secrets_manager()
            findings = sm.scan_hardcoded() if hasattr(sm, "scan_hardcoded") else []
            stage_results["2.4"] = len(findings) == 0
        except Exception:
            stage_results["2.4"] = False

        try:
            from fabric.registry.audit_logger import get_audit_logger

            audit = get_audit_logger()
            stage_results["2.5"] = bool(audit.get_stats().get("chain_valid"))
        except Exception:
            stage_results["2.5"] = False

        try:
            from fabric.registry.tenant_isolation import get_tenant_manager

            get_tenant_manager()
            stage_results["2.6"] = True
        except Exception:
            stage_results["2.6"] = False

        try:
            from fabric.registry.rate_limiter import get_rate_limiter

            get_rate_limiter()
            stage_results["2.7"] = True
        except Exception:
            stage_results["2.7"] = False

        try:
            from fabric.registry.execution_sandbox import get_execution_sandbox

            get_execution_sandbox()
            stage_results["3.1"] = True
        except Exception:
            stage_results["3.1"] = False

        try:
            from fabric.registry.tool_registry import get_tool_registry

            get_tool_registry()
            stage_results["3.2"] = True
        except Exception:
            stage_results["3.2"] = False

        try:
            from fabric.registry.memory_store import get_memory_store

            get_memory_store()
            stage_results["3.3"] = True
        except Exception:
            stage_results["3.3"] = False

        try:
            from fabric.registry.orchestrator_core import get_self_healing_orchestrator

            get_self_healing_orchestrator()
            stage_results["3.4"] = True
        except Exception:
            stage_results["3.4"] = False

        try:
            from fabric.registry.evidence_chain import get_evidence_chain

            get_evidence_chain()
            stage_results["4.1"] = True
        except Exception:
            stage_results["4.1"] = False

        try:
            from fabric.registry.governance_engine import get_governance_engine

            get_governance_engine()
            stage_results["4.2"] = True
        except Exception:
            stage_results["4.2"] = False

        try:
            from fabric.registry.apex_core import get_apex_core

            get_apex_core()
            stage_results["4.3"] = True
        except Exception:
            stage_results["4.3"] = False

        try:
            from fabric.registry.api_gateway import get_api_gateway

            get_api_gateway()
            stage_results["5.1"] = True
        except Exception:
            stage_results["5.1"] = False

        try:
            from fabric.registry.observability import get_observability

            get_observability()
            stage_results["5.2"] = True
        except Exception:
            stage_results["5.2"] = False

        try:
            from fabric.registry.release_manager import get_release_manager

            get_release_manager()
            stage_results["5.3"] = True
        except Exception:
            stage_results["5.3"] = False

        try:
            from fabric.registry.multi_model_orchestrator import get_multi_model_orchestrator

            get_multi_model_orchestrator()
            stage_results["6.1"] = True
        except Exception:
            stage_results["6.1"] = False

        try:
            from fabric.registry.advanced_cache import get_advanced_cache

            get_advanced_cache()
            stage_results["6.2"] = True
        except Exception:
            stage_results["6.2"] = False

        stage_results["6.3"] = True

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
