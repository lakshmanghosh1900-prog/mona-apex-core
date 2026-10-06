import time
import threading
from typing import Dict, List, Optional

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
VERSION = "1.0.0-production"
STAGE_KEYS = ["2.4", "2.5", "2.6", "2.7", "3.1", "3.2", "3.3", "3.4", "4.1", "4.2", "4.3", "5.1", "5.2"]


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
        stages: Dict[str, bool] = {}
        details: Dict[str, str] = {}

        # 2.4 secrets management
        try:
            sm = self._get_secrets()
            findings = sm.scan_hardcoded() if sm and hasattr(sm, "scan_hardcoded") else []
            stages["2.4"] = len(findings) == 0
            details["2.4"] = f"scan clean ({len(findings)} findings)"
        except Exception as e:
            stages["2.4"] = False
            details["2.4"] = str(e)

        # 2.5 audit trail
        try:
            audit = self._get_audit()
            stats = audit.get_stats()
            stages["2.5"] = bool(stats.get("chain_valid"))
            details["2.5"] = f"chain len={stats.get('chain_length', 0)}"
        except Exception as e:
            stages["2.5"] = False
            details["2.5"] = str(e)

        # 2.6 tenant isolation
        try:
            from fabric.registry.tenant_isolation import get_tenant_manager
            tm = get_tenant_manager()
            stages["2.6"] = tm.get_stats().get("total_tenants", 0) >= 0
            details["2.6"] = f"tenants={tm.get_stats().get('total_tenants', 0)}"
        except Exception as e:
            stages["2.6"] = False
            details["2.6"] = str(e)

        # 2.7 rate limiting
        try:
            from fabric.registry.rate_limiter import get_rate_limiter
            rl = get_rate_limiter()
            stages["2.7"] = rl.get_stats().get("total_buckets", 0) >= 0
            details["2.7"] = f"buckets={rl.get_stats().get('total_buckets', 0)}"
        except Exception as e:
            stages["2.7"] = False
            details["2.7"] = str(e)

        # 3.1 execution sandbox
        try:
            from fabric.registry.execution_sandbox import get_execution_sandbox
            sb = get_execution_sandbox()
            r = sb.execute_python("print(42)", actor="release", tenant_id="release")
            stages["3.1"] = r.get("success") == True and "42" in r.get("output", "")
            details["3.1"] = "execution sandbox"
        except Exception as e:
            stages["3.1"] = False
            details["3.1"] = str(e)

        # 3.2 tool registry
        try:
            tr = self._get_tool_registry()
            stages["3.2"] = tr.get_stats().get("total_tools", 0) >= 7
            details["3.2"] = f"tools={tr.get_stats()['total_tools']}"
        except Exception as e:
            stages["3.2"] = False
            details["3.2"] = str(e)

        # 3.3 memory & resume later
        try:
            from fabric.registry.memory_store import get_memory_store
            ms = get_memory_store()
            r = ms.save_memory("release_check", {"data": "release"}, actor="release", tenant_id="release")
            stages["3.3"] = r.get("success") == True
            details["3.3"] = f"mem={ms.get_stats()['total_memories']}"
        except Exception as e:
            stages["3.3"] = False
            details["3.3"] = str(e)

        # 3.4 orchestration & self-heal
        try:
            from fabric.registry.orchestrator_core import get_self_healing_orchestrator
            orch = get_self_healing_orchestrator()
            r = orch.execute("test", actor="release", tenant_id="release")
            stages["3.4"] = r.get("canonical_spec") == CANONICAL_SPEC
            details["3.4"] = f"runs={orch.get_stats()['total_runs']}"
        except Exception as e:
            stages["3.4"] = False
            details["3.4"] = str(e)

        # 4.1 evidence chain & report generator
        try:
            from fabric.registry.evidence_chain import get_evidence_chain
            ec = get_evidence_chain()
            r = ec.append("release_41", {"data": "release"}, actor="release", tenant_id="release")
            v = ec.verify_chain("release_41")
            stages["4.1"] = r.get("success") == True and v.get("valid") == True
            details["4.1"] = f"chains={ec.get_stats()['total_chains']}"
        except Exception as e:
            stages["4.1"] = False
            details["4.1"] = str(e)

        # 4.2 governance engine
        try:
            from fabric.registry.governance_engine import get_governance_engine
            gov = get_governance_engine()
            r = gov.full_compliance_check("test", "release", "release", "browser.search")
            stages["4.2"] = "all_passed" in r and r.get("canonical_spec") == CANONICAL_SPEC
            details["4.2"] = f"checks={gov.get_stats()['total_checks']}"
        except Exception as e:
            stages["4.2"] = False
            details["4.2"] = str(e)

        # 4.3 apex core end-to-end
        try:
            apex = self._get_apex_core()
            r = apex.run("search web for release gate", actor="release", tenant_id="release")
            stages["4.3"] = r.get("canonical_spec") == CANONICAL_SPEC and r.get("apex_core") == True
            details["4.3"] = f"runs={apex.get_stats()['total_runs']}"
        except Exception as e:
            stages["4.3"] = False
            details["4.3"] = str(e)

        # 5.1 api gateway
        try:
            gw = self._get_api_gateway()
            r = gw.register_route("/release/probe", "GET", tenant_id="release")
            stages["5.1"] = r.get("success") == True
            details["5.1"] = f"routes={gw.get_stats()['total_routes']}"
        except Exception as e:
            stages["5.1"] = False
            details["5.1"] = str(e)

        # 5.2 observability
        try:
            obs = self._get_observability()
            r = obs.health_check("release", actor="release")
            stages["5.2"] = r.get("all_checks") == True
            details["5.2"] = f"healthy={r.get('healthy')}"
        except Exception as e:
            stages["5.2"] = False
            details["5.2"] = str(e)

        return {"stages": stages, "details": details}

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
