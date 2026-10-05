from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fabric.registry.file_tool import FileTool, get_file_tool
from fabric.registry.limits import LimitsEnforcer
from fabric.registry.research_engine import ResearchEngine, get_research_engine
from fabric.registry.sandbox import SecureSandbox, get_sandbox
from fabric.registry.worker import ExecutionWorker, get_worker


class ToolMeshTester:
    """Stage 1.10 — end-to-end mesh: research -> file -> sandbox -> worker -> limits.

    Every step uses the production tools through the worker/limits stack, so a
    pass here means the stages compose, not just that each unit works alone.
    """

    def __init__(
        self,
        worker: ExecutionWorker | None = None,
        files: FileTool | None = None,
        sandbox: SecureSandbox | None = None,
        research: ResearchEngine | None = None,
        limits: LimitsEnforcer | None = None,
    ) -> None:
        self.worker = worker or get_worker()
        self.files = files or self.worker.files
        self.sandbox = sandbox or self.worker.sandbox
        self.research = research or self.worker.research
        self.limits = limits or self.worker.limits

    async def test_e2e_research_file_sandbox(self, query: str = "monorepo agent orchestration", sources: int = 3) -> dict[str, Any]:
        started = time.perf_counter()
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        report_path = f"mesh/{run_id}_report.md"
        trace: list[dict[str, Any]] = []
        steps: dict[str, Any] = {}

        # 1. research — evidence-backed answer
        research = await self.research.research(query=query, sources=sources, role="User")
        steps["research"] = {
            "sources_used": research["sources_used"],
            "cross_check_pass": research["cross_check_pass"],
            "confidence": research["confidence"],
        }
        trace.append({"step": 1, "name": "research.search", "ok": research["sources_used"] >= 1})
        research_ok = research["sources_used"] >= 1 and bool(research["evidence"])

        # 2. file write — persist the answer + its evidence
        body = [
            f"# Mona mesh report {run_id}",
            "",
            research["answer"],
            "",
            "## Evidence",
            *[f"- [{e['title']}]({e['url']}) — {e['domain']} (confidence {e['confidence']})" for e in research["evidence"]],
            "",
        ]
        write_task = await self.worker.dispatch("files.write", {"path": report_path, "content": "\n".join(body)}, "User")
        write = write_task.result or {}
        steps["file_write"] = {"path": write.get("path"), "bytes_written": write.get("bytes_written")}
        trace.append({"step": 2, "name": "files.write", "ok": bool(write.get("ok"))})

        # 3. file read — verify what landed on disk
        read_task = await self.worker.dispatch("files.read", {"path": report_path}, "User")
        read = read_task.result or {}
        content = str(read.get("content", ""))
        steps["file_read"] = {"path": read.get("path"), "chars": read.get("chars")}
        trace.append({"step": 3, "name": "files.read", "ok": bool(read.get("ok"))})
        file_read_ok = bool(read.get("ok")) and research["answer"] in content and "## Evidence" in content

        # 4. sandbox — execute code derived from the researched material
        expected = len(research["evidence"])
        sandbox_task = await self.worker.dispatch(
            "code.run", {"code": f"print({expected} * 2)", "timeout_seconds": 10}, "Operator"
        )
        sandbox = sandbox_task.result or {}
        steps["sandbox"] = {
            "stdout": sandbox.get("stdout", "").strip(),
            "returncode": sandbox.get("returncode"),
            "timed_out": sandbox.get("timed_out"),
        }
        trace.append({"step": 4, "name": "code.run", "ok": bool(sandbox.get("ok"))})
        sandbox_ok = bool(sandbox.get("ok")) and sandbox.get("stdout", "").strip() == str(expected * 2)

        # 5. worker — the same read, this time through the task queue
        task = self.worker.enqueue("files.read", {"path": report_path}, role="User")
        processed = await self.worker.process_queue()
        stats = self.worker.get_stats()
        steps["worker"] = {"task_id": task.task_id, "processed": len(processed), "stats": stats}
        trace.append({"step": 5, "name": "ExecutionWorker", "ok": stats["queue_cleared"] and processed[0].status.value == "COMPLETE"})
        worker_ok = bool(stats["queue_cleared"]) and bool(processed) and processed[0].status.value == "COMPLETE"

        # 6. limits — the same sandbox call, this time through the limits funnel
        limited = await self.limits.execute_with_limits(
            "code.run", self.sandbox.run_python, f"print({expected} * 2)", 10, role="Operator"
        )
        steps["limits"] = {
            "ok": limited["ok"],
            "attempts": limited["attempts"],
            "timeout_enforced": limited["timeout_enforced"],
            "retried": limited["retried"],
            "quota_allowed": limited["quota"]["allowed"],
            "budget_allowed": limited["budget"]["allowed"],
        }
        trace.append({"step": 6, "name": "LimitsEnforcer", "ok": bool(limited["ok"])})
        limits_ok = bool(limited["ok"]) and limited["quota"]["allowed"] and limited["budget"]["allowed"]

        checks = {
            "research_ok": research_ok,
            "file_write_ok": bool(write.get("ok")),
            "file_read_ok": file_read_ok,
            "sandbox_ok": sandbox_ok,
            "worker_ok": worker_ok,
            "limits_ok": limits_ok,
        }
        all_ok = all(checks.values())
        return {
            "ok": all_ok,
            "all_ok": all_ok,
            "checks": checks,
            "failed_checks": [name for name, ok in checks.items() if not ok],
            "query": query,
            "run_id": run_id,
            "report_path": report_path,
            "steps": steps,
            "trace": trace,
            "sources_used": research["sources_used"],
            "confidence": research["confidence"],
            "cost_usd": 0.0,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }


_tester: ToolMeshTester | None = None


def get_mesh_tester() -> ToolMeshTester:
    global _tester
    if _tester is None:
        _tester = ToolMeshTester()
    return _tester


def reset_mesh_tester() -> None:
    global _tester
    _tester = None