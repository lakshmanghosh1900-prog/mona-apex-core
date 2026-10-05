from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar, Deque

from fabric.registry.registry_loader import ToolRegistry, get_registry

_AUDIT_LIMIT = 500
_audit_log: Deque[dict[str, Any]] = deque(maxlen=_AUDIT_LIMIT)


def audit_records() -> list[dict[str, Any]]:
    return list(_audit_log)


def clear_audit() -> None:
    _audit_log.clear()


def validate_arguments(schema: dict[str, Any], arguments: dict[str, Any], prefix: str = "") -> list[str]:
    errors: list[str] = []
    if not isinstance(arguments, dict):
        return [f"{prefix or 'arguments'}: must be an object"]

    for key in schema.get("required", []):
        if key not in arguments:
            errors.append(f"{prefix}{key}: required property missing")

    for key, value in arguments.items():
        prop = schema.get("properties", {}).get(key)
        if prop is None:
            continue
        errors.extend(_validate_value(prop, value, f"{prefix}{key}"))
    return errors


def _validate_value(prop: dict[str, Any], value: Any, path: str) -> list[str]:
    errors: list[str] = []
    expected = prop.get("type")
    type_ok = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }.get(expected, lambda v: True)

    if not type_ok(value):
        errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
        return errors

    if expected == "string":
        if "minLength" in prop and len(value) < prop["minLength"]:
            errors.append(f"{path}: shorter than minLength {prop['minLength']}")
        if "maxLength" in prop and len(value) > prop["maxLength"]:
            errors.append(f"{path}: longer than maxLength {prop['maxLength']}")
        pattern = prop.get("pattern")
        if pattern:
            import re

            if not re.search(pattern, value):
                errors.append(f"{path}: does not match pattern {pattern}")
    elif expected in {"integer", "number"}:
        if "minimum" in prop and value < prop["minimum"]:
            errors.append(f"{path}: below minimum {prop['minimum']}")
        if "maximum" in prop and value > prop["maximum"]:
            errors.append(f"{path}: above maximum {prop['maximum']}")
    elif expected == "array":
        if "items" in prop:
            for idx, item in enumerate(value):
                errors.extend(_validate_value(prop["items"], item, f"{path}[{idx}]"))
        if "maxItems" in prop and len(value) > prop["maxItems"]:
            errors.append(f"{path}: more than maxItems {prop['maxItems']}")

    if "enum" in prop and value not in prop["enum"]:
        errors.append(f"{path}: {value!r} not in {prop['enum']}")
    return errors


@dataclass
class ToolResult:
    tool: str
    ok: bool
    result: Any = None
    error: str | None = None
    attempts: int = 1
    duration_ms: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
            "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 2),
            "evidence": self.evidence,
        }


class BaseTool(ABC):
    """Contract every Mona tool implements.

    Stage 1.1 ships metadata + validation + timeout/retry/audit plumbing.
    Subclasses override `run()` (Stage 1.2+ implements real execution).
    """

    tool_name: ClassVar[str] = ""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        if not self.tool_name:
            raise ValueError(f"{type(self).__name__} must declare tool_name")
        if self.tool_name not in self.registry:
            raise KeyError(f"tool '{self.tool_name}' not present in registry")

    @property
    def spec(self) -> dict[str, Any]:
        return self.registry.get(self.tool_name) or {}

    @property
    def permission_level(self) -> str:
        return self.spec.get("permission_level", "READ")

    @property
    def risk_level(self) -> str:
        return self.spec.get("risk_level", "LOW")

    @property
    def mutating(self) -> bool:
        return self.risk_level == "HIGH"

    def check_permission(self, role: str) -> bool:
        return self.registry.check_permission(self.tool_name, role)

    def requires_approval(self) -> bool:
        return self.registry.requires_approval(self.tool_name)

    async def execute(self, role: str = "User", **arguments: Any) -> ToolResult:
        started = time.perf_counter()
        errors = validate_arguments(self.spec.get("input_schema", {}), arguments)
        if errors:
            return self._finish(ToolResult(self.tool_name, False, error="; ".join(errors)), started, role, arguments)

        if not self.check_permission(role):
            return self._finish(
                ToolResult(self.tool_name, False, error=f"permission denied: role '{role}' lacks {self.permission_level}"),
                started,
                role,
                arguments,
            )

        retry = self.spec.get("retry_policy", {})
        max_attempts = int(retry.get("max_attempts", 1))
        backoff = float(retry.get("backoff_seconds", 0.0))
        multiplier = float(retry.get("backoff_multiplier", 1.0))
        timeout = float(self.spec.get("timeout", 30))

        last_error = "tool did not run"
        for attempt in range(1, max_attempts + 1):
            try:
                value = await asyncio.wait_for(self.run(**arguments), timeout=timeout)
                if isinstance(value, ToolResult):
                    value.attempts = attempt
                    return self._finish(value, started, role, arguments)
                return self._finish(ToolResult(self.tool_name, True, result=value, attempts=attempt), started, role, arguments)
            except asyncio.TimeoutError:
                last_error = f"timeout after {timeout}s"
            except NotImplementedError:
                return self._finish(
                    ToolResult(self.tool_name, False, error=f"tool '{self.tool_name}' not implemented yet (Stage 1.2+)"),
                    started,
                    role,
                    arguments,
                )
            except Exception as exc:  # noqa: BLE001 - tool boundary converts everything to ToolResult
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < max_attempts and backoff > 0:
                await asyncio.sleep(backoff)
                backoff *= multiplier

        return self._finish(ToolResult(self.tool_name, False, error=last_error, attempts=max_attempts), started, role, arguments)

    @abstractmethod
    async def run(self, **arguments: Any) -> Any:
        raise NotImplementedError

    def _finish(self, result: ToolResult, started: float, role: str, arguments: dict[str, Any]) -> ToolResult:
        result.duration_ms = (time.perf_counter() - started) * 1000
        _audit_log.append(
            {
                "tool": self.tool_name,
                "ok": result.ok,
                "role": role,
                "permission_level": self.permission_level,
                "risk_level": self.risk_level,
                "approval_required": self.requires_approval(),
                "attempts": result.attempts,
                "duration_ms": round(result.duration_ms, 2),
                "error": result.error,
                "args_keys": sorted(arguments),
            }
        )
        return result
