import time
import threading
import pathlib
import json
from typing import Dict, List, Optional

MEMORY_ROOT = pathlib.Path("/tmp/mona_sandbox/memory")
DEPLOY_ROOT = MEMORY_ROOT / "deployment"
DEPLOY_ROOT.mkdir(parents=True, exist_ok=True)

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class DeploymentManager:
    """Stage 7.1 - deployment records + multi-component health probe.
    Zero-cost, stdlib only."""

    def __init__(self):
        self.deployments: List[Dict] = []
        self.health_checks: List[Dict] = []
        self._lock = threading.RLock()
        self._release_manager = None
        self._observability = None

    def _get_release_manager(self):
        if self._release_manager is None:
            try:
                from fabric.registry.release_manager import get_release_manager
                self._release_manager = get_release_manager()
            except Exception:
                self._release_manager = None
        return self._release_manager

    def _get_observability(self):
        if self._observability is None:
            try:
                from fabric.registry.observability import get_observability
                self._observability = get_observability()
            except Exception:
                self._observability = None
        return self._observability

    def deploy(self, version: str, env: str = "production", actor: str = "system") -> Dict:
        if not version:
            return {"success": False, "reason": "Version required", "canonical_spec": CANONICAL_SPEC}
        entry = {
            "version": version,
            "env": env,
            "actor": actor,
            "status": "DEPLOYED",
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
            "isolated": True,
        }
        with self._lock:
            self.deployments.append(entry)
            try:
                (DEPLOY_ROOT / f"deploy_{version}_{int(time.time())}.json").write_text(json.dumps(entry, indent=2))
            except Exception:
                pass
        obs = self._get_observability()
        if obs:
            obs.record_metric("deployment", 1.0, {"version": version, "env": env}, actor=actor)
        return {
            "success": True,
            "deployment": entry,
            "version": version,
            "env": env,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
            "isolated": True,
        }

    def health_probe(self, component: str = "api") -> Dict:
        checks = {}
        try:
            from fabric.registry.api_gateway import get_api_gateway
            checks["api_gateway"] = get_api_gateway() is not None
        except Exception:
            checks["api_gateway"] = False
        try:
            from fabric.registry.apex_core import get_apex_core
            checks["apex_core"] = get_apex_core() is not None
        except Exception:
            checks["apex_core"] = False
        try:
            from fabric.registry.observability import get_observability
            checks["observability"] = get_observability() is not None
        except Exception:
            checks["observability"] = False
        try:
            from fabric.registry.enterprise_audit import get_enterprise_audit
            checks["enterprise_audit"] = get_enterprise_audit() is not None
        except Exception:
            checks["enterprise_audit"] = False
        all_ok = all(checks.values())
        entry = {
            "component": component,
            "checks": checks,
            "healthy": all_ok,
            "all_ok": all_ok,
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }
        with self._lock:
            self.health_checks.append(entry)
        return {
            "component": component,
            "healthy": all_ok,
            "all_checks": all_ok,
            "checks": checks,
            "passed": sum(1 for v in checks.values() if v),
            "total": len(checks),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }

    def get_deployments(self, limit: int = 20) -> Dict:
        with self._lock:
            return {
                "count": len(self.deployments),
                "deployments": self.deployments[-limit:],
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
            }

    def get_health_history(self, limit: int = 20) -> Dict:
        with self._lock:
            return {
                "count": len(self.health_checks),
                "checks": self.health_checks[-limit:],
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
            }

    def get_stats(self) -> Dict:
        with self._lock:
            wired = {
                "release_manager": self._get_release_manager() is not None,
                "observability": self._get_observability() is not None,
            }
            return {
                "total_deployments": len(self.deployments),
                "total_health_checks": len(self.health_checks),
                "healthy": sum(1 for h in self.health_checks if h.get("all_ok")),
                "wired": wired,
                "wired_all": all(wired.values()),
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "dod_ref": DOD_REF,
            }


_singleton = None
_lock = threading.Lock()


def get_deployment_manager() -> DeploymentManager:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = DeploymentManager()
    return _singleton
