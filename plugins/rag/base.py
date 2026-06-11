from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RagDocument:
    path: Path
    title: str
    content: str
    content_type: str


@dataclass(frozen=True)
class RagQuery:
    query: str
    top_k: int = 5


@dataclass(frozen=True)
class RagResult:
    document: RagDocument
    score: float
    snippet: str


class RagRetriever(Protocol):
    """Reserved interface for Markdown, PDF, TXT and enterprise knowledge bases."""

    async def search(self, query: RagQuery) -> list[RagResult]:
        raise NotImplementedError
