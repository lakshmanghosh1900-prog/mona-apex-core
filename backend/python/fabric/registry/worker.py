from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from fabric.registry.api_tool import ApiTool, get_api_tool
from fabric.registry.file_tool import FileTool, get_file_tool
from fabric.registry.limits import LimitsEnforcer
from fabric.registry.research_engine import ResearchEngine, get_research_engine
from fabric.registry.sandbox import SecureSandbox, get_sandbox


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class Task:
    task_id: str
    tool_name: str
    inputs: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: str | None = None
    role: str = "User"
    attempts: int = 0
    duration_ms: float = 0.0
    queued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    finished_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tool_name": self.tool_name,
            "inputs": self.inputs,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "role": self.role,
            "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 2),
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class UnsupportedTool(KeyError):
    pass


TaskHandler = Callable[[dict[str, Any], str], Awaitable[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionWorker:
    """Stage 1.8 — Agent task -> worker queue -> real tool.

    The worker owns no tool logic of its own: each route delegates to the
    Stage 1.3-1.7 implementation, so a queued task and a direct tool call
    behave identically.
    """

    def __init__(
        self,
        files: FileTool | None = None,
        sandbox: SecureSandbox | None = None,
        research: ResearchEngine | None = None,
        apis: ApiTool | None = None,
        limits: LimitsEnforcer | None = None,
    ) -> None:
        self.files = files or get_file_tool()
        self.sandbox = sandbox or get_sandbox()
        self.research = research or get_research_engine()
        self.apis = apis or get_api_tool()
        self.limits = limits or LimitsEnforcer()
        self.queue: list[Task] = []
        self.history: list[Task] = []
        self._total_enqueued = 0
        self._routes: dict[str, TaskHandler] = {
            "browser.search": self._route_browser_search,
            "research.search": self._route_research,
            "files.read": self._route_files_read,
            "files.write": self._route_files_write,
            "files.search": self._route_files_search,
            "code.run": self._route_code_run,
            "api.call": self._route_api_call,
        }

    # ---------- routes ----------
    @property
    def routes(self) -> list[str]:
        return sorted(self._routes)

    def register_route(self, tool_name: str, handler: TaskHandler) -> None:
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._routes[tool_name] = handler

    async def _route_browser_search(self, inputs: dict[str, Any], role: str) -> Any:
        from fabric.registry.browser_tool import get_browser_tool

        return await get_browser_tool().search(
            query=str(inputs.get("query", "")),
            limit=int(inputs.get("limit", inputs.get("max_results", 5)) or 5),
            role=role,
        )

    async def _route_research(self, inputs: dict[str, Any], role: str) -> Any:
        return await self.research.research(
            query=str(inputs.get("query", inputs.get("topic", ""))),
            sources=int(inputs.get("sources", inputs.get("max_sources", 3)) or 3),
            role=role,
        )

    async def _route_files_read(self, inputs: dict[str, Any], role: str) -> Any:
        return self.files.read(
            path=str(inputs.get("path", "")),
            role=role,
            max_chars=int(inputs.get("max_chars", 50_000) or 50_000),
        )

    async def _route_files_write(self, inputs: dict[str, Any], role: str) -> Any:
        return self.files.write(
            path=str(inputs.get("path", "")),
            content=str(inputs.get("content", "")),
            role=role,
            append=bool(inputs.get("append", False)),
        )

    async def _route_files_search(self, inputs: dict[str, Any], role: str) -> Any:
        return self.files.search(
            pattern=str(inputs.get("pattern", "")),
            role=role,
            glob=str(inputs.get("glob", "**/*") or "**/*"),
            use_regex=bool(inputs.get("use_regex", True)),
        )

    async def _route_code_run(self, inputs: dict[str, Any], role: str) -> Any:
        return self.sandbox.run_python(
            code=str(inputs.get("code", "")),
            timeout=float(inputs.get("timeout_seconds", inputs.get("timeout", 15)) or 15),
            role=role,
        )

    async def _route_api_call(self, inputs: dict[str, Any], role: str) -> Any:
        return await self.apis.call_api(
            api_name=str(inputs.get("api", inputs.get("api_name", ""))),
            endpoint=str(inputs.get("endpoint", "")),
            params=inputs.get("params") or {},
            role=role,
        )

    # ---------- queue ----------
    def enqueue(self, tool_name: str, inputs: dict[str, Any] | None = None, role: str = "User") -> Task:
        name = str(tool_name).strip()
        if name not in self._routes:
            raise UnsupportedTool(f"no route for tool '{name}', known routes: {self.routes}")
        task = Task(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            tool_name=name,
            inputs=dict(inputs or {}),
            role=role,
        )
        self.queue.append(task)
        self._total_enqueued += 1
        return task

    async def execute_task(self, task: Task) -> Task:
        handler = self._routes.get(task.tool_name)
        if handler is None:
            task.status = TaskStatus.FAILED
            task.error = f"no route for tool '{task.tool_name}'"
            task.finished_at = _now()
            self.history.append(task)
            return task

        task.status = TaskStatus.RUNNING
        task.started_at = _now()
        started = time.perf_counter()
        task.attempts += 1
        try:
            task.result = await handler(task.inputs, task.role)
            task.status = TaskStatus.COMPLETE
        except Exception as exc:  # noqa: BLE001 - a failed tool call is data, not a crash
            task.status = TaskStatus.FAILED
            task.error = f"{type(exc).__name__}: {exc}"
        finally:
            task.duration_ms = (time.perf_counter() - started) * 1000
            task.finished_at = _now()
            self.history.append(task)
        return task

    async def dispatch(self, tool_name: str, inputs: dict[str, Any] | None = None, role: str = "User") -> Task:
        """Run one routed tool call through a transient Task, without queueing."""
        name = str(tool_name).strip()
        if name not in self._routes:
            raise UnsupportedTool(f"no route for tool '{name}', known routes: {self.routes}")
        task = Task(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            tool_name=name,
            inputs=dict(inputs or {}),
            role=role,
        )
        return await self.execute_task(task)

    async def process_queue(self) -> list[Task]:
        processed: list[Task] = []
        while self.queue:
            processed.append(await self.execute_task(self.queue.pop(0)))
        return processed

    # ---------- reporting ----------
    def get_stats(self) -> dict[str, Any]:
        by_status = {status.value: 0 for status in TaskStatus}
        for task in self.history:
            by_status[task.status.value] += 1
        return {
            "queued": len(self.queue),
            "total_enqueued": self._total_enqueued,
            "executed": len(self.history),
            "completed": by_status[TaskStatus.COMPLETE.value],
            "failed": by_status[TaskStatus.FAILED.value],
            "by_status": by_status,
            "routes": self.routes,
            "queue_cleared": not self.queue,
            "sandbox_root": str(self.files.root),
        }

    def reset(self) -> None:
        self.queue.clear()
        self.history.clear()
        self._total_enqueued = 0


_worker: ExecutionWorker | None = None


def get_worker() -> ExecutionWorker:
    global _worker
    if _worker is None:
        _worker = ExecutionWorker()
    return _worker


def reset_worker() -> None:
    global _worker
    _worker = None