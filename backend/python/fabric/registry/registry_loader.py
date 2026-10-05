from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent / "registry.json"

REQUIRED_TOP_FIELDS = ("canonical_spec", "version", "stage", "spec_ref", "dod_ref", "tools")
REQUIRED_TOOL_FIELDS = (
    "tool_name",
    "description",
    "input_schema",
    "output_schema",
    "permission_level",
    "risk_level",
    "cost",
    "timeout",
    "retry_policy",
    "authentication",
    "audit_policy",
)
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class PermissionLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    SEND = "SEND"


class RiskLevel(str, Enum):
    LOW = "LOW"
    HIGH = "HIGH"


ROLE_PERMISSIONS: dict[str, frozenset[PermissionLevel]] = {
    "User": frozenset({PermissionLevel.READ, PermissionLevel.WRITE}),
    "Operator": frozenset({PermissionLevel.READ, PermissionLevel.WRITE, PermissionLevel.EXECUTE}),
    "Admin": frozenset(set(PermissionLevel)),
}


class RegistryError(ValueError):
    """Registry failed validation. `problems` lists every violation found."""


@dataclass(frozen=True)
class ToolRegistry:
    raw: dict[str, Any]
    tools: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def canonical_spec(self) -> str:
        return str(self.raw.get("canonical_spec", ""))

    @property
    def stage(self) -> str:
        return str(self.raw.get("stage", ""))

    @property
    def dod_ref(self) -> str:
        return str(self.raw.get("dod_ref", ""))

    @property
    def spec_ref(self) -> str:
        return str(self.raw.get("spec_ref", ""))

    def __len__(self) -> int:
        return len(self.tools)

    def __contains__(self, tool_name: object) -> bool:
        return tool_name in self.tools

    def get(self, tool_name: str) -> dict[str, Any] | None:
        return self.tools.get(tool_name)

    def specs(self) -> list[dict[str, Any]]:
        return list(self.tools.values())

    def names(self) -> list[str]:
        return list(self.tools)

    def check_permission(self, tool_name: str, role: str) -> bool:
        tool = self.tools.get(tool_name)
        if tool is None:
            return False
        allowed = ROLE_PERMISSIONS.get(role.upper() if role.islower() else role)
        if allowed is None:
            return False
        return PermissionLevel(tool["permission_level"]) in allowed

    def requires_approval(self, tool_name: str) -> bool:
        tool = self.tools.get(tool_name)
        if tool is None:
            return False
        return RiskLevel(tool["risk_level"]) is RiskLevel.HIGH

    def describe(self, tool_name: str, role: str = "User") -> dict[str, Any]:
        tool = self.tools.get(tool_name)
        if tool is None:
            return {
                "tool_name": tool_name,
                "known": False,
                "allowed": False,
                "requires_approval": False,
            }
        return {
            "tool_name": tool_name,
            "known": True,
            "permission_level": tool["permission_level"],
            "risk_level": tool["risk_level"],
            "role": role,
            "allowed": self.check_permission(tool_name, role),
            "requires_approval": self.requires_approval(tool_name),
            "timeout": tool["timeout"],
            "cost": tool["cost"],
            "retry_policy": tool["retry_policy"],
        }


