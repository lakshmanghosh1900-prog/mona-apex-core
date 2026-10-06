import time
import threading
from typing import Dict, List, Optional

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
VERSION = "1.0.0-production"

# Canonical stage keys for the release matrix (D1): owned by
# fabric.registry.stage_sweep.RELEASE_STAGE_KEYS.
from fabric.registry.stage_sweep import RELEASE_STAGE_KEYS as STAGE_KEYS  # noqa: E402


class ReleaseManager:
    """Stage 5.3 - production release pipeline: runs the full stage matrix
    (2.4 -> 5.2) and only marks a release production-ready when every gate
    passes. Zero-cost, stdlib only."""

    def __init__(self):
        self.releases: List[Dict] = []
        self._lock = threading.RLock()
        self._audit = None
        self._secrets = None
        self._tool_registry = None
        self._api_gateway = None
        self._observability = None
        self._apex_core = None

    def _get_audit(self):
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger
                self._audit = get_audit_logger()
            except Exception:
                self._audit = None
        return self._audit

    def _get_secrets(self):
        if self._secrets is None:
            try:
                from fabric.registry.secrets_manager import get_secrets_manager
                self._secrets = get_secrets_manager()
            except Exception:
                self._secrets = None
        return self._secrets

    def _get_tool_registry(self):
        if self._tool_registry is None:
            try:
                from fabric.registry.tool_registry import get_tool_registry
                self._tool_registry = get_tool_registry()
            except Exception:
                self._tool_registry = None
        return self._tool_registry

    def _get_api_gateway(self):
        if self._api_gateway is None:
            try:
                from fabric.registry.api_gateway import get_api_gateway
                self._api_gateway = get_api_gateway()
            except Exception:
                self._api_gateway = None
        return self._api_gateway

    def _get_observability(self):
        if self._observability is None:
            try:
                from fabric.registry.observability import get_observability
                self._observability = get_observability()
            except Exception:
                self._observability = None
        return self._observability

    def _get_apex_core(self):
        if self._apex_core is None:
            try:
                from fabric.registry.apex_core import get_apex_core
                self._apex_core = get_apex_core()
            except Exception:
                self._apex_core = None
        return self._apex_core

    def _run_stage_matrix(self) -> Dict:
        """Release stage matrix (D1): delegates to the central stage sweep.

        Runs functional probes for stages 2.4 -> 5.2 (RELEASE_STAGE_KEYS)
        instead of maintaining a private copy of every probe.
        """
        from fabric.registry.stage_sweep import run_stage_sweep

        result = run_stage_sweep(
            start="2.4",
            end="5.2",
            actor="release",
            tenant_id="release",
            mode="functional",
            memory_key="release_check",
            evidence_key="release_41",
            orch_task="test",
            apex_task="search web for release gate",
            gateway_route="/release/probe",
            health_component="release",
        )
        return {"stages": result["stages"], "details": result["details"]}

    def create_release(self, version: str = VERSION, actor: str = "system", tenant_id: str = "default") -> Dict:
        matrix = self._run_stage_matrix()
        stages = matrix["stages"]
        passed = sum(1 for v in stages.values() if v)
        total = len(stages)
        all_ok = total > 0 and passed == total
        record = {
            "version": version,
            "stages": stages,
            "details": matrix["details"],
            "passed": passed,
            "total": total,
            "production_ready": all_ok,
            "actor": actor,
            "tenant_id": tenant_id,
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
        }
        with self._lock:
            self.releases.append(record)
        audit = self._get_audit()
        if audit:
            try:
                if hasattr(audit, "record"):
                    audit.record("release.create", actor=actor, role="User", decision="ALLOW" if all_ok else "DENY", detail={"version": version, "passed": passed, "total": total})
                else:
                    audit.log(
                        "release.create",
                        actor,
                        "User",
                        {"version": version, "tenant_id": tenant_id},
                        {"success": all_ok, "passed": passed, "total": total, "production_ready": all_ok},
                        approved=all_ok,
                        policy_decision="ALLOW" if all_ok else "DENY",
                    )
            except Exception:
                pass
        return {
            "success": True,
            "version": version,
            "stages": stages,
            "passed": passed,
            "total": total,
            "production_ready": all_ok,
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
            "isolated": True,
        }

    def get_releases(self, limit: int = 20) -> Dict:
        with self._lock:
            return {
                "count": len(self.releases),
                "releases": self.releases[-limit:],
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
            }

    def get_stats(self) -> Dict:
        with self._lock:
            wired = {
                "audit": self._get_audit() is not None,
                "tool_registry": self._get_tool_registry() is not None,
                "api_gateway": self._get_api_gateway() is not None,
                "observability": self._get_observability() is not None,
                "apex_core": self._get_apex_core() is not None,
            }
            return {
                "version": VERSION,
                "total_releases": len(self.releases),
                "production_ready": sum(1 for r in self.releases if r.get("production_ready")),
                "last_production_ready": bool(self.releases[-1].get("production_ready")) if self.releases else None,
                "stage_keys": list(STAGE_KEYS),
                "wired": wired,
                "wired_all": all(wired.values()),
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "stack": "zero-cost",
                "dod_ref": DOD_REF,
            }


_singleton = None
_lock = threading.Lock()


def get_release_manager() -> ReleaseManager:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = ReleaseManager()
    return _singleton
