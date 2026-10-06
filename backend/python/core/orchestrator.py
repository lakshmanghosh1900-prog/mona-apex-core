from __future__ import annotations

import asyncio
import json
import re
import time
import traceback
from typing import Any, AsyncIterator

from agents.registry import AgentRegistry, default_registry
from fabric.tools import ToolMesh, build_mesh, run_safe

from . import llm
from .config import settings

try:
    from langgraph.graph import END, StateGraph

    HAS_LANGGRAPH = True
except Exception:
    HAS_LANGGRAPH = False

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class StepFailure(RuntimeError):
    def __init__(self, step: dict[str, Any], error: str, results: list[dict[str, Any]] | None = None) -> None:
        super().__init__(error)
        self.step = step
        self.error = error
        self.results = results or []


class OrchestratorState(TypedDict, total=False):
    task: str
    context: str
    plan: dict[str, Any]
    results: list[dict[str, Any]]
    diagnosis: str
    attempts: int
    verified: bool
    answer: str
    error: str
    trace: list[dict[str, Any]]


def extract_json(raw: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError(f"model did not return valid JSON: {raw[:300]}")


class SelfHealingOrchestrator:
    def __init__(
        self,
        mesh: ToolMesh | None = None,
        registry: AgentRegistry | None = None,
        approval: Any | None = None,
        memory: Any | None = None,
    ) -> None:
        self.mesh = mesh or build_mesh()
        self.registry = registry or default_registry()
        self.approval = approval
        self.memory = memory
        self.max_attempts = max(1, settings.max_heal_attempts)
        self._graph: Any | None = None
        self._model_probe: bool | None = None

    def _initial_state(self, task: str, context: str) -> OrchestratorState:
        return {
            "task": task,
            "context": context,
            "plan": {},
            "results": [],
            "diagnosis": "",
            "attempts": 0,
            "verified": False,
            "answer": "",
            "error": "",
            "trace": [],
        }

    async def stream(self, task: str, context: str = "") -> AsyncIterator[dict[str, Any]]:
        state = self._initial_state(task, context)
        graph = await self._compiled_graph()
        if graph is None:
            async for event in self._run_builtin(state):
                yield event
        else:
            final = dict(state)
            try:
                async for update in graph.astream(state, stream_mode="updates"):
                    for node, patch in update.items():
                        patch = patch or {}
                        final.update(patch)
                        event = self._graph_event(node, patch)
                        if event:
                            yield event
            except Exception as exc:
                final["error"] = str(exc)
                yield {"type": "error", "message": str(exc)}
            state = final
        async for event in self._finish(state):
            yield event

    async def _compiled_graph(self) -> Any:
        if not settings.use_langgraph or not HAS_LANGGRAPH:
            return None
        if self._graph is None:
            self._graph = await build_graph(self)
        return self._graph

    def _graph_event(self, node: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        if node == "heal":
            return {
                "type": "heal",
                "node": "heal",
                "attempt": int(patch.get("attempts", 0)),
                "error": str(patch.get("diagnosis") or ""),
            }
        if node == "act" and patch.get("error"):
            return {
                "type": "heal",
                "node": "act",
                "attempt": int(patch.get("attempts", 0)),
                "error": str(patch.get("error")),
            }
        messages = {"plan": "decomposing task", "act": "executing steps", "verify": "checking result"}
        if node in messages:
            return {"type": "status", "node": node, "message": messages[node]}
        return None

    async def _run_builtin(self, state: OrchestratorState) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "node": "plan", "message": "decomposing task"}
        try:
            state.update(await self._plan(state))
        except Exception as exc:
            yield {"type": "heal", "node": "plan", "error": str(exc)}
            state.update(await self._heal(state, StepFailure({"tool": "plan"}, str(exc))))

        while True:
            attempts = int(state.get("attempts", 0))
            yield {"type": "status", "node": "act", "message": f"executing attempt {attempts + 1}"}
            try:
                state.update(await self._act(state))
            except StepFailure as exc:
                if attempts >= self.max_attempts:
                    yield {"type": "error", "message": exc.error}
                    state["error"] = exc.error
                    break
                state["attempts"] = attempts + 1
                yield {
                    "type": "heal",
                    "node": "act",
                    "attempt": state["attempts"],
                    "error": exc.error,
                }
                state.update(await self._heal(state, exc))
                continue

            yield {"type": "status", "node": "verify", "message": "checking result"}
            try:
                state.update(await self._verify(state))
            except StepFailure as exc:
                if attempts >= self.max_attempts:
                    state["error"] = exc.error
                    yield {"type": "error", "message": exc.error}
                    break
                state["attempts"] = attempts + 1
                yield {
                    "type": "heal",
                    "node": "verify",
                    "attempt": state["attempts"],
                    "error": exc.error,
                }
                state.update(await self._heal(state, exc))
                continue

            if state.get("verified"):
                break
            if attempts >= self.max_attempts:
                break
            state["attempts"] = attempts + 1
            yield {
                "type": "heal",
                "node": "verify",
                "attempt": state["attempts"],
                "error": state.get("diagnosis") or "result rejected by critic",
            }
            state.update(await self._heal(state, StepFailure({}, state.get("diagnosis") or "rejected")))

    async def _finish(self, state: OrchestratorState) -> AsyncIterator[dict[str, Any]]:
        answer = state.get("answer") or self._fallback_answer(state)
        yield {"type": "status", "node": "deliver", "message": "streaming answer"}
        async for token in self._deliver(state, answer):
            yield {"type": "token", "text": token}

        yield {
            "type": "result",
            "verified": bool(state.get("verified")),
            "attempts": int(state.get("attempts", 0)),
            "answer": answer,
            "trace": state.get("trace", []),
            "error": state.get("error", ""),
        }

    async def run(self, task: str, context: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        answer_parts: list[str] = []
        async for event in self.stream(task, context):
            if event["type"] == "token":
                answer_parts.append(event["text"])
            elif event["type"] == "result":
                result = event
        if result and not result.get("answer"):
            result["answer"] = "".join(answer_parts)
        return result

    def graph_summary(self) -> dict[str, Any]:
        return {
            "engine": "langgraph" if HAS_LANGGRAPH else "builtin",
            "max_attempts": self.max_attempts,
            "agents": [a.name for a in self.registry.all()],
            "tools": [t["name"] for t in self.mesh.specs()],
            "mutating_tools": sorted(self.mesh.mutating_names()),
            "approval_gate": self.approval is not None,
            "memory": self.memory is not None,
        }

    async def _plan(self, state: OrchestratorState) -> dict[str, Any]:
        valid_tools = ", ".join(sorted(spec["name"] for spec in self.mesh.specs())) or "none"
        prompt = self._system_prompt() + f"""

TASK: {state["task"]}
CONTEXT: {state.get("context") or "none"}
VALID TOOLS: {valid_tools}

Return ONLY JSON with this shape:
{{"steps":[{{"tool":"<tool name>","arguments":{{}},"reason":"why"}}],"needs_approval":false,"memory_query":"short query for long-term memory recall"}}
Use only VALID TOOLS. If no tool is required, use an empty steps array.
"""
        try:
            raw = await llm.chat(_messages(prompt))
            plan = extract_json(raw)
        except Exception as exc:
            trace = list(state.get("trace", []))
            trace.append({"node": "plan", "fallback": str(exc)})
            return {
                "plan": {"steps": [], "direct": True},
                "diagnosis": f"planner fallback: {exc}",
                "trace": trace,
            }
        plan.setdefault("steps", [])
        plan["steps"] = self._clean_steps(plan.get("steps"))
        if self.memory is not None and plan.get("memory_query"):
            recalled = await self._recall(str(plan["memory_query"]))
            if recalled:
                plan["context"] = recalled
        trace = list(state.get("trace", []))
        trace.append({"node": "plan", "steps": len(plan["steps"])})
        return {"plan": plan, "trace": trace, "diagnosis": ""}

    async def _act(self, state: OrchestratorState) -> dict[str, Any]:
        plan = state.get("plan", {})
        steps = plan.get("steps", [])
        results: list[dict[str, Any]] = list(state.get("results", []))

        if not steps:
            direct = await llm.chat(
                _messages(self._system_prompt() + f"\n\nTASK: {state['task']}\nCONTEXT: {state.get('context') or 'none'}\nAnswer the task directly in plain prose.")
            )
            results.append({"tool": "direct", "ok": True, "result": direct})
            return {"results": results, "answer": direct}

        for index, step in enumerate(steps):
            tool_name = str(step.get("tool") or "").strip()
            arguments = step.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            if not tool_name:
                continue
            if tool_name in self.mesh.mutating_names():
                approved = await self._gate(state["task"], step)
                if not approved:
                    raise StepFailure(step, f"human approval denied for tool '{tool_name}'")
            outcome = await run_safe(self.mesh, tool_name, arguments)
            outcome["index"] = index
            outcome["reason"] = step.get("reason", "")
            results.append(outcome)
            if not outcome["ok"]:
                raise StepFailure(step, outcome["error"], results=results)

        return {"results": results}

    async def _has_real_model(self) -> bool:
        if self._model_probe is not None:
            return self._model_probe
        order = llm.provider_order()
        if any(provider in {"groq", "gemini"} for provider in order):
            self._model_probe = True
            return True
        if "ollama" in order:
            self._model_probe = await llm.probe_ollama()
            return self._model_probe
        self._model_probe = False
        return False

    async def _verify(self, state: OrchestratorState) -> dict[str, Any]:
        results = state.get("results", [])
        if not await self._has_real_model():
            answer = ""
            for item in results:
                if item.get("ok") and item.get("tool") == "direct":
                    answer = str(item.get("result"))
            return {
                "verified": True,
                "diagnosis": "no external model configured, delivered direct answer",
                "answer": answer,
            }
        prompt = (
            self._system_prompt()
            + f"""

You are the critic agent. Decide whether the executed results satisfy the task.

TASK: {state["task"]}
RESULTS: {json.dumps(results, default=str)[:6000]}

Return ONLY JSON:
{{"verified":true,"reason":"...","answer":"final user-facing answer, complete prose"}}
"""
        )
        try:
            verdict = extract_json(await llm.chat(_messages(prompt)))
        except Exception as exc:
            raise StepFailure({}, f"critic failed: {exc}") from exc

        verified = bool(verdict.get("verified"))
        diagnosis = str(verdict.get("reason") or "")
        updates: dict[str, Any] = {"verified": verified, "diagnosis": diagnosis}
        if verified:
            updates["answer"] = str(verdict.get("answer") or "").strip()
        return updates

    async def _heal(self, state: OrchestratorState, failure: StepFailure) -> dict[str, Any]:
        attempt = int(state.get("attempts", 0))
        if not await self._has_real_model():
            trace = list(state.get("trace", []))
            trace.append({"node": "heal", "attempt": attempt, "skipped": failure.error})
            return {
                "diagnosis": f"self-heal skipped without an external model: {failure.error}",
                "trace": trace,
                "verified": False,
            }
        await asyncio.sleep(min(2**attempt, 6))
        prompt = (
            self._system_prompt()
            + f"""

You are the healer agent. A step failed and you must rewrite the plan.

TASK: {state["task"]}
CURRENT PLAN: {json.dumps(state.get("plan", {}), default=str)[:3000]}
RESULTS SO FAR: {json.dumps(state.get("results", []), default=str)[:3000]}
FAILURE: {failure.error}
FAILED STEP: {json.dumps(failure.step, default=str)[:1000]}

Return ONLY JSON:
{{"diagnosis":"root cause","steps":[{{"tool":"<tool>","arguments":{{}},"reason":"..."}}]}}
Prefer simpler tools or a direct prose answer when tools are not needed.
"""
        )
        try:
            patch = extract_json(await llm.chat(_messages(prompt)))
        except Exception as exc:
            patch = {"diagnosis": f"healer unavailable: {exc}", "steps": []}

        plan = dict(state.get("plan", {}))
        if isinstance(patch.get("steps"), list):
            plan["steps"] = self._clean_steps(patch["steps"])
        trace = list(state.get("trace", []))
        trace.append({"node": "heal", "attempt": attempt, "diagnosis": patch.get("diagnosis", "")})
        return {
            "plan": plan,
            "diagnosis": str(patch.get("diagnosis") or failure.error),
            "results": [],
            "verified": False,
            "trace": trace,
        }

    def _clean_steps(self, steps: Any) -> list[dict[str, Any]]:
        if not isinstance(steps, list):
            return []
        known = {spec["name"] for spec in self.mesh.specs()}
        cleaned: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            name = str(step.get("tool") or "").strip()
            if name not in known:
                continue
            arguments = step.get("arguments")
            cleaned.append(
                {
                    "tool": name,
                    "arguments": arguments if isinstance(arguments, dict) else {},
                    "reason": str(step.get("reason") or ""),
                }
            )
        return cleaned

    async def _gate(self, task: str, step: dict[str, Any]) -> bool:
        if self.approval is None:
            return settings.telegram_auto_approve
        try:
            return await self.approval.request(task=task, step=step, timeout=settings.telegram_timeout)
        except Exception:
            return False

    async def _recall(self, query: str) -> str:
        try:
            hits = await self.memory.recall(query, top_k=settings.memory_top_k)
        except Exception:
            return ""
        return "\n".join(h.get("text", "") for h in hits if h.get("text"))[:4000]

    async def _deliver(self, state: OrchestratorState, answer: str) -> AsyncIterator[str]:
        if not await self._has_real_model():
            for line in answer.splitlines() or [""]:
                yield line
            return
        prompt = (
            self._system_prompt()
            + f"\n\nTASK: {state['task']}\nFINAL ANSWER: {answer}\nRewrite the final answer as a polished, concise reply to the user. Prose only."
        )
        try:
            async for token in llm.stream(_messages(prompt)):
                yield token
        except Exception:
            for line in answer.splitlines() or [""]:
                yield line

    def _fallback_answer(self, state: OrchestratorState) -> str:
        results = state.get("results", [])
        if results:
            last = results[-1]
            if last.get("ok"):
                return str(last.get("result"))
        return state.get("diagnosis") or state.get("error") or "No result could be produced for this task."

    def _system_prompt(self) -> str:
        tools = json.dumps(self.mesh.specs(), indent=None)[:4000]
        return (
            "You are Mona, the Apex Core orchestrator. You are autonomous, terse, and factual.\n"
            f"AGENT SWARM:\n{self.registry.prompts(self.mesh)}\n"
            f"TOOL MESH SCHEMAS: {tools}\n"
            "Rules: use tools only when they add value; never invent tool output; "
            "irreversible or mutating actions require human approval; always emit valid JSON when asked for JSON."
        )


def _messages(system: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}]


async def build_graph(orchestrator: SelfHealingOrchestrator):
    if not HAS_LANGGRAPH:
        return None

    async def plan_node(state: OrchestratorState) -> dict[str, Any]:
        try:
            return await orchestrator._plan(state)
        except Exception as exc:
            return {
                "plan": {"steps": []},
                "diagnosis": f"planner failed: {exc}",
                "trace": [*state.get("trace", []), {"node": "plan", "error": str(exc)}],
            }

    async def act_node(state: OrchestratorState) -> dict[str, Any]:
        try:
            return await orchestrator._act(state)
        except StepFailure as exc:
            return {
                "error": exc.error,
                "failed_step": exc.step,
                "results": exc.results,
                "verified": False,
            }
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}", "failed_step": {}, "verified": False}

    async def verify_node(state: OrchestratorState) -> dict[str, Any]:
        if state.get("error"):
            return {}
        try:
            return await orchestrator._verify(state)
        except StepFailure as exc:
            return {"verified": False, "diagnosis": exc.error}

    async def heal_node(state: OrchestratorState) -> dict[str, Any]:
        attempts = int(state.get("attempts", 0)) + 1
        failure = StepFailure(state.get("failed_step", {}), state.get("error") or state.get("diagnosis") or "rejected")
        updates = await orchestrator._heal({**state, "attempts": attempts}, failure)
        updates["attempts"] = attempts
        updates["error"] = ""
        return updates

    def route_after_act(state: OrchestratorState) -> str:
        if state.get("error") and int(state.get("attempts", 0)) >= orchestrator.max_attempts:
            return END
        if state.get("error"):
            return "heal"
        return "verify"

    def route_after_verify(state: OrchestratorState) -> str:
        if state.get("verified"):
            return END
        if int(state.get("attempts", 0)) >= orchestrator.max_attempts:
            return END
        return "heal"

    def route_after_heal(state: OrchestratorState) -> str:
        if int(state.get("attempts", 0)) >= orchestrator.max_attempts:
            return END
        return "act"

    graph = StateGraph(OrchestratorState)
    graph.add_node("plan", plan_node)
    graph.add_node("act", act_node)
    graph.add_node("verify", verify_node)
    graph.add_node("heal", heal_node)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "act")
    graph.add_conditional_edges("act", route_after_act, {"verify": "verify", "heal": "heal", END: END})
    graph.add_conditional_edges("verify", route_after_verify, {"heal": "heal", END: END})
    graph.add_conditional_edges("heal", route_after_heal, {"act": "act", END: END})
    return graph.compile()


def describe_error(exc: BaseException) -> dict[str, str]:
    return {"type": type(exc).__name__, "message": str(exc)}


def elapsed(started: float) -> float:
    return round(time.monotonic() - started, 3)
