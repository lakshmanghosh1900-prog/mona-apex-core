from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from fabric.registry.browser_tool import (
    BrowserPermissionError,
    get_browser_tool,
    playwright_available,
)
from fabric.registry.permission_enforcer import TOOL_METADATA_REGISTRY
from fabric.registry.registry_loader import get_registry
from fabric.registry.stealth_config import CANONICAL_SPEC, stealth_summary

VERIFY_13_PATH = "/phase1/stage1.3/verify"


EVIDENCE_FIELDS = ("action", "url", "title", "timestamp", "source")


def build_stage13_verify_payload() -> dict[str, Any]:
    registry = get_registry()
    tool = get_browser_tool()
    stealth = stealth_summary()
    checks = {
        "browser_tool_exists": tool is not None,
        "singleton": get_browser_tool() is tool,
        "search_and_open_in_metadata": all(
            name in TOOL_METADATA_REGISTRY for name in ("browser.search", "browser.open")
        ),
        "evidence_tracking_fields": callable(getattr(tool, "_record", None))
        and callable(getattr(tool, "evidence_log", None))
        and set(EVIDENCE_FIELDS) == {"action", "url", "title", "timestamp", "source"},
        "stealth_config_present": bool(stealth["hides_webdriver"]) and bool(stealth["launch_args"]),
        "playwright_optional_fallback": not tool.use_playwright or playwright_available(),
        "zero_cost_stack": all(
            meta["cost"] == 0.0 for meta in TOOL_METADATA_REGISTRY.values() if "cost" in meta
        ),
    }
    complete = all(checks.values())
    return {
        "stage": "Phase 1 Stage 1.3 - Browser Tool",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": CANONICAL_SPEC,
        "all_checks": complete,
        "checks": checks,
        "playwright_installed": playwright_available(),
        "stealth": stealth_summary(),
        "evidence_entries": len(tool.evidence),
    }


def build_browser_router() -> APIRouter:
    router = APIRouter()

    @router.get(VERIFY_13_PATH)
    async def verify_stage_1_3() -> dict[str, Any]:
        return build_stage13_verify_payload()

    @router.get("/tools/browser.search/execute")
    async def execute_search(
        query: str = Query(..., description="Search query"),
        limit: int = Query(default=5, ge=1, le=20),
        role: str = Query(default="User"),
    ) -> dict[str, Any]:
        try:
            return await get_browser_tool().search(query=query, limit=limit, role=role)
        except BrowserPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @router.get("/tools/browser.open/execute")
    async def execute_open(
        url: str = Query(..., description="Absolute http(s) URL"),
        role: str = Query(default="User"),
        max_chars: int = Query(default=8000, ge=100, le=50000),
    ) -> dict[str, Any]:
        try:
            return await get_browser_tool().open(url=url, role=role, max_chars=max_chars)
        except BrowserPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/tools/browser.extract/execute")
    async def execute_extract(
        url: str = Query(..., description="Absolute http(s) URL"),
        selector: str | None = Query(default=None),
        role: str = Query(default="User"),
    ) -> dict[str, Any]:
        try:
            return await get_browser_tool().extract(url=url, selector=selector, role=role)
        except BrowserPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return router
