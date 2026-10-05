from __future__ import annotations

import threading
from typing import Any

CANONICAL_SPEC = "MONA - Powered by Apex Core"
DOD_REF = (
    "Understand->Plan->Select Model->Select Tool->Check Permission->Approval->"
    "Execute in Sandbox->Observe->Verify->Self-Heal->Evidence->Memory->Report->Resume Later"
)


class OrchestratorGuard:
    """Stage 2.2/2.3 — wires PolicyEngine + TenantIsolation + AuditLog + ApprovalGate
    into every tool call the orchestrator makes.

    Order: tenant isolation -> policy engine -> (async) approval gate -> audit.
    Zero-cost, stdlib only. All lookups are lazy and failure-tolerant so the guard
    degrades loudly in stats instead of crashing a run.
    """

    MUTATING_TOOLS = frozenset(
        {"files.write", "files.delete", "code.run", "email.send", "sheets.write", "telegram.send", "tool.mutate"}
    )

    def __init__(self) -> None:
        self._policy: Any = None
        self._audit: Any = None
        self._tenant: Any = None
        self._approval: Any = None
        self._approval_resolved = False
        self._lock = threading.Lock()

    # ---------- lazy wiring ----------
    def _get_policy(self) -> Any:
        if self._policy is None:
            try:
                from fabric.registry.policy_engine import get_policy_engine

                self._policy = get_policy_engine()
            except Exception:
                self._policy = None
        return self._policy

    def _get_audit(self) -> Any:
        if self._audit is None:
            try:
                from fabric.registry.audit_logger import get_audit_logger

                self._audit = get_audit_logger()
            except Exception:
                self._audit = None
        return self._audit

    def _get_tenant(self) -> Any:
        if self._tenant is None:
            try:
                from fabric.registry.tenant_isolation import get_tenant_manager

                self._tenant = get_tenant_manager()
            except Exception:
                self._tenant = None
        return self._tenant

    def _get_approval(self) -> Any:
        """Approval gate lives in core.telegram_approval (Stage 1 gate)."""
        if not self._approval_resolved:
            with self._lock:
                if not self._approval_resolved:
                    self._approval = None
                    try:
                        from core.telegram_approval import TelegramApprovalGate

                        self._approval = TelegramApprovalGate()
                    except Exception:
                        self._approval = None
                    self._approval_resolved = True
        return self._approval

    # ---------- helpers ----------
    @classmethod
    def is_mutating(cls, tool_name: str) -> bool:
        if tool_name in cls.MUTATING_TOOLS:
            return True
        return any(marker in tool_name for marker in ("write", "delete", "send", "run", "mutate"))

    def _audit_record(
        self,
        action: str,
        actor: str,
        role: str,
        resource: str,
        decision: str,
        detail: dict[str, Any],
        tenant_id: str = "",
    ) -> None:
        audit = self._get_audit()
        if audit is None:
            return
        try:
            audit.log(
                action,
                actor,
                role,
                {"resource": resource, "tenant_id": tenant_id, **detail},
                {"allowed": decision == "ALLOW", "success": decision == "ALLOW", "resource": resource, "tenant_id": tenant_id},
                approved=decision in ("ALLOW", "REQUIRE_APPROVAL"),
                policy_decision=decision,
            )
        except Exception:
            pass

    # ---------- the gate ----------
    def guard(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        actor: str = "system",
        role: str = "User",
        tenant_id: str = "default",
        resource: str = "",
        approved: bool = False,
        intent: str = "",
    ) -> dict[str, Any]:
        params = params or {}
        resource = resource or tool_name
        mutating = self.is_mutating(tool_name)

        base: dict[str, Any] = {
            "tool": tool_name,
            "actor": actor,
            "role": role,
            "tenant_id": tenant_id,
            "resource": resource,
            "is_mutating": mutating,
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
            "wiring": self.get_stats()["wired"],
        }

        # 1. tenant isolation
        tenant = self._get_tenant()
        if tenant is not None:
            try:
                iso = tenant.enforce_isolation(actor, role, tenant_id, resource)
                if not iso.get("allowed"):
                    base.update(
                        {
                            "allowed": False,
                            "decision": "DENY",
                            "reason": f"Tenant isolation: {iso.get('reason')}",
                            "stage": "tenant_isolation",
                        }
                    )
                    self._audit_record(f"guard.{tool_name}", actor, role, resource, "DENY", {"stage": "tenant_isolation", "reason": base["reason"]}, tenant_id=tenant_id)
                    return base
            except Exception as exc:  # noqa: BLE001
                base["tenant_error"] = f"{type(exc).__name__}: {exc}"

        # 2. policy engine
        policy = self._get_policy()
        if policy is None:
            base.update({"allowed": False, "decision": "DENY", "reason": "policy engine unavailable", "stage": "policy"})
            return base

        try:
            decision_obj = policy.evaluate(tool_name, role=role, intent=intent, approved=approved)
        except Exception as exc:  # noqa: BLE001
            base.update({"allowed": False, "decision": "DENY", "reason": f"policy error: {exc}", "stage": "policy"})
            return base

        policy_decision = getattr(decision_obj, "decision", "DENY")
        reasons = list(getattr(decision_obj, "reasons", []))

        if policy_decision == "DENY":
            base.update({"allowed": False, "decision": "DENY", "reason": "; ".join(reasons) or "policy DENY", "stage": "policy", "risk": getattr(decision_obj, "risk", "UNKNOWN")})
            self._audit_record(f"guard.{tool_name}", actor, role, resource, "DENY", {"stage": "policy", "reasons": reasons}, tenant_id=tenant_id)
            return base

        if policy_decision == "REQUIRE_APPROVAL":
            base.update(
                {
                    "allowed": False,
                    "decision": "REQUIRE_APPROVAL",
                    "reason": "; ".join(reasons),
                    "risk": getattr(decision_obj, "risk", "HIGH"),
                    "stage": "approval",
                    "approval_gate": "core.telegram_approval.TelegramApprovalGate",
                    "hint": "call guard_async() to await the human gate, or pass approved=True",
                }
            )
            self._audit_record(f"guard.{tool_name}", actor, role, resource, "REQUIRE_APPROVAL", {"stage": "approval", "mutating": mutating}, tenant_id=tenant_id)
            return base

        base.update({"allowed": True, "decision": "ALLOW", "reason": "; ".join(reasons) or "policy ALLOW", "stage": "complete", "risk": getattr(decision_obj, "risk", "LOW")})
        self._audit_record(f"guard.{tool_name}", actor, role, resource, "ALLOW", {"stage": "complete", "mutating": mutating}, tenant_id=tenant_id)
        return base

    async def guard_async(
        self,
        tool_name: str,
        params: dict[str, Any] | None = None,
        actor: str = "system",
        role: str = "User",
        tenant_id: str = "default",
        resource: str = "",
        intent: str = "",
    ) -> dict[str, Any]:
        """Await the Telegram approval gate when policy requires human approval."""
        pre = self.guard(tool_name, params, actor=actor, role=role, tenant_id=tenant_id, resource=resource, intent=intent)
        if pre.get("decision") != "REQUIRE_APPROVAL":
            return pre

        gate = self._get_approval()
        if gate is None:
            pre["approval_error"] = "approval gate unavailable"
            return pre

        step = {"tool": tool_name, "params": params or {}, "resource": resource or tool_name, "reason": pre.get("reason", "")}
        try:
            approved = await gate.request(f"{actor} requests {tool_name}", step)
        except Exception as exc:  # noqa: BLE001
            pre["approval_error"] = f"{type(exc).__name__}: {exc}"
            return pre

        if approved:
            final = self.guard(tool_name, params, actor=actor, role=role, tenant_id=tenant_id, resource=resource, approved=True, intent=intent)
            final["approved_by"] = "telegram_gate"
            return final

        pre.update({"allowed": False, "decision": "DENY", "reason": "human denied via approval gate", "stage": "approval"})
        self._audit_record(f"guard.{tool_name}", actor, role, resource or tool_name, "DENY", {"stage": "approval", "human": "denied"}, tenant_id=tenant_id)
        return pre

    # ---------- stats ----------
    def get_stats(self) -> dict[str, Any]:
        return {
            "mutating_tools": sorted(self.MUTATING_TOOLS),
            "wired": {
                "policy_engine": self._get_policy() is not None,
                "audit_log": self._get_audit() is not None,
                "tenant_isolation": self._get_tenant() is not None,
                "approval_gate": self._get_approval() is not None,
            },
            "canonical_spec": CANONICAL_SPEC,
            "dod_ref": DOD_REF,
            "zero_cost": True,
        }


_singleton: OrchestratorGuard | None = None
_singleton_lock = threading.Lock()


def get_orchestrator_guard() -> OrchestratorGuard:
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = OrchestratorGuard()
    return _singleton


def reset_orchestrator_guard() -> None:
    global _singleton
    with _singleton_lock:
        _singleton = None
