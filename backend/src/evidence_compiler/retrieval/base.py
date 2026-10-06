"""Retriever interface. BM25 today; embedding or hybrid retrievers can slot in later."""

from dataclasses import dataclass
from typing import Protocol

from evidence_compiler.core.models import EvidenceItem


@dataclass(frozen=True)
class Hit:
    item: EvidenceItem
    score: float


class Retriever(Protocol):
    def index(self, items: list[EvidenceItem]) -> None: ...

    def remove_source(self, source_id: str) -> None: ...

    def search(self, query: str, k: int) -> list[Hit]: ...
