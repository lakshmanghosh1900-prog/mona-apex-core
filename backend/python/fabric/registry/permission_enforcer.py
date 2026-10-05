from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any

from fabric.registry.budget_manager import BudgetManager
from fabric.registry.registry_loader import get_registry

METADATA_FIELDS = (
    "tool_name",
    "timeout",
    "cost",
    "cost_per_1000",
    "retry_max",
    "retry_backoff",
    "quota_per_hour",
    "max_concurrent",
    "requires_approval",
    "budget_limit_per_day",
    "allowed_roles",
)
BACKOFF_STRATEGIES = ("exponential", "linear", "fixed")
ALL_ROLES = ("User", "Operator", "Admin", "Owner")
QUOTA_WINDOW_SECONDS = 3600

TOOL_METADATA_REGISTRY: dict[str, dict[str, Any]] = {
    "browser.search": {
        "tool_name": "browser.search",
        "timeout": 30,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 3,
        "retry_backoff": {"strategy": "exponential", "initial_seconds": 1.0, "multiplier": 2.0, "max_seconds": 8.0},
        "quota_per_hour": 100,
        "max_concurrent": 4,
        "requires_approval": False,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
    "browser.open": {
        "tool_name": "browser.open",
        "timeout": 45,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 2,
        "retry_backoff": {"strategy": "exponential", "initial_seconds": 1.0, "multiplier": 2.0, "max_seconds": 8.0},
        "quota_per_hour": 60,
        "max_concurrent": 4,
        "requires_approval": False,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
    "files.read": {
        "tool_name": "files.read",
        "timeout": 15,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 2,
        "retry_backoff": {"strategy": "fixed", "initial_seconds": 0.5, "multiplier": 1.0, "max_seconds": 0.5},
        "quota_per_hour": 500,
        "max_concurrent": 8,
        "requires_approval": False,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
    "files.write": {
        "tool_name": "files.write",
        "timeout": 15,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 1,
        "retry_backoff": {"strategy": "fixed", "initial_seconds": 0.0, "multiplier": 1.0, "max_seconds": 0.0},
        "quota_per_hour": 200,
        "max_concurrent": 2,
        "requires_approval": True,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
    "code.run": {
        "tool_name": "code.run",
        "timeout": 60,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 1,
        "retry_backoff": {"strategy": "fixed", "initial_seconds": 0.0, "multiplier": 1.0, "max_seconds": 0.0},
        "quota_per_hour": 50,
        "max_concurrent": 2,
        "requires_approval": True,
        "budget_limit_per_day": 0.0,
        "allowed_roles": ["Operator", "Admin", "Owner"],
    },
    "sheets.write": {
        "tool_name": "sheets.write",
        "timeout": 30,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 2,
        "retry_backoff": {"strategy": "exponential", "initial_seconds": 1.0, "multiplier": 2.0, "max_seconds": 8.0},
        "quota_per_hour": 120,
        "max_concurrent": 2,
        "requires_approval": True,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
    "email.send": {
        "tool_name": "email.send",
        "timeout": 30,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 2,
        "retry_backoff": {"strategy": "exponential", "initial_seconds": 2.0, "multiplier": 2.0, "max_seconds": 8.0},
        "quota_per_hour": 10,
        "max_concurrent": 1,
        "requires_approval": True,
        "budget_limit_per_day": 0.0,
        "allowed_roles": ["Admin", "Owner"],
    },
    "research.search": {
        "tool_name": "research.search",
        "timeout": 60,
        "cost": 0.0,
        "cost_per_1000": 0.0,
        "retry_max": 3,
        "retry_backoff": {"strategy": "exponential", "initial_seconds": 1.5, "multiplier": 2.0, "max_seconds": 8.0},
        "quota_per_hour": 60,
        "max_concurrent": 4,
        "requires_approval": False,
        "budget_limit_per_day": 0.0,
        "allowed_roles": list(ALL_ROLES),
    },
}


def validate_metadata(metadata: dict[str, dict[str, Any]] | None = None) -> list[str]:
    meta = metadata if metadata is not None else TOOL_METADATA_REGISTRY
    problems: list[str] = []
    if len(meta) < 8:
        problems.append(f"metadata must define at least 8 tools, got {len(meta)}")

    for name, entry in meta.items():
        for field_name in METADATA_FIELDS:
            if field_name not in entry:
                problems.append(f"{name}: missing '{field_name}'")
        if not isinstance(entry.get("timeout"), int) or entry.get("timeout", 0) < 1:
            problems.append(f"{name}: timeout must be an int >= 1")
        for cost_field in ("cost", "cost_per_1000", "budget_limit_per_day"):
            value = entry.get(cost_field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                problems.append(f"{name}: {cost_field} must be a non-negative number")
        if not isinstance(entry.get("retry_max"), int) or entry.get("retry_max", 0) < 1:
            problems.append(f"{name}: retry_max must be an int >= 1")
        backoff = entry.get("retry_backoff")
        if not isinstance(backoff, dict) or backoff.get("strategy") not in BACKOFF_STRATEGIES:
            problems.append(f"{name}: retry_backoff.strategy must be one of {BACKOFF_STRATEGIES}")
        elif not isinstance(backoff.get("initial_seconds"), (int, float)) or backoff["initial_seconds"] < 0:
            problems.append(f"{name}: retry_backoff.initial_seconds must be >= 0")
        if not isinstance(entry.get("quota_per_hour"), int) or entry.get("quota_per_hour", 0) < 1:
            problems.append(f"{name}: quota_per_hour must be an int >= 1")
        if not isinstance(entry.get("max_concurrent"), int) or entry.get("max_concurrent", 0) < 1:
            problems.append(f"{name}: max_concurrent must be an int >= 1")
        if not isinstance(entry.get("requires_approval"), bool):
            problems.append(f"{name}: requires_approval must be boolean")
        roles = entry.get("allowed_roles")
        if not isinstance(roles, list) or not roles:
            problems.append(f"{name}: allowed_roles must be a non-empty list")
        elif any(role not in ALL_ROLES for role in roles):
            problems.append(f"{name}: allowed_roles contains unknown role, allowed={ALL_ROLES}")
        if entry.get("tool_name") != name:
            problems.append(f"{name}: tool_name mismatch")
    return problems


def validate_registry_consistency() -> list[str]:
    """Metadata must not contradict the Stage 1.1 registry.json."""
    registry = get_registry()
    problems: list[str] = []
    for name, entry in TOOL_METADATA_REGISTRY.items():
        tool = registry.get(name)
        if tool is None:
            problems.append(f"{name}: present in metadata but missing from registry.json")
            continue
        if entry["timeout"] != tool["timeout"]:
            problems.append(f"{name}: timeout metadata={entry['timeout']} registry={tool['timeout']}")
        if entry["retry_max"] != tool["retry_policy"]["max_attempts"]:
            problems.append(f"{name}: retry_max metadata={entry['retry_max']} registry={tool['retry_policy']['max_attempts']}")
        if entry["cost"] != tool["cost"]["per_call"]:
            problems.append(f"{name}: cost metadata={entry['cost']} registry={tool['cost']['per_call']}")
        expected_approval = tool["risk_level"] == "HIGH"
        if entry["requires_approval"] != expected_approval:
            problems.append(f"{name}: requires_approval metadata={entry['requires_approval']} registry_risk={tool['risk_level']}")
    for name in registry.names():
        if name not in TOOL_METADATA_REGISTRY:
            problems.append(f"{name}: present in registry.json but missing from TOOL_METADATA_REGISTRY")
    return problems


class PermissionEnforcer:
    """Stage 1.2 enforcement: role, approval, quota, budget, concurrency
    plus timeout/retry policy lookup. Stdlib only, $0 stack."""

    def __init__(self, budget: BudgetManager | None = None) -> None:
        self.budget = budget or BudgetManager()
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    @staticmethod
    def metadata(tool_name: str) -> dict[str, Any]:
        entry = TOOL_METADATA_REGISTRY.get(tool_name)
        if entry is None:
            raise KeyError(f"unknown tool: {tool_name}")
        return entry

    def check_permission(self, tool_name: str, role: str) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        allowed_by_metadata = role in entry["allowed_roles"]
        allowed_by_registry = get_registry().check_permission(tool_name, role)
        return {
            "allowed": allowed_by_metadata and allowed_by_registry,
            "role": role,
            "allowed_roles": entry["allowed_roles"],
            "permission_level": (get_registry().get(tool_name) or {}).get("permission_level"),
            "reason": (
                "ok"
                if allowed_by_metadata and allowed_by_registry
                else f"role '{role}' not permitted for {tool_name}"
            ),
        }

    def _prune(self, tool_name: str) -> None:
        now = time.time()
        window = self._calls[tool_name]
        while window and now - window[0] > QUOTA_WINDOW_SECONDS:
            window.popleft()

    def check_quota(self, tool_name: str) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        with self._lock:
            self._prune(tool_name)
            used = len(self._calls[tool_name])
        limit = entry["quota_per_hour"]
        return {
            "allowed": used < limit,
            "used": used,
            "limit": limit,
            "window_seconds": QUOTA_WINDOW_SECONDS,
            "resets_in_seconds": (
                round(QUOTA_WINDOW_SECONDS - (time.time() - self._calls[tool_name][0]), 1)
                if self._calls.get(tool_name)
                else 0
            ),
        }

    def check_budget(self, tool_name: str) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        report = self.budget.check(tool_cost_usd=entry["cost"], limit_usd=entry["budget_limit_per_day"])
        report["tool"] = tool_name
        return report

    def check_concurrency(self, tool_name: str) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        with self._lock:
            active = self._active[tool_name]
        return {"allowed": active < entry["max_concurrent"], "active": active, "limit": entry["max_concurrent"]}

    def get_timeout(self, tool_name: str) -> int:
        return int(self.metadata(tool_name)["timeout"])

    def get_retry_policy(self, tool_name: str) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        backoff = dict(entry["retry_backoff"])
        return {"max_attempts": entry["retry_max"], **backoff}

    def record_call(self, tool_name: str, cost_usd: float | None = None) -> dict[str, Any]:
        entry = self.metadata(tool_name)
        cost = entry["cost"] if cost_usd is None else float(cost_usd)
        with self._lock:
            self._prune(tool_name)
            self._calls[tool_name].append(time.time())
            used = len(self._calls[tool_name])
        self.budget.spend(cost, tool_name=tool_name)
        return {
            "tool": tool_name,
            "recorded": True,
            "cost_usd": cost,
            "quota_used": used,
            "quota_limit": entry["quota_per_hour"],
            "spent_today": self.budget.spent_today(),
        }

    def try_acquire(self, tool_name: str) -> bool:
        entry = self.metadata(tool_name)
        with self._lock:
            if self._active[tool_name] >= entry["max_concurrent"]:
                return False
            self._active[tool_name] += 1
            return True

    def release(self, tool_name: str) -> None:
        with self._lock:
            if self._active[tool_name] > 0:
                self._active[tool_name] -= 1

    def check(self, tool_name: str, role: str = "User") -> dict[str, Any]:
        entry = self.metadata(tool_name)
        permission = self.check_permission(tool_name, role)
        quota = self.check_quota(tool_name)
        budget = self.check_budget(tool_name)
        concurrency = self.check_concurrency(tool_name)
        reasons = []
        if not permission["allowed"]:
            reasons.append(permission["reason"])
        if not quota["allowed"]:
            reasons.append(f"quota exhausted: {quota['used']}/{quota['limit']} per hour")
        if not budget["allowed"]:
            reasons.append(f"budget exceeded: {budget['spent_today']}/{budget['limit_per_day']} USD today")
        if not concurrency["allowed"]:
            reasons.append(f"concurrency limit: {concurrency['active']}/{concurrency['limit']}")
        return {
            "tool_name": tool_name,
            "canonical_spec": get_registry().canonical_spec,
            "allowed": not reasons,
            "requires_approval": entry["requires_approval"],
            "risk_level": "HIGH" if entry["requires_approval"] else "LOW",
            "permission": permission,
            "quota": quota,
            "budget": budget,
            "concurrency": concurrency,
            "timeout": entry["timeout"],
            "retry_policy": self.get_retry_policy(tool_name),
            "cost": entry["cost"],
            "reasons": reasons,
        }

    def reset(self) -> None:
        with self._lock:
            self._calls.clear()
            self._active.clear()
        self.budget.reset()


_enforcer: PermissionEnforcer | None = None


def get_enforcer(refresh: bool = False) -> PermissionEnforcer:
    global _enforcer
    if _enforcer is None or refresh:
        _enforcer = PermissionEnforcer()
    return _enforcer


def reset_enforcer() -> None:
    global _enforcer
    _enforcer = None
