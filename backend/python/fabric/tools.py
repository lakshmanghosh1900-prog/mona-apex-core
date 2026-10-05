from __future__ import annotations

import inspect
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import httpx


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]
    mutating: bool = False

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "mutating": self.mutating,
        }


class ToolMesh:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict[str, Any]]:
        return [t.schema() for t in self._tools.values()]

    async def invoke(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        return await tool.handler(**(arguments or {}))

    def mutating_names(self) -> set[str]:
        return {name for name, tool in self._tools.items() if tool.mutating}


async def _time_now(tz: str = "UTC") -> str:
    if tz != "UTC":
        tz = "UTC"
    return datetime.now(timezone.utc).isoformat()


async def _calculator(expression: str) -> Any:
    allowed = set("0123456789+-*/(). %eE")
    if not expression or set(expression) - allowed:
        raise ValueError("expression contains unsupported characters")
    try:
        return eval(expression, {"__builtins__": {}}, {"math": math})  # noqa: S307
    except Exception as exc:
        raise ValueError(f"could not evaluate expression: {exc}") from exc


async def _http_fetch(url: str, max_chars: int = 4000) -> str:
    if not url.startswith(("http://", "https://")):
        raise ValueError("only http(s) urls are supported")
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        res = await client.get(url, headers={"User-Agent": "MonaApexCore/1.0"})
        res.raise_for_status()
        return res.text[:max_chars]


async def _json_probe(payload: str) -> Any:
    return json.loads(payload)


def build_mesh() -> ToolMesh:
    mesh = ToolMesh()
    mesh.register(
        Tool(
            name="time_now",
            description="Return the current UTC timestamp in ISO-8601 format.",
            parameters={
                "type": "object",
                "properties": {"tz": {"type": "string", "enum": ["UTC"]}},
                "required": [],
            },
            handler=_time_now,
        )
    )
    mesh.register(
        Tool(
            name="calculator",
            description="Evaluate a basic arithmetic expression and return the number.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            handler=_calculator,
        )
    )
    mesh.register(
        Tool(
            name="http_fetch",
            description="Fetch a public http(s) URL and return raw text content.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 4000},
                },
                "required": ["url"],
            },
            handler=_http_fetch,
        )
    )
    mesh.register(
        Tool(
            name="json_probe",
            description="Parse a JSON string and return the structured value.",
            parameters={
                "type": "object",
                "properties": {"payload": {"type": "string"}},
                "required": ["payload"],
            },
            handler=_json_probe,
        )
    )
    return mesh


async def run_safe(mesh: ToolMesh, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    tool = mesh.get(name)
    if tool is None:
        return {"tool": name, "ok": False, "error": f"unknown tool: {name}"}
    try:
        value = tool.handler(**(arguments or {}))
        if inspect.isawaitable(value):
            value = await value
        return {"tool": name, "ok": True, "result": value}
    except Exception as exc:
        return {"tool": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
