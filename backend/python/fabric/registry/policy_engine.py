from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fabric.registry.auth import ROLE_LEVELS
from fabric.registry.permission_enforcer import get_enforcer
from fabric.registry.registry_loader import get_registry

DECISION_ALLOW = "ALLOW"
DECISION_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
DECISION_DENY = "DENY"

# Actions classified beyond tool risk: irreversible / externally visible.
IRREVERSIBLE_ACTIONS = frozenset({"email.send", "files.write", "code.run", "sheets.write"})
SENSITIVE_PATTERNS = ("delete", "drop", "purge", "transfer", "publish", "deploy")


@dataclass(frozen=True)
class PolicyDecision:
    decision: str
    tool_name: str
    role: str
    risk: str
    reasons: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision != DECISION_DENY

    @property
    def requires_human_approval(self) -> bool:
        return self.decision == DECISION_REQUIRE_APPROVAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "tool_name": self.tool_name,
            "role": self.role,
            "risk": self.risk,
            "allowed": self.allowed,
            "requires_human_approval": self.requires_human_approval,
            "reasons": self.reasons,
            "details": self.details,
        }


class PolicyEngine:
    """Stage 2.1 — declarative policy over the Stage 1.2 enforcement layer.

    Order: role gate (DENY) → quota/budget gate (DENY) → risk gate
    (HIGH → REQUIRE_APPROVAL, LOW → ALLOW). Decisions are pure functions of
    registry metadata — no network, no cost.
    """

    def classify_risk(self, tool_name: str, intent: str = "") -> str:
        registry = get_registry()
        tool = registry.get(tool_name)
        base = "HIGH" if (tool and tool.get("risk_level") == "HIGH") else "LOW"
        lowered = intent.lower()
        if any(pattern in lowered for pattern in SENSITIVE_PATTERNS):
            return "HIGH"
        return base

    def evaluate(self, tool_name: str, role: str = "User", intent: str = "", approved: bool = False) -> PolicyDecision:
        registry = get_registry()
        if tool_name not in registry:
            return PolicyDecision(DECISION_DENY, tool_name, role, "UNKNOWN", [f"unknown tool: {tool_name}"])
        if role not in ROLE_LEVELS:
            return PolicyDecision(DECISION_DENY, tool_name, role, "UNKNOWN", [f"unknown role: {role}"])

        risk = self.classify_risk(tool_name, intent)
        enforcer = get_enforcer()
        permission = enforcer.check_permission(tool_name, role)
        quota = enforcer.check_quota(tool_name)
        budget = enforcer.check_budget(tool_name)
        details = {
            "permission": permission,
            "quota": quota,
            "budget": budget,
            "irreversible": tool_name in IRREVERSIBLE_ACTIONS,
            "policy_version": "2.1",
        }

        deny_reasons: list[str] = []
        if not permission["allowed"]:
            deny_reasons.append(permission["reason"])
        if not quota["allowed"]:
            deny_reasons.append(f"quota exhausted: {quota['used']}/{quota['limit']} per hour")
        if not budget["allowed"]:
            deny_reasons.append(f"budget exceeded: {budget['spent_today']}/{budget['limit_per_day']} USD")
        if deny_reasons:
            return PolicyDecision(DECISION_DENY, tool_name, role, risk, deny_reasons, details)

        if risk == "HIGH":
            reasons = [f"risk_level=HIGH for {tool_name}"]
            if tool_name in IRREVERSIBLE_ACTIONS:
                reasons.append("irreversible action class")
            if approved:
                return PolicyDecision(DECISION_ALLOW, tool_name, role, risk, reasons + ["pre-approved"], details)
            reasons.append("human approval required (Telegram gate or /approvals)")
            return PolicyDecision(DECISION_REQUIRE_APPROVAL, tool_name, role, risk, reasons, details)

        return PolicyDecision(DECISION_ALLOW, tool_name, role, risk, ["risk_level=LOW, auto-execute"], details)

    def evaluate_token(self, tool_name: str, role: str, intent: str = "") -> PolicyDecision:
        return self.evaluate(tool_name, role=role, intent=intent)


_engine: PolicyEngine | None = None


def get_policy_engine() -> PolicyEngine:
    global _engine
    if _engine is None:
        _engine = PolicyEngine()
    return _engine
