from __future__ import annotations

import asyncio
from typing import Any, Awaitable

import pytest

from fabric.registry.api_tool import ApiNotRegistered, ApiTool, demo_config
from fabric.registry.browser_tool import BrowserTool
from fabric.registry.budget_manager import BudgetManager
from fabric.registry.fastapi_mega import (
    ALL_STAGES,
    MEGA_VERIFY_PATH,
    STAGE_VERIFY_PATHS,
    build_mega_router,
    build_mega_verify_payload,
    build_stage14_verify_payload,
    build_stage15_verify_payload,
    build_stage16_verify_payload,
    build_stage17_verify_payload,
    build_stage18_verify_payload,
    build_stage19_verify_payload,
    build_stage110_verify_payload,
)
from fabric.registry.file_tool import FileTool, SandboxPathError
from fabric.registry.limits import LimitsEnforcer, compute_backoff
from fabric.registry.mesh_tester import ToolMeshTester
from fabric.registry.permission_enforcer import PermissionEnforcer
from fabric.registry.research_engine import Evidence, ResearchEngine, ResearchPermissionError
from fabric.registry.sandbox import SandboxPermissionError, SecureSandbox
from fabric.registry.worker import ExecutionWorker, TaskStatus, UnsupportedTool
from fabric.sandbox.docker_sandbox import SecureSandbox as DockerSandboxMirror


def run(coro: Awaitable[Any]) -> Any:
    return asyncio.run(coro)


def offline_engine() -> ResearchEngine:
    """Playwright-free research engine backed by deterministic mock evidence."""
    return ResearchEngine(browser=BrowserTool(offline=True))


def build_worker() -> ExecutionWorker:
    return ExecutionWorker(
        files=FileTool(),
        sandbox=SecureSandbox(),
        research=offline_engine(),
        limits=LimitsEnforcer(enforcer=PermissionEnforcer(), backoff_scale=0.0),
    )


def _cleanup(files: FileTool, *paths: str) -> None:
    for path in paths:
        if (files.root / path).exists():
            files.organize("delete", path)


@pytest.fixture()
def worker() -> ExecutionWorker:
    instance = build_worker()
    yield instance
    _cleanup(instance.files, "test_mega", "mesh")


def test_stage1_4_research_engine():
    engine = offline_engine()
    report = run(engine.research("mona apex core orchestration", sources=3))

    assert report["tool"] == "research.search"
    assert report["sources_used"] >= 1
    assert len(report["evidence"]) >= 1
    assert report["answer"]
    assert isinstance(report["cross_check_pass"], bool)
    assert report["cross_check_pass"] is True
    assert 0.0 < report["confidence"] <= 1.0
    assert report["cost_usd"] == 0.0

    for item in report["evidence"]:
        assert item["url"].startswith("http")
        assert item["title"] and item["snippet"] and item["source"] and item["timestamp"]
        assert 0.0 < float(item["confidence"]) <= 1.0

    with pytest.raises(ResearchPermissionError):
        run(engine.research("mona", sources=1, role="Guest"))

    evidence = Evidence(
        url="https://example.com/a", title="A", snippet="b", source="test", confidence=0.5, timestamp="now"
    )
    assert evidence.domain == "example.com"
    assert set(evidence.as_dict()) >= {
        "rank", "url", "domain", "title", "snippet", "source", "confidence", "timestamp",
    }

    payload = run(build_stage14_verify_payload())
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert payload["sources_used"] >= 1
    assert payload["evidence"]
    assert all(payload["checks"].values()), payload["checks"]


def test_stage1_5_file_tool():
    files = FileTool()
    assert files.root.exists()
    _cleanup(files, "test_mega")

    written = files.write("test_mega/hello.txt", "mona stage 1.5 verification marker")
    assert written["ok"] is True
    assert written["path"] == "test_mega/hello.txt"

    read = files.read("test_mega/hello.txt")
    assert read["ok"] is True
    assert read["content"] == "mona stage 1.5 verification marker"

    found = files.search("verification marker")
    assert found["ok"] is True
    assert found["match_count"] >= 1
    assert any(match["path"] == "test_mega/hello.txt" for match in found["matches"])

    moved = files.organize("move", "test_mega/hello.txt", "test_mega/moved/hello.txt")
    assert moved["ok"] is True
    assert files.read("test_mega/moved/hello.txt")["ok"] is True
    assert files.organize("list", "test_mega")["count"] >= 1

    for escape in ("../../etc/passwd", "/etc/passwd", "..\\..\\windows\\system32"):
        with pytest.raises(SandboxPathError):
            files.read(escape)

    assert files.stats()["contained"] is True
    _cleanup(files, "test_mega")

    payload = build_stage15_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]


