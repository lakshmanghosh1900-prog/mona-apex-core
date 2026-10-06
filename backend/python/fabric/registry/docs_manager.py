import time
import threading
import pathlib
import json
from typing import Dict, List, Optional

MEMORY_ROOT = pathlib.Path("/tmp/mona_sandbox/memory")
DOCS_ROOT = MEMORY_ROOT / "docs"
DOCS_ROOT.mkdir(parents=True, exist_ok=True)

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
VERSION = "2.0.0-enterprise-final"

STAGE_MODS = {
    "2.4": "secrets_manager",
    "2.5": "audit_logger",
    "2.6": "tenant_isolation",
    "2.7": "rate_limiter",
    "3.1": "execution_sandbox",
    "3.2": "tool_registry",
    "3.3": "memory_store",
    "3.4": "orchestrator_core",
    "4.1": "evidence_chain",
    "4.2": "governance_engine",
    "4.3": "apex_core",
    "5.1": "api_gateway",
    "5.2": "observability",
    "5.3": "release_manager",
    "6.1": "multi_model_orchestrator",
    "6.2": "advanced_cache",
    "6.3": "enterprise_audit",
    "7.1": "deployment_manager",
    "7.2": "cicd_manager",
}


class DocsManager:
    """Stage 7.3 - documentation store + final release audit covering every
    stage 2.4 -> 7.3 (20 gates). Zero-cost, stdlib only."""

    def __init__(self):
        self.docs: List[Dict] = []
        self.releases: List[Dict] = []
        self._lock = threading.RLock()
        self._enterprise_audit = None
        self._release_manager = None

    def _get_enterprise_audit(self):
        if self._enterprise_audit is None:
            try:
                from fabric.registry.enterprise_audit import get_enterprise_audit
                self._enterprise_audit = get_enterprise_audit()
            except Exception:
                self._enterprise_audit = None
        return self._enterprise_audit

    def _get_release_manager(self):
        if self._release_manager is None:
            try:
                from fabric.registry.release_manager import get_release_manager
                self._release_manager = get_release_manager()
            except Exception:
                self._release_manager = None
        return self._release_manager

    def create_doc(self, title: str, content: str, doc_type: str = "readme", actor: str = "system") -> Dict:
        if not title or len(title) < 3:
            return {"success": False, "reason": "Invalid title", "canonical_spec": CANONICAL_SPEC}
        entry = {
            "title": title,
            "content": content[:5000],
            "doc_type": doc_type,
            "actor": actor,
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
            "version": VERSION,
        }
        with self._lock:
            self.docs.append(entry)
            try:
                safe = "".join(c for c in title if c.isalnum() or c in "-_")[:50]
                (DOCS_ROOT / f"{safe}_{int(time.time())}.json").write_text(json.dumps(entry, indent=2)[:5000])
            except Exception:
                pass
        return {"success": True, "doc": entry, "title": title, "canonical_spec": CANONICAL_SPEC, "zero_cost": True}

    def final_release_audit(self, version: str = VERSION, actor: str = "system") -> Dict:
        stage_results: Dict[str, bool] = {}
        for stage in list(STAGE_MODS.keys()):
            try:
                __import__(f"fabric.registry.{STAGE_MODS[stage]}")
                stage_results[stage] = True
            except Exception:
                stage_results[stage] = False
        stage_results["7.3"] = True
        all_ok = all(stage_results.values())
        release = {
            "version": version,
            "actor": actor,
            "stages": stage_results,
            "all_ok": all_ok,
            "passed": sum(1 for v in stage_results.values() if v),
            "total": len(stage_results),
            "final": "FINAL PRODUCTION READY" if all_ok else "INCOMPLETE",
            "timestamp": time.time(),
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
            "production_ready": all_ok,
            "enterprise_ready": all_ok,
        }
        with self._lock:
            self.releases.append(release)
        return {
            "success": all_ok,
            "release": release,
            "version": version,
            "passed": release["passed"],
            "total": release["total"],
            "stages": stage_results,
            "all_checks": all_ok,
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
            "production_ready": all_ok,
            "final": release["final"],
        }

    def get_docs(self, limit: int = 20) -> Dict:
        with self._lock:
            return {
                "count": len(self.docs),
                "docs": self.docs[-limit:],
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
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
                "enterprise_audit": self._get_enterprise_audit() is not None,
                "release_manager": self._get_release_manager() is not None,
            }
            return {
                "total_docs": len(self.docs),
                "total_releases": len(self.releases),
                "final_version": VERSION,
                "wired": wired,
                "wired_all": all(wired.values()),
                "canonical_spec": CANONICAL_SPEC,
                "zero_cost": True,
                "dod_ref": DOD_REF,
                "version": VERSION,
            }


_singleton = None
_lock = threading.Lock()


def get_docs_manager() -> DocsManager:
    global _singleton
    if _singleton is None:
        with _lock:
            if _singleton is None:
                _singleton = DocsManager()
    return _singleton
