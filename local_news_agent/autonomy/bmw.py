from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any

from ..model import estimate_tokens


@dataclass
class MemoryItem:
    kind: str; text: str; importance: float = 0.5; sources: list[str] = field(default_factory=list); created_at: float = field(default_factory=time)


class BoundedMemoryWindow:
    """A fixed-size prompt memory with explicit compression/discard metrics."""

    def __init__(self, max_items: int = 12, max_tokens: int = 1200):
        self.max_items = max(4, max_items); self.max_tokens = max(256, max_tokens); self.items: list[MemoryItem] = []
        self.compressed = self.discarded = self.retrieval_count = 0

    def add(self, kind: str, text: str, importance: float = 0.5, sources: list[str] | None = None) -> None:
        clean = " ".join(str(text).split())[:1000]
        if clean: self.items.append(MemoryItem(kind, clean, min(1.0, max(0.0, importance)), list(dict.fromkeys(sources or []))))
        self._bound()

    def retrieve(self, query: str, limit: int = 4) -> list[MemoryItem]:
        words = set(query.lower().split())
        ranked = sorted(self.items, key=lambda x: (len(words & set(x.text.lower().split())), x.importance), reverse=True)
        self.retrieval_count += 1
        return ranked[:max(1, limit)]

    def context(self) -> dict[str, Any]:
        selected = sorted(self.items, key=lambda x: x.importance, reverse=True)
        return {"items": [{"kind": x.kind, "text": x.text[:320], "sources": x.sources[:3]} for x in selected], "metrics": self.metrics()}

    def metrics(self) -> dict[str, int]:
        return {"prompt_tokens": estimate_tokens(" ".join(x.text for x in self.items)), "estimated_kv_pressure": min(100, int(100 * estimate_tokens(" ".join(x.text for x in self.items)) / self.max_tokens)), "items_retained": len(self.items), "items_compressed": self.compressed, "items_discarded": self.discarded, "retrieval_count": self.retrieval_count}

    def _bound(self) -> None:
        self.items.sort(key=lambda x: (x.importance, x.created_at), reverse=True)
        while len(self.items) > self.max_items:
            dropped = self.items.pop(); self.discarded += 1
            if dropped.importance >= 0.55 and self.items:
                self.items[-1].text = (self.items[-1].text[:240] + " | " + dropped.text[:120])[:400]; self.compressed += 1
        while estimate_tokens(" ".join(x.text for x in self.items)) > self.max_tokens and self.items:
            self.items.pop(); self.discarded += 1
