from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

from fabric.registry.registry_loader import ROLE_PERMISSIONS, RegistryError, get_registry, validate

VERIFY_PATH = "/phase1/stage1.1/verify"
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

    return router
