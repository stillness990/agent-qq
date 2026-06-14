from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class McpRequest:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class McpResponse:
    ok: bool
    content: str
    metadata: dict[str, Any] | None = None


class McpConnector(Protocol):
    """Reserved interface for future MCP integrations."""

    async def call(self, request: McpRequest) -> McpResponse:
        raise NotImplementedError