def validate(raw: Any) -> list[str]:
    problems: list[str] = []
    if not isinstance(raw, dict):
        return ["registry root must be a JSON object"]

    for name in REQUIRED_TOP_FIELDS:
        if name not in raw:
            problems.append(f"missing top-level field: {name}")

    tools = raw.get("tools")
    if not isinstance(tools, list):
        problems.append("'tools' must be an array")
        return problems
    if len(tools) < 1:
        problems.append("'tools' must contain at least 1 tool")

    seen: set[str] = set()
    for idx, tool in enumerate(tools):
        where = f"tools[{idx}]"
        if not isinstance(tool, dict):
            problems.append(f"{where}: must be an object")
            continue

        name = tool.get("tool_name")
        if not isinstance(name, str) or not TOOL_NAME_PATTERN.match(name):
            problems.append(f"{where}: tool_name must match 'domain.action' (lowercase)")
            name = None
        elif name in seen:
            problems.append(f"{where}: duplicate tool_name '{name}'")
        else:
            seen.add(name)
            where = name

        for req in REQUIRED_TOOL_FIELDS:
            if req not in tool:
                problems.append(f"{where}: missing field '{req}'")

        level = tool.get("permission_level")
        if level is not None and level not in {p.value for p in PermissionLevel}:
            problems.append(f"{where}: permission_level '{level}' not in {[p.value for p in PermissionLevel]}")

        risk = tool.get("risk_level")
        if risk is not None and risk not in {r.value for r in RiskLevel}:
            problems.append(f"{where}: risk_level '{risk}' not in {[r.value for r in RiskLevel]}")

        timeout = tool.get("timeout")
        if timeout is not None and (not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1 or timeout > 600):
            problems.append(f"{where}: timeout must be an integer between 1 and 600 seconds")

        cost = tool.get("cost")
        if cost is not None:
            if not isinstance(cost, dict) or "currency" not in cost or "per_call" not in cost:
                problems.append(f"{where}: cost must be an object with 'currency' and 'per_call'")
            elif not isinstance(cost["per_call"], (int, float)) or cost["per_call"] < 0:
                problems.append(f"{where}: cost.per_call must be a non-negative number")

        retry = tool.get("retry_policy")
        if retry is not None:
            if not isinstance(retry, dict):
                problems.append(f"{where}: retry_policy must be an object")
            else:
                attempts = retry.get("max_attempts")
                if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1 or attempts > 5:
                    problems.append(f"{where}: retry_policy.max_attempts must be an integer 1..5")
                if "backoff_seconds" in retry and (not isinstance(retry["backoff_seconds"], (int, float)) or retry["backoff_seconds"] < 0):
                    problems.append(f"{where}: retry_policy.backoff_seconds must be >= 0")

        auth = tool.get("authentication")
        if auth is not None and (not isinstance(auth, dict) or not isinstance(auth.get("required"), bool)):
            problems.append(f"{where}: authentication must be an object with boolean 'required'")

        audit = tool.get("audit_policy")
        if audit is not None:
            if not isinstance(audit, dict) or not isinstance(audit.get("log"), bool):
                problems.append(f"{where}: audit_policy must be an object with boolean 'log'")
            else:
                days = audit.get("retain_days")
                if not isinstance(days, int) or isinstance(days, bool) or days < 1:
                    problems.append(f"{where}: audit_policy.retain_days must be an integer >= 1")

        for schema_key in ("input_schema", "output_schema"):
            schema = tool.get(schema_key)
            if schema is None:
                continue
            if not isinstance(schema, dict) or schema.get("type") != "object":
                problems.append(f"{where}: {schema_key} must be an object JSON schema with 'type': 'object'")

    return problems


def load_registry(path: Path | str = REGISTRY_PATH) -> ToolRegistry:
    registry_path = Path(path)
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError(f"registry file not found: {registry_path}") from exc
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry is not valid JSON: {exc}") from exc

    problems = validate(raw)
    if problems:
        raise RegistryError("registry validation failed:\n  - " + "\n  - ".join(problems))

    tools: dict[str, dict[str, Any]] = {}
    for tool in raw["tools"]:
        tools[tool["tool_name"]] = tool
    return ToolRegistry(raw=raw, tools=tools)


_cached: ToolRegistry | None = None


def get_registry(path: Path | str | None = None, refresh: bool = False) -> ToolRegistry:
    global _cached
    if _cached is None or refresh or path is not None:
        registry = load_registry(path or REGISTRY_PATH)
        if path is None:
            _cached = registry
        return registry
    return _cached


def reset_registry() -> None:
    global _cached
    _cached = None


def _self_check(registry: ToolRegistry) -> list[tuple[str, bool, Any, Any]]:
    checks = [
        ("registry loads 8+ tools", len(registry) >= 8, len(registry), ">= 8"),
        ("permission_level validation", all(t["permission_level"] in {p.value for p in PermissionLevel} for t in registry.specs()), "enum", {p.value for p in PermissionLevel}),
        ("risk_level LOW=auto / HIGH=approval", all(t["risk_level"] in {r.value for r in RiskLevel} for t in registry.specs()), "enum", {r.value for r in RiskLevel}),
        ('check_permission("browser.search", "User")', registry.check_permission("browser.search", "User"), registry.check_permission("browser.search", "User"), True),
        ('requires_approval("email.send")', registry.requires_approval("email.send"), registry.requires_approval("email.send"), True),
        ('requires_approval("browser.search")', not registry.requires_approval("browser.search"), registry.requires_approval("browser.search"), False),
    ]
    return checks


def main() -> int:
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass
    registry = get_registry(refresh=True)
    print(f"{len(registry)} tools loaded")
    print(f"canonical_spec: {registry.canonical_spec}")
    print(f"stage: {registry.stage}")
    print(f"tools: {', '.join(registry.names())}")
    print("-" * 60)
    failed = 0
    for label, ok, got, expected in _self_check(registry):
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"[{mark}] {label} (got={got!r}, expected={expected!r})")
    print("-" * 60)
    print("Stage 1.1 self-check:", "COMPLETE" if failed == 0 else f"{failed} FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
