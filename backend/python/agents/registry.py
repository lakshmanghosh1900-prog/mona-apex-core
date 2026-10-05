from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from fabric.tools import ToolMesh


@dataclass(frozen=True)
class Agent:
    name: str
    role: str
    description: str
    tools: tuple[str, ...] = ()
    guardrail: str = "never perform irreversible actions without human approval"


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def prompts(self, mesh: ToolMesh) -> str:
        lines = []
        for agent in self._agents.values():
            tool_names = ", ".join(t for t in agent.tools if mesh.get(t))
            lines.append(f"- {agent.name} ({agent.role}): {agent.description}. Tools: {tool_names}")
        return "\n".join(lines)


def default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        Agent(
            name="planner",
            role="reasoning",
            description="Breaks a user goal into ordered, verifiable steps",
            tools=("time_now",),
        )
    )
    registry.register(
        Agent(
            name="operator",
            role="execution",
            description="Executes steps through the tool mesh and reports raw results",
            tools=("calculator", "http_fetch", "json_probe", "time_now"),
        )
    )
    registry.register(
        Agent(
            name="critic",
            role="verification",
            description="Checks executed output against the original goal",
            tools=(),
        )
    )
    registry.register(
        Agent(
            name="healer",
            role="recovery",
            description="Diagnoses failures and rewrites the failing step",
            tools=("calculator", "http_fetch"),
        )
    )
    return registry
