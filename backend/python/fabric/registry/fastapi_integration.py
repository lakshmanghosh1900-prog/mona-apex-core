from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from fabric.registry.budget_manager import BudgetManager
from fabric.registry.permission_enforcer import (
    TOOL_METADATA_REGISTRY,
    get_enforcer,
    validate_metadata,
    validate_registry_consistency,
)
from fabric.registry.registry_loader import ROLE_PERMISSIONS, RegistryError, get_registry, validate

VERIFY_PATH = "/phase1/stage1.1/verify"
VERIFY_12_PATH = "/phase1/stage1.2/verify"
CANONICAL_SPEC_FALLBACK = "MONA — Powered by Apex Core"


def build_tools_payload(mesh_specs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    registry = get_registry()
    return {
        "canonical_spec": registry.canonical_spec,
        "stage": registry.stage,
        "count": len(registry),
        "tools": registry.specs(),
        "mesh": mesh_specs or [],
    }


def build_verify_payload() -> dict[str, Any]:
    registry = get_registry()
    tools_payload = build_tools_payload()
    problems = validate(registry.raw)
    checks = {
        "registry_loads_8plus_tools": len(registry) >= 8,
        "permission_level_validation": not any("permission_level" in p for p in problems),
        "risk_level_detection": not any("risk_level" in p for p in problems),
        "check_permission_browser_search_User": registry.check_permission("browser.search", "User"),
        "requires_approval_email_send": registry.requires_approval("email.send"),
        "not_requires_approval_browser_search": not registry.requires_approval("browser.search"),
        "tools_endpoint_returns_count_and_spec": (
            tools_payload.get("count") == len(registry)
            and tools_payload.get("canonical_spec") == registry.canonical_spec
            and isinstance(tools_payload.get("tools"), list)
        ),
    }
    complete = all(checks.values())
    return {
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "stage": "Phase 1 / Stage 1.1 — Tool Registry",
        "canonical_spec": registry.canonical_spec,
        "dod_ref": registry.dod_ref,
        "tools_loaded": len(registry),
        "tool_names": registry.names(),
        "roles": sorted(ROLE_PERMISSIONS),
        "checks": checks,
    }


def build_stage12_verify_payload() -> dict[str, Any]:
    registry = get_registry()
    enforcer = get_enforcer()
    metadata = TOOL_METADATA_REGISTRY
    problems = validate_metadata() + validate_registry_consistency()

    def _cost_zero() -> bool:
        return all(e["cost"] == 0.0 and e["cost_per_1000"] == 0.0 for e in metadata.values())

    checks = {
        "metadata_has_8_tools": len(metadata) >= 8,
        "timeout_defined": metadata.get("code.run", {}).get("timeout") == 60
        and metadata.get("browser.search", {}).get("timeout") == 30,
        "retry_defined": metadata.get("browser.search", {}).get("retry_max") == 3
        and metadata.get("browser.search", {}).get("retry_backoff", {}).get("strategy") == "exponential",
        "cost_zero_all_tools": _cost_zero(),
        "high_risk_requires_approval": metadata.get("email.send", {}).get("requires_approval") is True
        and registry.requires_approval("email.send"),
        "low_risk_no_approval": metadata.get("browser.search", {}).get("requires_approval") is False
        and not registry.requires_approval("browser.search"),
        "quota_defined": metadata.get("browser.search", {}).get("quota_per_hour") == 100,
        "budget_manager_zero_cost": BudgetManager().zero_cost and enforcer.budget.zero_cost,
    }
    complete = all(checks.values()) and not problems
    return {
        "stage": "Phase 1 Stage 1.2 - Tool Permission Metadata",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": registry.canonical_spec,
        "dod_ref": registry.dod_ref,
        "all_checks": complete,
        "checks": checks,
        "problems": problems,
        "tools_with_metadata": len(metadata),
        "enforcement": {
            "email.send": enforcer.check("email.send", role="User"),
            "browser.search": enforcer.check("browser.search", role="User"),
        },
    }


def build_router(mesh_specs: Callable[[], list[dict[str, Any]]] | None = None) -> APIRouter:
    router = APIRouter()
    mesh_source = mesh_specs or (lambda: [])

    @router.get("/tools")
    async def list_tools() -> dict[str, Any]:
        try:
            return build_tools_payload(mesh_source())
        except RegistryError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/tools/check/{tool_name}")
    async def check_tool(
        tool_name: str,
        role: str = Query(default="User", description="RBAC role: User | Operator | Admin"),
    ) -> dict[str, Any]:
        registry = get_registry()
        if tool_name not in registry:
            raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")
        return registry.describe(tool_name, role=role)

    @router.get("/tools/{tool_name}/metadata")
    async def tool_metadata(tool_name: str) -> dict[str, Any]:
        enforcer = get_enforcer()
        try:
            entry = enforcer.metadata(tool_name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
        return {
            "canonical_spec": get_registry().canonical_spec,
            "stage": "Phase 1 Stage 1.2 - Tool Permission Metadata",
            "tool_name": tool_name,
            "metadata": entry,
            "retry_policy": enforcer.get_retry_policy(tool_name),
            "timeout": enforcer.get_timeout(tool_name),
        }

    @router.get("/tools/{tool_name}/check-detailed")
    async def check_tool_detailed(
        tool_name: str,
        role: str = Query(default="User", description="RBAC role: User | Operator | Admin | Owner"),
    ) -> dict[str, Any]:
        try:
            return get_enforcer().check(tool_name, role=role)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc

    @router.get("/tools/{tool_name}")
    async def get_tool(tool_name: str) -> dict[str, Any]:
        registry = get_registry()
        tool = registry.get(tool_name)
        if tool is None:
            raise HTTPException(status_code=404, detail=f"unknown tool: {tool_name}")
        return {
            "canonical_spec": registry.canonical_spec,
            "tool": tool,
            "requires_approval": registry.requires_approval(tool_name),
            "roles_allowed": [role for role in sorted(ROLE_PERMISSIONS) if registry.check_permission(tool_name, role)],
        }

    @router.get(VERIFY_PATH)
    async def verify_stage_1_1() -> dict[str, Any]:
        try:
            return build_verify_payload()
        except RegistryError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get(VERIFY_12_PATH)
    async def verify_stage_1_2() -> dict[str, Any]:
        try:
            return build_stage12_verify_payload()
        except RegistryError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
