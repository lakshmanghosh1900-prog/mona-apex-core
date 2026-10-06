import time
import threading
import pathlib
import json
from typing import Dict, List, Optional

MEMORY_ROOT = pathlib.Path("/tmp/mona_sandbox/memory")
OBS_ROOT = MEMORY_ROOT / "observability"
OBS_ROOT.mkdir(parents=True, exist_ok=True)

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class Observability:
    """Stage 5.2 - metrics, health checks and component wiring. Zero-cost."""

    def __init__(self):
        self.metrics: Dict[str, List[Dict]] = {}
        self.logs: List[Dict] = []
        self.health_checks: List[Dict] = []
        self._lock = threading.RLock()
        self._audit = None
        self._apex_core = None

    def _get_audit(self):
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit = get_audit_logger()
            except Exception:
                self._audit = None
        return self._audit

    def _get_apex_core(self):
        if self._apex_core is None:
            try:
                from fabric.registry.apex_core import get_apex_core
                self._apex_core = get_apex_core()
            except Exception:
                self._apex_core = None
        return self._apex_core

    def record_metric(self, name: str, value: float, labels: Dict = None, actor: str = "system", tenant_id: str = "default") -> Dict:
        if not name:
            return {"success": False, "reason": "Invalid metric name", "canonical_spec": CANONICAL_SPEC}
        with self._lock:
            entry = {"name": name, "value": value, "labels": labels or {}, "actor": actor, "tenant_id": tenant_id, "timestamp": time.time(), "canonical_spec": CANONICAL_SPEC, "zero_cost": True}
            if name not in self.metrics:
                self.metrics[name] = []
            self.metrics[name].append(entry)
            self.logs.append(entry)
        audit = self._get_audit()
        if audit:
            try:
                if hasattr(audit, "record"):
                    audit.record("metric.record", actor=actor, role="User", decision="ALLOW", detail={"metric": name, "value": value})
                else:
                    audit.log(
                        "metric.record",
                        actor,
                        "User",
                        {"metric": name, "labels": labels or {}, "tenant_id": tenant_id},
                        {"success": True, "metric": name, "value": value},
                        approved=True,
                        policy_decision="ALLOW",
                    )
            except Exception:
                pass
        return {"success": True, "metric": name, "value": value, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def health_check(self, component: str = "api", actor: str = "system") -> Dict:
        checks: Dict[str, bool] = {}
        try:
            from fabric.registry.tool_registry import get_tool_registry
            checks["tool_registry"] = get_tool_registry() is not None
        except Exception:
            checks["tool_registry"] = False
        try:
            from fabric.registry.execution_sandbox import get_execution_sandbox
            checks["execution_sandbox"] = get_execution_sandbox() is not None
        except Exception:
            checks["execution_sandbox"] = False
        try:
            from fabric.registry.memory_store import get_memory_store
            checks["memory_store"] = get_memory_store() is not None
        except Exception:
            checks["memory_store"] = False
        try:
            from fabric.registry.evidence_chain import get_evidence_chain
            checks["evidence_chain"] = get_evidence_chain() is not None
        except Exception:
            checks["evidence_chain"] = False
        try:
            from fabric.registry.governance_engine import get_governance_engine
            checks["governance_engine"] = get_governance_engine() is not None
        except Exception:
            checks["governance_engine"] = False
        checks["apex_core"] = self._get_apex_core() is not None
        all_ok = all(checks.values())
        entry = {"component": component, "checks": checks, "all_ok": all_ok, "actor": actor, "timestamp": time.time(), "canonical_spec": CANONICAL_SPEC, "zero_cost": True}
        with self._lock:
            self.health_checks.append(entry)
        try:
            (OBS_ROOT / f"health_{int(time.time() * 1000)}.json").write_text(json.dumps(entry, indent=2, default=str))
        except Exception:
            pass
        return {
            "component": component,
            "healthy": all_ok,
            "checks": checks,
            "all_checks": all_ok,
            "passed": sum(1 for v in checks.values() if v),
            "total": len(checks),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }

    def get_metrics(self, name: Optional[str] = None, limit: int = 50) -> Dict:
        with self._lock:
            if name:
                data = self.metrics.get(name, [])[-limit:]
                return {"name": name, "count": len(data), "metrics": data, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}
            all_metrics: List[Dict] = []
            for v in self.metrics.values():
                all_metrics.extend(v)
            return {"count": len(all_metrics), "metrics": all_metrics[-limit:], "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def get_health_history(self, limit: int = 20) -> Dict:
        with self._lock:
            return {"count": len(self.health_checks), "checks": self.health_checks[-limit:], "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def get_stats(self) -> Dict:
        with self._lock:
            return {
                "total_metrics": sum(len(v) for v in self.metrics.values()),
                "metric_names": list(self.metrics.keys()),
                "total_logs": len(self.logs),
                "total_health_checks": len(self.health_checks),
                "healthy": len([h for h in self.health_checks if h.get("all_ok")]),
                "wired": {"apex_core": self._get_apex_core() is not None, "audit": self._get_audit() is not None},
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "dod_ref": DOD_REF,
                "stack": "zero-cost",
            }


_singleton = None
_lock = threading.Lock()


def get_observability() -> Observability:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = Observability()
    return _singleton