def test_stage1_6_api_tool():
    api = ApiTool()
    assert api.list_apis() == []

    registered = api.register_api("mona.test", demo_config("mona.test", rate_limit_per_minute=2))
    assert registered["name"] == "mona.test"
    assert registered["rate_limit_per_minute"] == 2
    assert [item["name"] for item in api.list_apis()] == ["mona.test"]

    first = run(api.call_api("mona.test", "status", {}))
    assert first["ok"] is True
    assert first["mocked"] is True
    assert first["live_enabled"] is False
    assert first["cost_usd"] == 0.0
    assert first["data"]["stack"] == "zero-cost"

    second = run(api.call_api("mona.test", "echo", {"query": "mona"}))
    assert second["ok"] is True
    assert second["rate_limited"] is False

    third = run(api.call_api("mona.test", "status", {}))
    assert third["ok"] is False
    assert third["rate_limited"] is True
    assert "rate limit exceeded" in third["error"]

    with pytest.raises(ApiNotRegistered):
        run(api.call_api("not.registered", "status", {}))
    assert api.unregister_api("mona.test") is True

    payload = run(build_stage16_verify_payload())
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]


def test_stage1_7_sandbox():
    sandbox = SecureSandbox()
    assert DockerSandboxMirror is SecureSandbox

    result = sandbox.run_python("print('mona ' + str(6 * 7))")
    assert result["ok"] is True
    assert result["stdout"].strip().endswith("42")
    assert result["returncode"] == 0
    assert result["timed_out"] is False
    assert result["execution_count"] == 1
    assert result["isolated"] is True
    assert result["env_scrubbed"] is True

    slow = sandbox.run_python("import time; time.sleep(30)", timeout=1)
    assert slow["timed_out"] is True
    assert slow["ok"] is False
    assert sandbox.execution_count == 2
    assert sandbox.timeout_count == 1

    boom = sandbox.run_python("raise ValueError('boom')")
    assert boom["ok"] is False
    assert "ValueError" in boom["stderr"]

    with pytest.raises(SandboxPermissionError):
        sandbox.run_python("print(1)", role="User")

    isolation = sandbox.verify_isolation()
    assert isolation["isolation_ok"] is True
    assert all(isolation["checks"].values()), isolation["checks"]
    assert isolation["failed_checks"] == []

    payload = build_stage17_verify_payload()
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]


def test_stage1_8_worker():
    worker = build_worker()
    _cleanup(worker.files, "test_mega")

    with pytest.raises(UnsupportedTool):
        worker.enqueue("nope.nope", {})

    tasks = [
        worker.enqueue("browser.search", {"query": "fastapi", "limit": 2}, role="User"),
        worker.enqueue("files.write", {"path": "test_mega/w.txt", "content": "mona worker"}, role="User"),
        worker.enqueue("files.read", {"path": "test_mega/w.txt"}, role="User"),
        worker.enqueue("code.run", {"code": "print('worker')"}, role="Operator"),
        worker.enqueue("research.search", {"query": "agent tools", "sources": 2}, role="User"),
    ]
    assert all(task.status is TaskStatus.PENDING for task in tasks)
    assert worker.get_stats()["queued"] == 5

    processed = run(worker.process_queue())

    assert len(processed) == 5
    assert all(task.status is TaskStatus.COMPLETE for task in processed), [task.error for task in processed]
    stats = worker.get_stats()
    assert stats["queue_cleared"] is True
    assert stats["queued"] == 0
    assert stats["total_enqueued"] == 5
    assert stats["completed"] == 5
    assert stats["failed"] == 0
    assert set(stats["by_status"]) == {status.value for status in TaskStatus}
    assert {"browser.search", "files.read", "files.write", "code.run", "research.search"} <= set(stats["routes"])

    denied = run(worker.execute_task(worker.enqueue("code.run", {"code": "print(1)"}, role="User")))
    assert denied.status is TaskStatus.FAILED
    assert "code.run denied" in (denied.error or "")
    _cleanup(worker.files, "test_mega")

    payload = run(build_stage18_verify_payload())
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]


