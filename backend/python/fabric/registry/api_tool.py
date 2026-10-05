from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from fabric.registry.registry_loader import get_registry

RATE_WINDOW_SECONDS = 60.0


class ApiNotRegistered(KeyError):
    pass


class ApiRateLimitError(RuntimeError):
    pass


@dataclass
class ApiConfig:
    """Declarative description of an external API.

    Secrets never live here: `auth_env` names the environment variable that
    holds the token, and the value is only read at call time.
    """

    name: str
    base_url: str
    description: str = ""
    auth_env: str | None = None
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"
    rate_limit_per_minute: int = 60
    timeout_seconds: float = 15.0
    cost_usd: float = 0.0
    allow_live: bool = False
    mock_responses: dict[str, Any] = field(default_factory=dict)
    default_mock: Any = None
    headers: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "description": self.description,
            "auth_env": self.auth_env,
            "auth_configured": bool(self.auth_env and os.getenv(self.auth_env)),
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "timeout_seconds": self.timeout_seconds,
            "cost_usd": self.cost_usd,
            "allow_live": self.allow_live,
            "mock_endpoints": sorted(self.mock_responses),
            "headers": sorted(self.headers),
        }


class ApiTool:
    """Stage 1.6 — generic external API calls with rate limiting + mocks.

    `allow_live=False` (the default) keeps the stack at $0 and makes every
    call deterministic: the configured mock payload is returned without
    touching the network. Live mode is opt-in per API.
    """

    def __init__(self) -> None:
        self._apis: dict[str, ApiConfig] = {}
        self._calls: dict[str, Deque[float]] = {}
        self._lock = threading.Lock()
        self.total_calls = 0
        self.rate_limited_calls = 0

    # ---------- registration ----------
    def register_api(self, name: str, config: ApiConfig | dict[str, Any]) -> dict[str, Any]:
        key = str(name).strip()
        if not key:
            raise ValueError("api name must be a non-empty string")
        if isinstance(config, dict):
            payload = dict(config)
            payload.setdefault("name", key)
            config = ApiConfig(**payload)
        if config.name != key:
            config.name = key
        if config.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")
        with self._lock:
            self._apis[key] = config
            self._calls.setdefault(key, deque())
        return config.as_dict()

    def unregister_api(self, name: str) -> bool:
        with self._lock:
            existed = self._apis.pop(name, None) is not None
            self._calls.pop(name, None)
        return existed

    def get_api(self, name: str) -> ApiConfig:
        config = self._apis.get(name)
        if config is None:
            raise ApiNotRegistered(f"api not registered: {name}")
        return config

    def list_apis(self) -> list[dict[str, Any]]:
        with self._lock:
            configs = list(self._apis.values())
        return [c.as_dict() for c in sorted(configs, key=lambda c: c.name)]

    # ---------- rate limiting ----------
    def _prune(self, name: str) -> None:
        window = self._calls.setdefault(name, deque())
        now = time.time()
        while window and now - window[0] > RATE_WINDOW_SECONDS:
            window.popleft()

    def check_rate_limit(self, name: str) -> dict[str, Any]:
        config = self.get_api(name)
        with self._lock:
            self._prune(name)
            used = len(self._calls[name])
        return {
            "allowed": used < config.rate_limit_per_minute,
            "used": used,
            "limit": config.rate_limit_per_minute,
            "window_seconds": RATE_WINDOW_SECONDS,
            "resets_in_seconds": round(RATE_WINDOW_SECONDS - (time.time() - self._calls[name][0]), 2)
            if self._calls.get(name)
            else 0.0,
        }

    def _record_call(self, name: str) -> None:
        with self._lock:
            self._prune(name)
            self._calls[name].append(time.time())
            self.total_calls += 1

    # ---------- calling ----------
    def _mock_for(self, config: ApiConfig, endpoint: str) -> Any:
        if endpoint in config.mock_responses:
            return config.mock_responses[endpoint]
        return config.default_mock

    def _auth_headers(self, config: ApiConfig) -> dict[str, str]:
        headers = {"User-Agent": "mona-apex-core/1.0", **config.headers}
        token = os.getenv(config.auth_env, "").strip() if config.auth_env else ""
        if token:
            prefix = f"{config.auth_prefix} " if config.auth_prefix else ""
            headers[config.auth_header] = f"{prefix}{token}"
        return headers

    async def call_api(
        self,
        api_name: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        role: str = "User",
    ) -> dict[str, Any]:
        config = self.get_api(api_name)
        params = dict(params or {})
        started = time.perf_counter()

        allowed = True
        reasons: list[str] = []
        rate_limited = False
        if not get_registry().check_permission(TOOL_GUARD_TOOL, role):
            allowed = False
            reasons.append(f"role '{role}' not permitted to call external APIs")

        rate = self.check_rate_limit(api_name)
        if not rate["allowed"]:
            allowed = False
            rate_limited = True
            reasons.append(f"rate limit exceeded: {rate['used']}/{rate['limit']} per minute")
            self.rate_limited_calls += 1

        if not allowed:
            return {
                "tool": TOOL_GUARD_TOOL,
                "ok": False,
                "api": api_name,
                "endpoint": endpoint,
                "rate_limited": rate_limited,
                "rate": rate,
                "params": params,
                "mocked": False,
                "error": "; ".join(reasons),
                "reasons": reasons,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        url = f"{config.base_url.rstrip('/')}/{str(endpoint).lstrip('/')}"
        mocked = True
        status = 200
        data: Any = self._mock_for(config, endpoint)
        error: str | None = None

        if config.allow_live:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
                    response = await client.request(
                        method.upper(), url, params=params, headers=self._auth_headers(config)
                    )
                status = response.status_code
                mocked = False
                try:
                    data = response.json()
                except ValueError:
                    data = response.text
            except Exception as exc:  # noqa: BLE001 - degrade to mock, never 500 on a 0-cost stack
                error = f"{type(exc).__name__}: {exc}"
                data = self._mock_for(config, endpoint)

        self._record_call(api_name)
        return {
            "tool": TOOL_GUARD_TOOL,
            "ok": 200 <= status < 300,
            "api": api_name,
            "endpoint": endpoint,
            "method": method.upper(),
            "url": url,
            "status": status,
            "mocked": mocked,
            "rate_limited": False,
            "rate": rate,
            "params": params,
            "data": data,
            "error": error,
            "auth_configured": bool(config.auth_env and os.getenv(config.auth_env)),
            "cost_usd": config.cost_usd,
            "live_enabled": config.allow_live,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        }

    # ---------- housekeeping ----------
    def stats(self) -> dict[str, Any]:
        with self._lock:
            names = list(self._apis)
        return {
            "registered": len(names),
            "apis": names,
            "total_calls": self.total_calls,
            "rate_limited_calls": self.rate_limited_calls,
            "window_seconds": RATE_WINDOW_SECONDS,
        }

    def reset(self) -> None:
        with self._lock:
            self._apis.clear()
            self._calls.clear()
        self.total_calls = 0
        self.rate_limited_calls = 0


TOOL_GUARD_TOOL = "research.search"

_framework: ApiTool | None = None


def get_api_tool() -> ApiTool:
    global _framework
    if _framework is None:
        _framework = ApiTool()
    return _framework


def reset_api_tool() -> None:
    global _framework
    _framework = None


def demo_config(name: str = "mona.demo", rate_limit_per_minute: int = 2) -> ApiConfig:
    """Zero-cost fixture used by the Stage 1.6 verification endpoint."""
    return ApiConfig(
        name=name,
        base_url="https://api.example.invalid/v1",
        description="Deterministic 0-cost fixture for Phase 1 verification.",
        auth_env="MONA_DEMO_API_KEY",
        rate_limit_per_minute=rate_limit_per_minute,
        mock_responses={
            "status": {"ok": True, "stack": "zero-cost", "mock": True},
            "echo": {"ok": True, "echo": None},
        },
        default_mock={"ok": True, "mock": True, "stack": "zero-cost"},
    )


__all__ = [
    "ApiConfig",
    "ApiNotRegistered",
    "ApiRateLimitError",
    "ApiTool",
    "RATE_WINDOW_SECONDS",
    "demo_config",
    "get_api_tool",
    "reset_api_tool",
]