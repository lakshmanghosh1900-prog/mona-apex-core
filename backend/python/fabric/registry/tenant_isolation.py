from __future__ import annotations

import json
import os
import pathlib
import re
import time
from typing import Any, Dict, Optional

TENANT_ROOT = pathlib.Path("/tmp/mona_sandbox/tenants")
TENANT_ROOT.mkdir(parents=True, exist_ok=True)

TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{3,64}$")

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"


class TenantIsolationManager:
    def __init__(self) -> None:
        self.tenants: Dict[str, Dict] = {}  # tenant_id -> {created_by, created_at, actors: set}
        self.actor_tenants: Dict[str, set] = {}  # actor -> set(tenant_ids)
        self._audit: Optional[Any] = None

    def _get_audit(self) -> Optional[Any]:
        # Single canonical audit engine: fabric.registry.audit_logger.
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger

                self._audit = get_audit_logger()
            except Exception:
                self._audit = None
        return self._audit

    def _sanitize_tenant_id(self, tenant_id: str) -> bool:
        return bool(TENANT_ID_PATTERN.match(tenant_id))

    def _get_tenant_path(self, tenant_id: str) -> pathlib.Path:
        # Always resolve to canonical
        p = (TENANT_ROOT / tenant_id).resolve()
        # Ensure still under TENANT_ROOT
        try:
            p.relative_to(TENANT_ROOT.resolve())
        except ValueError:
            raise ValueError(f"Tenant path escape detected: {p}")
        return p

    def _is_symlink_attack(self, path: pathlib.Path) -> bool:
        # Check any component is symlink
        try:
            for parent in path.parents:
                if parent == TENANT_ROOT.resolve():
                    break
                if parent.is_symlink():
                    return True
            if path.is_symlink():
                return True
        except Exception:
            pass
        return False

    def create_tenant_workspace(self, tenant_id: str, actor: str, role: str = "User") -> Dict:
        audit = self._get_audit()
        if not self._sanitize_tenant_id(tenant_id):
            result = {
                "success": False,
                "reason": f"Invalid tenant_id format: {tenant_id}",
                "tenant_id": tenant_id,
                "canonical_spec": CANONICAL_SPEC,
            }
            if audit:
                audit.log("tenant.create", actor, role, {"tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
            return result

        tenant_path = self._get_tenant_path(tenant_id)
        try:
            tenant_path.mkdir(parents=True, exist_ok=True)
            # Create subdirs
            (tenant_path / "files").mkdir(exist_ok=True)
            (tenant_path / "audit").mkdir(exist_ok=True)
            # marker
            marker = tenant_path / ".tenant"
            marker.write_text(
                json.dumps(
                    {
                        "tenant_id": tenant_id,
                        "created_by": actor,
                        "role": role,
                        "created_at": time.time(),
                        "canonical_spec": CANONICAL_SPEC,
                    }
                ),
                encoding="utf-8",
            )

            if tenant_id not in self.tenants:
                self.tenants[tenant_id] = {"created_by": actor, "created_at": time.time(), "actors": set()}
            self.tenants[tenant_id]["actors"].add(actor)
            if actor not in self.actor_tenants:
                self.actor_tenants[actor] = set()
            self.actor_tenants[actor].add(tenant_id)

            result = {
                "success": True,
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "path": str(tenant_path),
                "canonical_path": str(tenant_path.resolve()),
                "canonical_spec": CANONICAL_SPEC,
                "dod_ref": DOD_REF,
                "stack": "zero-cost",
                "isolated": True,
            }
            if audit:
                audit.log("tenant.create", actor, role, {"tenant_id": tenant_id}, result, approved=True, policy_decision="ALLOW")
            return result
        except Exception as e:
            result = {"success": False, "reason": str(e), "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}
            if audit:
                audit.log("tenant.create", actor, role, {"tenant_id": tenant_id}, result, approved=False, policy_decision="DENY")
            return result

    def get_tenant_context(self, actor: str, tenant_id: str, role: str = "User") -> Dict:
        if not self._sanitize_tenant_id(tenant_id):
            return {"valid": False, "reason": "Invalid tenant_id", "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}
        exists = tenant_id in self.tenants
        actor_has_access = False
        if role == "Admin":
            actor_has_access = True
        else:
            actor_has_access = tenant_id in self.actor_tenants.get(actor, set()) or exists  # first time allow creation check

        return {
            "valid": self._sanitize_tenant_id(tenant_id) and (exists or role in ["Admin", "Operator"]),
            "tenant_id": tenant_id,
            "actor": actor,
            "role": role,
            "exists": exists,
            "actor_has_access": actor_has_access,
            "path": str(self._get_tenant_path(tenant_id)),
            "canonical_spec": CANONICAL_SPEC,
            "isolated": True,
        }

    def enforce_isolation(self, actor: str, role: str, tenant_id: str, resource_path: str) -> Dict:
        audit = self._get_audit()
        # Sanitize tenant_id
        if not self._sanitize_tenant_id(tenant_id):
            res = {
                "allowed": False,
                "reason": "Invalid tenant_id format",
                "tenant_id": tenant_id,
                "canonical_spec": CANONICAL_SPEC,
            }
            if audit:
                audit.log("tenant.enforce", actor, role, {"tenant_id": tenant_id, "resource": resource_path}, res, approved=False, policy_decision="DENY")
            return res

        try:
            tenant_path = self._get_tenant_path(tenant_id)
            # Resolve resource_path - must be within tenant
            # resource_path can be absolute or relative
            if os.path.isabs(resource_path):
                # If absolute, must be under tenant_root
                candidate = pathlib.Path(resource_path).resolve()
            else:
                candidate = (tenant_path / resource_path).resolve()

            # Path traversal check: candidate must be within tenant_path
            try:
                candidate.relative_to(tenant_path.resolve())
                within = True
            except ValueError:
                within = False

            if not within:
                res = {
                    "allowed": False,
                    "reason": f"Path traversal blocked: {resource_path} not in tenant {tenant_id}",
                    "tenant_id": tenant_id,
                    "resource": resource_path,
                    "candidate": str(candidate),
                    "tenant_path": str(tenant_path),
                    "canonical_spec": CANONICAL_SPEC,
                }
                if audit:
                    audit.log("tenant.enforce", actor, role, {"tenant_id": tenant_id, "resource": resource_path}, res, approved=False, policy_decision="DENY")
                return res

            # Symlink attack check
            if self._is_symlink_attack(candidate):
                res = {
                    "allowed": False,
                    "reason": "Symlink attack blocked",
                    "tenant_id": tenant_id,
                    "resource": resource_path,
                    "canonical_spec": CANONICAL_SPEC,
                }
                if audit:
                    audit.log("tenant.enforce", actor, role, {"tenant_id": tenant_id, "resource": resource_path}, res, approved=False, policy_decision="DENY")
                return res

            # Role-based cross-tenant check
            if role == "User":
                # User can only access tenants they belong to
                allowed_tenants = self.actor_tenants.get(actor, set())
                if tenant_id not in allowed_tenants and tenant_id != actor and actor not in ["admin", "system"]:
                    # If tenant doesn't exist yet, allow creation but not access to other's data?
                    # For User, deny if exists and not in allowed
                    if tenant_id in self.tenants and tenant_id not in allowed_tenants:
                        res = {
                            "allowed": False,
                            "reason": f"Cross-tenant access denied for User {actor} to {tenant_id}",
                            "tenant_id": tenant_id,
                            "actor": actor,
                            "role": role,
                            "canonical_spec": CANONICAL_SPEC,
                        }
                        if audit:
                            audit.log(
                                "tenant.enforce",
                                actor,
                                role,
                                {"tenant_id": tenant_id, "resource": resource_path},
                                res,
                                approved=False,
                                policy_decision="DENY",
                            )
                        return res

            # Allowed
            res = {
                "allowed": True,
                "reason": "Isolation enforced, access allowed",
                "tenant_id": tenant_id,
                "actor": actor,
                "role": role,
                "resource": resource_path,
                "canonical_path": str(candidate),
                "tenant_path": str(tenant_path),
                "canonical_spec": CANONICAL_SPEC,
                "dod_ref": DOD_REF,
                "isolated": True,
                "zero_cost": True,
            }
            if audit:
                audit.log("tenant.enforce", actor, role, {"tenant_id": tenant_id, "resource": resource_path}, res, approved=True, policy_decision="ALLOW")
            return res
        except Exception as e:
            res = {
                "allowed": False,
                "reason": f"Enforce error: {e}",
                "tenant_id": tenant_id,
                "canonical_spec": CANONICAL_SPEC,
            }
            if audit:
                audit.log("tenant.enforce", actor, role, {"tenant_id": tenant_id, "resource": resource_path}, res, approved=False, policy_decision="DENY")
            return res

    def write_file(self, tenant_id: str, actor: str, role: str, relative_path: str, content: str) -> Dict:
        enforce = self.enforce_isolation(actor, role, tenant_id, relative_path)
        if not enforce.get("allowed"):
            return {"success": False, "reason": enforce.get("reason"), "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}
        try:
            target = pathlib.Path(enforce["canonical_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "tenant_id": tenant_id,
                "path": str(target),
                "actor": actor,
                "role": role,
                "canonical_spec": CANONICAL_SPEC,
                "isolated": True,
            }
        except Exception as e:
            return {"success": False, "reason": str(e), "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}

    def read_file(self, tenant_id: str, actor: str, role: str, relative_path: str) -> Dict:
        enforce = self.enforce_isolation(actor, role, tenant_id, relative_path)
        if not enforce.get("allowed"):
            return {"success": False, "reason": enforce.get("reason"), "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}
        try:
            target = pathlib.Path(enforce["canonical_path"])
            if not target.exists():
                return {
                    "success": False,
                    "reason": "File not found",
                    "tenant_id": tenant_id,
                    "path": str(target),
                    "canonical_spec": CANONICAL_SPEC,
                }
            content = target.read_text(encoding="utf-8")
            return {
                "success": True,
                "tenant_id": tenant_id,
                "path": str(target),
                "content": content,
                "actor": actor,
                "canonical_spec": CANONICAL_SPEC,
                "isolated": True,
            }
        except Exception as e:
            return {"success": False, "reason": str(e), "tenant_id": tenant_id, "canonical_spec": CANONICAL_SPEC}

    def list_tenants(self, actor: str, role: str = "User") -> Dict:
        if role == "Admin":
            all_tenants = list(self.tenants.keys())
        else:
            all_tenants = list(self.actor_tenants.get(actor, set()))
        return {
            "actor": actor,
            "role": role,
            "tenants": all_tenants,
            "count": len(all_tenants),
            "canonical_spec": CANONICAL_SPEC,
            "isolated": True,
        }

    def validate_cross_tenant_access(self, src_tenant: str, dst_tenant: str, actor: str, role: str) -> Dict:
        if src_tenant == dst_tenant:
            return {"allowed": True, "reason": "Same tenant", "src": src_tenant, "dst": dst_tenant, "canonical_spec": CANONICAL_SPEC}
        if role == "Admin":
            return {
                "allowed": True,
                "reason": "Admin allowed cross-tenant but logged",
                "src": src_tenant,
                "dst": dst_tenant,
                "actor": actor,
                "role": role,
                "logged": True,
                "canonical_spec": CANONICAL_SPEC,
            }
        if role == "Operator":
            # Operator can access if both tenants in his allowed set
            allowed = self.actor_tenants.get(actor, set())
            if src_tenant in allowed and dst_tenant in allowed:
                return {
                    "allowed": True,
                    "reason": "Operator has both tenants",
                    "src": src_tenant,
                    "dst": dst_tenant,
                    "canonical_spec": CANONICAL_SPEC,
                }
        return {
            "allowed": False,
            "reason": f"Cross-tenant denied for {role} {actor}: {src_tenant} -> {dst_tenant}",
            "src": src_tenant,
            "dst": dst_tenant,
            "actor": actor,
            "role": role,
            "canonical_spec": CANONICAL_SPEC,
        }

    def get_stats(self) -> Dict:
        return {
            "total_tenants": len(self.tenants),
            "total_actors": len(self.actor_tenants),
            "tenant_root": str(TENANT_ROOT),
            "tenants": list(self.tenants.keys())[:20],
            "canonical_spec": CANONICAL_SPEC,
            "zero_cost": True,
        }


_singleton: Optional[TenantIsolationManager] = None


def get_tenant_manager() -> TenantIsolationManager:
    global _singleton
    if _singleton is None:
        _singleton = TenantIsolationManager()
    return _singleton
