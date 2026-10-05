from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable

from fabric.registry.permission_enforcer import (
    TOOL_METADATA_REGISTRY,
    PermissionEnforcer,
    get_enforcer,
)


def compute_backoff(attempt: int, policy: dict[str, Any], scale: float = 1.0) -> float:
    """Delay before `attempt`+1. attempt is 1-based (already-failed count)."""
    strategy = str(policy.get("strategy", "fixed"))
    initial = float(policy.get("initial_seconds", 0.5) or 0.0)
    multiplier = float(policy.get("multiplier", 2.0) or 1.0)
    cap = float(policy.get("max_seconds", 8.0) or 0.0)

    if strategy == "exponential":
        delay = initial * (multiplier ** max(0, attempt - 1))
    elif strategy == "linear":
        delay = initial * max(1, attempt)
    else:
        delay = initial

    if cap > 0:
        delay = min(delay, cap)
    return round(max(0.0, delay) * max(0.0, scale), 6)


class LimitsEnforcer:
    """Stage 1.9 — one funnel for timeout, retry, quota and budget.

    `execute_with_limits` reads the Stage 1.2 metadata through
    `PermissionEnforcer`, so tool limits are declared once and enforced
    everywhere. `backoff_scale` exists so tests (and interactive calls) can
    run with the real policy shape but without the real sleep.
    """

    def __init__(self, enforcer: PermissionEnforcer | None = None, backoff_scale: float = 1.0) -> None:
        self.enforcer = enforcer or get_enforcer()
        self.backoff_scale = float(backoff_scale)

    # ---------- sync-friendly invocation ----------
    @staticmethod
    async def _call(func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        result = await asyncio.to_thread(func, *args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    # ---------- enforcement ----------
    async def execute_with_limits(
        self,
        tool_name: str,
        func: Callable[..., Any],
        *args: Any,
        role: str = "User",
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        gate = self.enforcer.check(tool_name, role=role)
        policy = self.enforcer.get_retry_policy(tool_name)
        declared_timeout = float(self.enforcer.get_timeout(tool_name))

        # A per-call override may only tighten the declared limit, never extend it.
        if timeout_seconds is None:
            timeout = declared_timeout
        else:
            timeout = min(max(float(timeout_seconds), 0.1), declared_timeout)
        max_attempts = max(1, int(policy.get("max_attempts", 1)))

        base = {
            "tool": tool_name,
            "timeout_seconds": timeout,
            "declared_timeout_seconds": declared_timeout,
            "timeout_overridden": timeout != declared_timeout,
            "max_attempts": max_attempts,
            "retry_policy": policy,
            "quota": gate["quota"],
            "budget": gate["budget"],
            "concurrency": gate["concurrency"],
            "requires_approval": gate["requires_approval"],
            "backoff_scale": self.backoff_scale,
        }

        if not gate["allowed"]:
            return {
                **base,
                "ok": False,
                "result": None,
                "error": "; ".join(gate["reasons"]) or "denied",
                "blocked_by": "gate",
                "attempts": 0,
                "timeout_enforced": False,
                "retried": False,
                "backoff_delays": [],
                "duration_ms": 0.0,
            }

        if not self.enforcer.try_acquire(tool_name):
            report = self.enforcer.check_concurrency(tool_name)
            return {
                **base,
                "ok": False,
                "result": None,
                "error": f"concurrency limit reached: {report['active']}/{report['limit']}",
                "blocked_by": "concurrency",
                "attempts": 0,
                "timeout_enforced": False,
                "retried": False,
                "backoff_delays": [],
                "duration_ms": 0.0,
            }

        started = time.perf_counter()
        attempts = 0
        timeout_enforced = False
        delays: list[float] = []
        last_error = "tool did not run"

        try:
            for attempt in range(1, max_attempts + 1):
                attempts = attempt
                try:
                    result = await asyncio.wait_for(
                        self._call(func, args, kwargs), timeout=timeout
                    )
                    recorded = self.enforcer.record_call(tool_name)
                    return {
                        **base,
                        "ok": True,
                        "result": result,
                        "error": None,
                        "blocked_by": None,
                        "attempts": attempt,
                        "timeout_enforced": timeout_enforced,
                        "retried": attempt > 1,
                        "backoff_delays": delays,
                        "quota_used": recorded["quota_used"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                except asyncio.TimeoutError:
                    timeout_enforced = True
                    last_error = f"timeout after {timeout}s"
                except Exception as exc:  # noqa: BLE001 - retried below, reported at the end
                    last_error = f"{type(exc).__name__}: {exc}"

                if attempt < max_attempts:
                    delay = compute_backoff(attempt, policy, self.backoff_scale)
                    delays.append(delay)
                    if delay > 0:
                        await asyncio.sleep(delay)

            quota = self.enforcer.check_quota(tool_name)
            return {
                **base,
                "ok": False,
                "result": None,
                "error": last_error,
                "blocked_by": "attempts_exhausted",
                "attempts": attempts,
                "timeout_enforced": timeout_enforced,
                "retried": attempts > 1,
                "backoff_delays": delays,
                "quota": quota,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        finally:
            self.enforcer.release(tool_name)

    # ---------- policy reporting ----------
    def policy_for(self, tool_name: str) -> dict[str, Any]:
        gate = self.enforcer.check(tool_name, role="User")
        return {
            "tool_name": tool_name,
            "timeout_seconds": self.enforcer.get_timeout(tool_name),
            "retry_policy": self.enforcer.get_retry_policy(tool_name),
            "quota": gate["quota"],
            "budget": gate["budget"],
            "concurrency": gate["concurrency"],
            "cost_usd": gate["cost"],
            "zero_cost_stack": gate["cost"] == 0.0,
        }

    def limits_summary(self) -> dict[str, Any]:
        return {
            "tools": sorted(TOOL_METADATA_REGISTRY),
            "enforced": ["timeout", "retry_backoff", "quota_per_hour", "budget_per_day", "max_concurrent"],
            "backoff_strategies": ["exponential", "linear", "fixed"],
            "backoff_scale": self.backoff_scale,
            "budget_spent_today_usd": self.enforcer.budget.spent_today(),
            "zero_cost_stack": self.enforcer.budget.zero_cost,
        }


_limiter: LimitsEnforcer | None = None


def get_limiter(backoff_scale: float = 1.0) -> LimitsEnforcer:
    global _limiter
    if _limiter is None or backoff_scale != _limiter.backoff_scale:
        _limiter = LimitsEnforcer(backoff_scale=backoff_scale)
    return _limiter


def reset_limiter() -> None:
    global _limiter
    _limiter = None