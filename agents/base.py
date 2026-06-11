from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentContext:
    user_id: int
    command: str
    payload: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentResult:
    ok: bool
    content: str
    metadata: dict[str, Any] | None = None


class BaseAgent(Protocol):
    """Base interface for Planner, Coding, Search and Ops agents."""

    name: str

    async def run(self, context: AgentContext) -> AgentResult:
        raise NotImplementedError
