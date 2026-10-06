"""Deterministic BM25 retrieval over document evidence (PDF paragraphs and table rows)."""

import re
import threading

from rank_bm25 import BM25Okapi

from evidence_compiler.core.models import EvidenceItem
from evidence_compiler.retrieval.base import Hit

_STOP = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "what",
        "why",
        "how",
        "which",
        "who",
        "did",
        "does",
        "do",
    ]
)


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    return [t for t in tokens if t not in _STOP]


class BM25Retriever:
    def __init__(self) -> None:
        self._items: dict[str, EvidenceItem] = {}
        self._order: list[str] = []
        self._bm25: BM25Okapi | None = None
        self._lock = threading.Lock()

    def index(self, items: list[EvidenceItem]) -> None:
        with self._lock:
            for item in items:
                self._items[item.id] = item
            self._rebuild()

    def remove_source(self, source_id: str) -> None:
        with self._lock:
            self._items = {k: v for k, v in self._items.items() if source_id not in v.source_ids}
            self._rebuild()

    def _rebuild(self) -> None:
        self._order = list(self._items)
        corpus = [tokenize(self._items[i].text) or ["_"] for i in self._order]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def search(self, query: str, k: int) -> list[Hit]:
        with self._lock:
            if self._bm25 is None:
                return []
            q = tokenize(query)
            if not q:
                return []
            scores = self._bm25.get_scores(q)
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            return [
                Hit(self._items[self._order[i]], float(scores[i]))
                for i in ranked[:k]
                if scores[i] > 0
            ]
