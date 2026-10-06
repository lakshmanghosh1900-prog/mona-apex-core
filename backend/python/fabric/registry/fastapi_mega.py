from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from fabric.registry.api_tool import ApiTool, demo_config
from fabric.registry.browser_tool import BrowserTool
from fabric.registry.budget_manager import BudgetManager
from fabric.registry.fastapi_browser import build_stage13_verify_payload
from fabric.registry.fastapi_integration import build_stage12_verify_payload, build_verify_payload
from fabric.registry.file_tool import FileTool, SandboxPathError
from fabric.registry.limits import LimitsEnforcer
from fabric.registry.mesh_tester import ToolMeshTester
from fabric.registry.permission_enforcer import TOOL_METADATA_REGISTRY, PermissionEnforcer
from fabric.registry.research_engine import ResearchEngine
from fabric.registry.registry_loader import get_registry
from fabric.registry.sandbox import SecureSandbox
from fabric.registry.worker import ExecutionWorker, TaskStatus
from fabric.registry.state_root import get_state_root, state_dir

STAGE_VERIFY_PATHS = {
    "1.4": "/phase1/stage1.4/verify",
    "1.5": "/phase1/stage1.5/verify",
    "1.6": "/phase1/stage1.6/verify",
    "1.7": "/phase1/stage1.7/verify",
    "1.8": "/phase1/stage1.8/verify",
    "1.9": "/phase1/stage1.9/verify",
    "1.10": "/phase1/stage1.10/verify",
}
MEGA_VERIFY_PATH = "/phase1/mega/verify"

EVIDENCE_FIELDS = ("url", "title", "snippet", "source", "confidence", "timestamp")
STAGE_TITLES = {
    "1.1": "Tool Registry",
    "1.2": "Tool Permission Metadata",
    "1.3": "Browser Tool",
    "1.4": "Research Engine",
    "1.5": "File Tool",
    "1.6": "API Tool Framework",
    "1.7": "Secure Sandbox",
    "1.8": "Execution Worker",
    "1.9": "Timeout / Retry / Cost Limits",
    "1.10": "Tool Mesh Testing",
}
ALL_STAGES = tuple(STAGE_TITLES)