def test_stage1_9_limits():
    limits = LimitsEnforcer(enforcer=PermissionEnforcer(budget=BudgetManager()), backoff_scale=0.0)

    async def too_slow() -> None:
        await asyncio.sleep(5)

    timed = run(limits.execute_with_limits("code.run", too_slow, role="Operator", timeout_seconds=1))
    assert timed["ok"] is False
    assert timed["timeout_enforced"] is True
    assert timed["attempts"] == 1
    assert timed["declared_timeout_seconds"] == 60.0

    calls = {"count": 0}

    async def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 2:
            raise RuntimeError("transient")
        return "recovered"

    retried = run(limits.execute_with_limits("files.read", flaky))
    assert retried["ok"] is True
    assert retried["result"] == "recovered"
    assert retried["attempts"] == 2
    assert retried["retried"] is True
    assert len(retried["backoff_delays"]) == 1

    denied = run(limits.execute_with_limits("browser.search", flaky, role="Guest"))
    assert denied["ok"] is False
    assert denied["blocked_by"] == "gate"

    enforcer = limits.enforcer
    quota_tool = "research.search"
    quota_limit = enforcer.metadata(quota_tool)["quota_per_hour"]
    for _ in range(quota_limit):
        enforcer.record_call(quota_tool)
    quota = enforcer.check_quota(quota_tool)
    assert quota["allowed"] is False
    assert quota["used"] == quota_limit
    blocked = run(limits.execute_with_limits(quota_tool, flaky, role="User"))
    assert blocked["ok"] is False
    assert blocked["blocked_by"] == "gate"
    assert "quota" in blocked["error"]

    budget = BudgetManager(daily_limit_usd=0.0)
    assert budget.check(tool_cost_usd=0.0, limit_usd=0.0)["allowed"] is True
    assert budget.check(tool_cost_usd=1.0, limit_usd=0.0)["allowed"] is False

    policy = {"strategy": "exponential", "initial_seconds": 1.5, "multiplier": 2.0, "max_seconds": 8.0}
    assert [compute_backoff(i, policy) for i in (1, 2, 3, 4)] == [1.5, 3.0, 6.0, 8.0]
    assert compute_backoff(2, {"strategy": "linear", "initial_seconds": 1.0}) == 2.0
    assert compute_backoff(3, {"strategy": "fixed", "initial_seconds": 0.5}) == 0.5
    assert compute_backoff(1, policy, scale=0.0) == 0.0

    payload = run(build_stage19_verify_payload())
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]
    assert payload["checks"]["timeout_enforced"] is True
    assert payload["checks"]["retry_with_backoff"] is True
    assert payload["checks"]["quota_enforced"] is True
    assert payload["checks"]["budget_zero_cost_allowed"] is True


def test_stage1_10_mesh_e2e(worker):
    tester = ToolMeshTester(worker=worker)

    report = run(tester.test_e2e_research_file_sandbox())
    assert report["all_ok"] is True
    assert report["failed_checks"] == []
    assert len(report["checks"]) == 6
    assert all(report["checks"].values()), report["checks"]
    assert report["sources_used"] >= 1
    assert report["cost_usd"] == 0.0
    assert [step["step"] for step in report["trace"]] == [1, 2, 3, 4, 5, 6]
    assert all(step["ok"] for step in report["trace"])
    assert report["steps"]["worker"]["stats"]["queue_cleared"] is True
    assert report["steps"]["limits"]["quota_allowed"] is True
    assert report["steps"]["limits"]["budget_allowed"] is True

    repeat = run(tester.test_e2e_research_file_sandbox())
    assert repeat["all_ok"] is True
    assert repeat["run_id"] != report["run_id"]

    payload = run(build_stage110_verify_payload())
    assert payload["status"] == "✅ COMPLETE"
    assert payload["all_checks"] is True
    assert all(payload["checks"].values()), payload["checks"]

    mega = run(build_mega_verify_payload())
    assert mega["status"] == "✅ PHASE 1 COMPLETE"
    assert mega["all_checks"] is True
    assert mega["passed"] == mega["total_stages"] == len(ALL_STAGES) == 10
    assert mega["failed"] == 0
    assert mega["failed_stages"] == []
    assert mega["cost_usd"] == 0.0
    assert [stage["stage"] for stage in mega["stages"]] == [
        "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10",
    ]
    assert all(stage["status"] == "✅ COMPLETE" for stage in mega["stages"]), mega["stages"]
    for stage in ALL_STAGES:
        assert mega["details"][f"stage{stage}"]["all_checks"] is True, stage

    routes = {route.path for route in build_mega_router().routes}
    assert set(STAGE_VERIFY_PATHS.values()) <= routes
    assert MEGA_VERIFY_PATH in routes
    assert len(STAGE_VERIFY_PATHS) == 7