def _header(stage: str, checks: dict[str, bool], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = get_registry()
    complete = all(checks.values())
    payload = {
        "stage": f"Phase 1 Stage {stage} — {STAGE_TITLES[stage]}",
        "status": "✅ COMPLETE" if complete else "❌ INCOMPLETE",
        "canonical_spec": registry.canonical_spec,
        "dod_ref": registry.dod_ref,
        "all_checks": complete,
        "checks": checks,
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "cost_usd": 0.0,
        "stack": "zero-cost",
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def _is_complete(payload: dict[str, Any]) -> bool:
    if "all_checks" in payload:
        return bool(payload["all_checks"])
    checks = payload.get("checks", {})
    return bool(checks) and all(checks.values())


# ---------------- Stage 1.4 ----------------
async def build_stage14_verify_payload() -> dict[str, Any]:
    """Deterministic: the mock-evidence path, so verification never depends on
    the network. The live DuckDuckGo path is exercised by Stage 1.3's search."""
    engine = ResearchEngine(browser=BrowserTool(offline=True))
    report = await engine.research(query="mona apex core agent orchestration", sources=3)
    evidence = report["evidence"]
    checks = {
        "answer_generated": bool(report["answer"]),
        "sources_used_at_least_1": report["sources_used"] >= 1,
        "evidence_present": len(evidence) >= 1,
        "evidence_fields_complete": all(
            all(field in item for field in EVIDENCE_FIELDS) for item in evidence
        ),
        "cross_check_evaluated": isinstance(report["cross_check_pass"], bool)
        and "cross_check" in report,
        "confidence_scored": 0.0 < float(report["confidence"]) <= 1.0,
        "zero_cost": report["cost_usd"] == 0.0,
    }
    return _header(
        "1.4",
        checks,
        {
            "query": report["query"],
            "sources_used": report["sources_used"],
            "cross_check_pass": report["cross_check_pass"],
            "cross_check": report["cross_check"],
            "confidence": report["confidence"],
            "collection_mode": report["collection_mode"],
            "evidence": evidence,
        },
    )


# ---------------- Stage 1.5 ----------------
def build_stage15_verify_payload() -> dict[str, Any]:
    files = FileTool()
    rel = f"stage15/{int(time.time() * 1000)}.txt"
    content = "mona stage 1.5 sandbox verification marker"
    written = files.write(rel, content)
    read = files.read(rel)
    found = files.search("stage 1.5 sandbox")
    moved = files.organize("move", rel, rel.replace(".txt", ".moved.txt"))
    listed = files.organize("list", "stage15")

    traversal_blocked = False
    traversal_error = ""
    for attempt in ("../../etc/passwd", "/etc/passwd", "..\\..\\windows\\system32\\config\\sam"):
        try:
            files.read(attempt)
        except SandboxPathError as exc:
            traversal_blocked = True
            traversal_error = str(exc)
            break
        except Exception as exc:  # noqa: BLE001
            traversal_blocked = False
            traversal_error = f"{type(exc).__name__}: {exc}"
            break

    checks = {
        "write_success": bool(written.get("ok")),
        "read_roundtrip": bool(read.get("ok")) and read.get("content", "").startswith(content),
        "search_found_marker": found.get("match_count", 0) >= 1,
        "organize_move": bool(moved.get("ok")),
        "organize_list": bool(listed.get("ok")),
        "traversal_blocked": traversal_blocked,
        "writes_confined_to_sandbox": files.stats()["contained"],
    }
    files.organize("delete", "stage15")
    return _header(
        "1.5",
        checks,
        {
            "sandbox_root": str(files.root),
            "canonical_root": str(get_state_root()),
            "stats": files.stats(),
            "traversal_error": traversal_error,
        },
    )


# ---------------- Stage 1.6 ----------------
async def build_stage16_verify_payload() -> dict[str, Any]:
    api = ApiTool()
    name = "mona.verify"
    registered = api.register_api(name, demo_config(name, rate_limit_per_minute=2))
    listed = api.list_apis()
    first = await api.call_api(name, "status", {})
    second = await api.call_api(name, "echo", {"query": "mona"})
    third = await api.call_api(name, "status", {})

    checks = {
        "register_api": registered["name"] == name,
        "list_apis_contains_api": any(item["name"] == name for item in listed),
        "call_api_ok": bool(first.get("ok")) and bool(first.get("mocked")),
        "rate_limit_allows_under_cap": bool(second.get("ok")) and not second.get("rate_limited"),
        "rate_limit_blocks_over_cap": bool(third.get("rate_limited")) and not third.get("ok"),
        "zero_cost": first.get("cost_usd") == 0.0 and registered["cost_usd"] == 0.0,
        "no_secret_in_code": registered["auth_env"] == "MONA_DEMO_API_KEY"
        and not registered["auth_configured"],
    }
    return _header(
        "1.6",
        checks,
        {
            "apis": [item["name"] for item in listed],
            "stats": api.stats(),
            "sample_response": first.get("data"),
            "rate_limit_per_minute": registered["rate_limit_per_minute"],
            "live_enabled": first.get("live_enabled"),
        },
    )


# ---------------- Stage 1.7 ----------------
def build_stage17_verify_payload() -> dict[str, Any]:
    sandbox = SecureSandbox()
    run = sandbox.run_python("print('mona sandbox ' + str(6 * 7))")
    isolation = sandbox.verify_isolation()

    checks = {
        "run_python_success": bool(run.get("ok")) and run.get("stdout", "").strip().endswith("42"),
        "execution_count_tracked": sandbox.execution_count >= 2 and run.get("execution_count", 0) >= 1,
        "isolation_ok": bool(isolation.get("isolation_ok")),
        "timeout_kills_process": bool(isolation["checks"].get("timeout_kills_process")),
        "env_scrubbed": bool(isolation["checks"].get("env_scrubbed")),
        "cwd_inside_sandbox": bool(isolation["checks"].get("cwd_inside_sandbox")),
    }
    return _header(
        "1.7",
        checks,
        {
            "run": {key: run.get(key) for key in ("stdout", "returncode", "timed_out", "duration_ms", "timeout_seconds")},
            "isolation": isolation,
            "stats": sandbox.stats(),
        },
    )


# ---------------- Stage 1.8 ----------------
async def build_stage18_verify_payload() -> dict[str, Any]:
    worker = ExecutionWorker(
        files=FileTool(),
        sandbox=SecureSandbox(),
        research=ResearchEngine(browser=BrowserTool(offline=True)),
        limits=LimitsEnforcer(enforcer=PermissionEnforcer(), backoff_scale=0.0),
    )
    rel = "stage18/task.txt"
    queued = [
        worker.enqueue("browser.search", {"query": "fastapi", "limit": 2}, role="User"),
        worker.enqueue("files.write", {"path": rel, "content": "mona stage 1.8 worker payload"}, role="User"),
        worker.enqueue("files.read", {"path": rel}, role="User"),
        worker.enqueue("code.run", {"code": "print('worker')"}, role="Operator"),
        worker.enqueue("research.search", {"query": "agent tools", "sources": 2}, role="User"),
    ]
    processed = await worker.process_queue()
    stats = worker.get_stats()

    checks = {
        "tasks_enqueued": len(queued) == 5,
        "all_routes_execute": all(task.status is TaskStatus.COMPLETE for task in processed),
        "queue_cleared": bool(stats["queue_cleared"]) and stats["queued"] == 0,
        "stats_tracked": stats["total_enqueued"] == 5 and stats["completed"] == 5,
        "no_failed_tasks": stats["failed"] == 0 and not [t.error for t in processed if t.error],
        "required_routes_present": {"browser.search", "files.read", "files.write", "code.run", "research.search"}
        <= set(stats["routes"]),
    }
    worker.files.organize("delete", "stage18")
    return _header(
        "1.8",
        checks,
        {
            "routes": stats["routes"],
            "stats": stats,
            "tasks": [task.as_dict() for task in processed],
        },
    )


# ---------------- Stage 1.9 ----------------
async def build_stage19_verify_payload() -> dict[str, Any]:
    fresh = PermissionEnforcer(budget=BudgetManager())
    limits = LimitsEnforcer(enforcer=fresh, backoff_scale=0.0)

    async def too_slow() -> None:
        await asyncio.sleep(5)

    timeout_call = await limits.execute_with_limits(
        "code.run", too_slow, role="Operator", timeout_seconds=1
    )

    attempts = {"count": 0}

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient transport failure")
        return "recovered"

    retry_call = await limits.execute_with_limits("files.read", flaky)

    quota_tool = "research.search"
    quota_limit = fresh.metadata(quota_tool)["quota_per_hour"]
    for _ in range(quota_limit):
        fresh.record_call(quota_tool)
    quota_report = fresh.check_quota(quota_tool)
    quota_denied = await limits.execute_with_limits(quota_tool, flaky, role="User")

    budget = BudgetManager(daily_limit_usd=0.0)
    zero_cost_ok = budget.check(tool_cost_usd=0.0, limit_usd=0.0)["allowed"]
    paid_blocked = budget.check(tool_cost_usd=1.0, limit_usd=0.0)

    checks = {
        "timeout_enforced": bool(timeout_call["timeout_enforced"])
        and not timeout_call["ok"]
        and timeout_call["attempts"] == 1,
        "timeout_cannot_exceed_declared": timeout_call["declared_timeout_seconds"] == 60.0,
        "retry_with_backoff": bool(retry_call["ok"]) and retry_call["attempts"] == 2 and retry_call["retried"],
        "quota_enforced": not quota_report["allowed"] and quota_report["used"] == quota_limit,
        "quota_blocks_call": not quota_denied["ok"] and quota_denied["blocked_by"] == "gate",
        "budget_zero_cost_allowed": bool(zero_cost_ok) and budget.zero_cost,
        "budget_blocks_paid_spend": not paid_blocked["allowed"],
        "cost_zero_all_tools": all(entry["cost"] == 0.0 for entry in TOOL_METADATA_REGISTRY.values()),
    }
    return _header(
        "1.9",
        checks,
        {
            "timeout_call": timeout_call,
            "retry_call": retry_call,
            "quota": quota_report,
            "quota_blocked_call": {"ok": quota_denied["ok"], "error": quota_denied["error"]},
            "budget": {"zero_cost_allowed": zero_cost_ok, "paid_blocked": paid_blocked},
            "summary": limits.limits_summary(),
        },
    )


# ---------------- Stage 1.10 ----------------
async def build_stage110_verify_payload() -> dict[str, Any]:
    worker = ExecutionWorker(
        files=FileTool(),
        sandbox=SecureSandbox(),
        research=ResearchEngine(browser=BrowserTool(offline=True)),
        limits=LimitsEnforcer(enforcer=PermissionEnforcer(), backoff_scale=0.0),
    )
    tester = ToolMeshTester(worker=worker)
    report = await tester.test_e2e_research_file_sandbox()

    checks = dict(report["checks"])
    checks["six_checks_present"] = len(report["checks"]) == 6
    checks["stages_compose"] = report["sources_used"] >= 1 and bool(report["report_path"])
    return _header(
        "1.10",
        checks,
        {
            "e2e": report,
            "failed_checks": report["failed_checks"],
        },
    )


# ---------------- Mega ----------------
async def build_mega_verify_payload() -> dict[str, Any]:
    started = time.perf_counter()
    registry = get_registry()

    builders: dict[str, Any] = {
        "1.1": lambda: build_verify_payload(),
        "1.2": lambda: build_stage12_verify_payload(),
        "1.3": lambda: build_stage13_verify_payload(),
        "1.4": build_stage14_verify_payload,
        "1.5": lambda: build_stage15_verify_payload(),
        "1.6": build_stage16_verify_payload,
        "1.7": lambda: build_stage17_verify_payload(),
        "1.8": build_stage18_verify_payload,
        "1.9": build_stage19_verify_payload,
        "1.10": build_stage110_verify_payload,
    }

    stages: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    for stage in ALL_STAGES:
        try:
            # Stages 1.1-1.3 and the sync stages return dicts; async ones await.
            result = builders[stage]()
            payload = await result if inspect.isawaitable(result) else result
            passed = _is_complete(payload)
            # Normalise: 1.1-1.3 predate `all_checks`, mega callers get one shape.
            payload["all_checks"] = passed
            payload.setdefault("failed_checks", [n for n, ok in payload.get("checks", {}).items() if not ok])
        except Exception as exc:  # noqa: BLE001 - a broken stage must not 500 the mega report
            payload = {"stage": stage, "status": "❌ INCOMPLETE", "error": f"{type(exc).__name__}: {exc}"}
            passed = False
        stages.append(
            {
                "stage": stage,
                "title": STAGE_TITLES[stage],
                "status": payload.get("status", "❌ INCOMPLETE"),
                "passed": passed,
                "failed_checks": payload.get("failed_checks", []),
            }
        )
        details[f"stage{stage}"] = payload

    passed_count = sum(1 for stage in stages if stage["passed"])
    all_ok = passed_count == len(ALL_STAGES)
    return {
        "status": "✅ PHASE 1 COMPLETE" if all_ok else "❌ INCOMPLETE",
        "canonical_spec": registry.canonical_spec,
        "dod_ref": registry.dod_ref,
        "all_checks": all_ok,
        "passed": passed_count,
        "failed": len(ALL_STAGES) - passed_count,
        "total_stages": len(ALL_STAGES),
        "stages": stages,
        "failed_stages": [s["stage"] for s in stages if not s["passed"]],
        "tools_registered": len(registry),
        "tool_names": registry.names(),
        "stack": "zero-cost",
        "cost_usd": 0.0,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "details": details,
    }


def build_mega_router() -> APIRouter:
    router = APIRouter()

    @router.get(STAGE_VERIFY_PATHS["1.4"])
    async def verify_stage_1_4() -> dict[str, Any]:
        return await build_stage14_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.5"])
    async def verify_stage_1_5() -> dict[str, Any]:
        return build_stage15_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.6"])
    async def verify_stage_1_6() -> dict[str, Any]:
        return await build_stage16_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.7"])
    async def verify_stage_1_7() -> dict[str, Any]:
        return build_stage17_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.8"])
    async def verify_stage_1_8() -> dict[str, Any]:
        return await build_stage18_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.9"])
    async def verify_stage_1_9() -> dict[str, Any]:
        return await build_stage19_verify_payload()

    @router.get(STAGE_VERIFY_PATHS["1.10"])
    async def verify_stage_1_10() -> dict[str, Any]:
        return await build_stage110_verify_payload()

    @router.get(MEGA_VERIFY_PATH)
    async def verify_phase1() -> dict[str, Any]:
        return await build_mega_verify_payload()

    return router