from __future__ import annotations

import math
import re
from hashlib import sha256
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Timescale(str, Enum):
    SHORT = "SHORT"      # e.g., transient search snippets, ephemeral queries (fast decay)
    MEDIUM = "MEDIUM"    # e.g., candidate unselected stories (moderate decay)
    LONG = "LONG"        # e.g., confirmed facts, selected story, verified claims (slow decay)


# Base alpha decay coefficients (higher = faster forgetting)
ALPHA_MAP: dict[Timescale, float] = {
    Timescale.SHORT: 0.75,
    Timescale.MEDIUM: 0.30,
    Timescale.LONG: 0.02,
}

MAX_IMPORTANCE = 5.0
MAX_ACCESS_COUNT = 20


def stable_node_id(prefix: str, value: str) -> str:
    """Return a deterministic, collision-resistant ID across Python processes."""
    digest = sha256(value.strip().casefold().encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


@dataclass
class ConceptNode:
    """Atomic node in the working memory concept graph with Concept-Importance-governed decay."""
    id: str
    text: str
    category: str
    timescale: Timescale = Timescale.SHORT
    importance: float = 1.0  # Concept Importance I(c)
    created_step: int = 0
    last_accessed_step: int = 0
    access_count: int = 1
    base_alpha: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.base_alpha is None:
            self.base_alpha = ALPHA_MAP.get(self.timescale, 0.20)

    def retention(self, current_step: int, pressure: float = 0.0, beta: float = 0.8) -> float:
        """Compute learned retention score governed by Concept Importance I(c).

        Decay is a direct function of Concept Importance:
            effective_alpha = (base_alpha / max(0.1, self.importance)) * (1.0 + 0.75 * max(0.0, pressure))
            R(c, Delta t) = importance * exp(-effective_alpha * Delta t) + beta * min(1.0, 0.25 * access_count)

        - High Concept Importance (I(c) >> 1, e.g. confirmed facts, primary evidence):
          effective_alpha -> 0.0, decay is strongly dampened, concept persists in memory.
        - Low Concept Importance (I(c) -> 0, e.g. ephemeral search scraps):
          effective_alpha is high, concept decays rapidly and gets evicted during consolidation.
        """
        effective_alpha = (self.base_alpha / max(0.1, self.importance)) * (1.0 + 0.75 * max(0.0, pressure))
        delta_t = max(0, current_step - self.last_accessed_step)
        decay = self.importance * math.exp(-effective_alpha * delta_t)
        reinforcement = beta * min(1.0, 0.25 * self.access_count)
        return decay + reinforcement

    def reinforce(self, current_step: int, weight: int = 1) -> None:
        """Reinforce memory retention upon retrieval or verification."""
        self.last_accessed_step = current_step
        self.access_count = min(MAX_ACCESS_COUNT, self.access_count + max(0, weight))
        self.importance = min(MAX_IMPORTANCE, self.importance + 0.25 * max(0, weight))



class ConceptGraph:
    """Concept graph G = (V, E) maintaining relations and neighbor attention."""

    def __init__(self) -> None:
        self.nodes: dict[str, ConceptNode] = {}
        self.edges: dict[str, set[str]] = {}

    def add_node(self, node: ConceptNode) -> None:
        self.nodes[node.id] = node
        if node.id not in self.edges:
            self.edges[node.id] = set()

    def add_edge(self, id_a: str, id_b: str) -> None:
        if id_a in self.nodes and id_b in self.nodes and id_a != id_b:
            self.edges.setdefault(id_a, set()).add(id_b)
            self.edges.setdefault(id_b, set()).add(id_a)

    def reinforce(self, node_id: str, current_step: int, weight: int = 1) -> None:
        if node_id in self.nodes:
            self.nodes[node_id].reinforce(current_step, weight)
            # Propagate partial reinforcement to connected neighbors (GAT-inspired diffusion)
            for neighbor_id in self.edges.get(node_id, ()):
                if neighbor_id in self.nodes:
                    neighbor = self.nodes[neighbor_id]
                    neighbor.last_accessed_step = current_step
                    neighbor.importance = min(MAX_IMPORTANCE, neighbor.importance + 0.1 * max(0, weight))

    def neighbors(self, node_id: str) -> list[ConceptNode]:
        return [self.nodes[n_id] for n_id in self.edges.get(node_id, ()) if n_id in self.nodes]

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        neighbors = self.edges.pop(node_id, set())
        for n in neighbors:
            if n in self.edges:
                self.edges[n].discard(node_id)


class BudgetedWorkingMemory:
    """Event-driven bounded working memory manager with GAT consolidation and adaptive loss."""

    def __init__(
        self,
        budget_nodes: int = 8,
        pressure_threshold: float = 0.60,
        min_retention_threshold: float = 0.35,
    ) -> None:
        self.budget_nodes = max(4, budget_nodes)
        self.pressure_threshold = pressure_threshold
        self.min_retention_threshold = min_retention_threshold
        self.current_step = 0
        self.graph = ConceptGraph()
        self.consolidated_tokens: list[dict[str, Any]] = []
        self.total_consolidations = 0

    @property
    def pressure(self) -> float:
        """Memory pressure P = |V| / B (Monograph Section 8)."""
        return len(self.graph.nodes) / self.budget_nodes

    def tick(self, step: int) -> None:
        self.current_step = step
        self.consolidate_if_needed()

    def ingest_search_result(self, title: str, snippet: str, url: str) -> str:
        """Ingest search item into short-timescale working memory."""
        node_id = stable_node_id("search", url)
        if node_id not in self.graph.nodes:
            node = ConceptNode(
                id=node_id,
                text=f"{title}: {snippet[:140]}",
                category="search_result",
                timescale=Timescale.SHORT,
                importance=0.6,
                created_step=self.current_step,
                last_accessed_step=self.current_step,
                metadata={"url": url, "title": title},
            )
            self.graph.add_node(node)
            self._link_related_nodes(node)
        else:
            self.graph.reinforce(node_id, self.current_step, weight=1)
        self.consolidate_if_needed()
        return node_id

    def ingest_story_candidate(self, headline: str, event: str, confidence: float, sources: list[str]) -> str:
        """Ingest candidate story into medium-timescale working memory."""
        node_id = stable_node_id("story", headline)
        if node_id not in self.graph.nodes:
            node = ConceptNode(
                id=node_id,
                text=f"{headline} - {event[:160]}",
                category="story_candidate",
                timescale=Timescale.MEDIUM,
                importance=max(1.0, float(confidence) * 1.5),
                created_step=self.current_step,
                last_accessed_step=self.current_step,
                metadata={"headline": headline, "confidence": confidence, "sources": sources},
            )
            self.graph.add_node(node)
            self._link_related_nodes(node)
        else:
            self.graph.reinforce(node_id, self.current_step, weight=2)
        self.consolidate_if_needed()
        return node_id

    def ingest_evidence_claim(self, headline: str, claim: str, sources: list[str]) -> str:
        """Store a source claim without promoting it to a confirmed fact."""
        node_id = stable_node_id("claim", claim)
        if node_id not in self.graph.nodes:
            node = ConceptNode(
                id=node_id,
                text=claim[:200],
                category="evidence_claim",
                timescale=Timescale.MEDIUM,
                importance=0.9,
                created_step=self.current_step,
                last_accessed_step=self.current_step,
                metadata={"headline": headline, "sources": list(dict.fromkeys(sources))},
            )
            self.graph.add_node(node)
            self._link_related_nodes(node)
        else:
            node = self.graph.nodes[node_id]
            node.metadata["sources"] = list(dict.fromkeys([*node.metadata.get("sources", []), *sources]))
            self.graph.reinforce(node_id, self.current_step)
        self.consolidate_if_needed()
        return node_id

    def ingest_confirmed_fact(self, headline: str, fact: str, sources: list[str]) -> str:
        """Ingest verified/confirmed facts into long-timescale working memory."""
        node_id = stable_node_id("fact", fact)
        if node_id in self.graph.nodes:
            node = self.graph.nodes[node_id]
            node.metadata["sources"] = list(dict.fromkeys([*node.metadata.get("sources", []), *sources]))
            node.timescale = Timescale.LONG
            node.base_alpha = ALPHA_MAP[Timescale.LONG]
            node.category = "confirmed_fact"
            self.graph.reinforce(node_id, self.current_step, weight=2)
            self.consolidate_if_needed()
            return node_id
        node = ConceptNode(
            id=node_id,
            text=fact[:200],
            category="confirmed_fact",
            timescale=Timescale.LONG,
            importance=2.5,
            created_step=self.current_step,
            last_accessed_step=self.current_step,
            access_count=3,
            metadata={"headline": headline, "sources": sources},
        )
        self.graph.add_node(node)
        self._link_related_nodes(node)
        self.consolidate_if_needed()
        return node_id

    def reinforce_selected(self, headline: str) -> None:
        """Heavily reinforce the selected story across memory."""
        for node in self.graph.nodes.values():
            if headline.lower() in node.text.lower():
                node.timescale = Timescale.LONG
                node.base_alpha = ALPHA_MAP[Timescale.LONG]
                node.importance = min(MAX_IMPORTANCE, node.importance + 1.5)
                self.graph.reinforce(node.id, self.current_step, weight=4)


    def _link_related_nodes(self, new_node: ConceptNode) -> None:
        """Build graph edges based on shared semantic terms."""
        stop_words = {"this", "that", "with", "from", "have", "will", "about", "after", "before", "news"}
        new_terms = {w for w in re.findall(r"[a-z0-9]+", new_node.text.lower()) if len(w) > 3 and w not in stop_words}
        if not new_terms:
            return

        for other_id, other_node in self.graph.nodes.items():
            if other_id == new_node.id:
                continue
            other_terms = {w for w in re.findall(r"[a-z0-9]+", other_node.text.lower()) if len(w) > 3 and w not in stop_words}
            overlap = len(new_terms & other_terms)
            if overlap >= 2:
                self.graph.add_edge(new_node.id, other_id)

    def consolidate_if_needed(self) -> bool:
        """Event-Driven Consolidation: if usage / budget > tau, compress (Monograph Section 4 & 5)."""
        if self.pressure <= self.pressure_threshold:
            return False

        p = self.pressure

        # 1. Evaluate retention for all nodes
        node_retention: list[tuple[float, ConceptNode]] = [
            (node.retention(self.current_step, pressure=p), node)
            for node in list(self.graph.nodes.values())
        ]

        # 2. Remove decayed nodes, then reduce to the configured pressure target.
        # This avoids reporting repeated "consolidations" that removed nothing.
        target_nodes = max(1, min(self.budget_nodes, math.floor(self.budget_nodes * self.pressure_threshold)))
        removed: list[ConceptNode] = [node for score, node in node_retention if score < self.min_retention_threshold]
        removed_ids = {node.id for node in removed}
        survivors = [(score, node) for score, node in node_retention if node.id not in removed_ids]
        survivors.sort(key=lambda item: (item[0], item[1].id), reverse=True)
        overflow = [node for _, node in survivors[target_nodes:]]
        for node in overflow:
            if node.id not in removed_ids:
                removed.append(node)
                removed_ids.add(node.id)

        if not removed:
            return False

        self.total_consolidations += 1
        cluster_text = " | ".join(f"[{node.category}] {node.text[:50]}" for node in removed[:4])
        self.consolidated_tokens.append({
            "token_id": f"c_mem_{self.total_consolidations}",
            "summary": f"Compressed evidence concepts ({len(removed)} items): {cluster_text[:180]}",
            "step": self.current_step,
            "timescale": "CONSOLIDATED",
        })
        self.consolidated_tokens = self.consolidated_tokens[-2:]
        for node in removed:
            self.graph.remove_node(node.id)
        return True


    def get_budgeted_summary(self) -> dict[str, Any]:
        """Return the bounded working memory view for compact prompt formatting."""
        p = self.pressure
        scored_nodes = [
            {
                "id": node.id,
                "category": node.category,
                "text": node.text[:100],
                "retention": round(node.retention(self.current_step, pressure=p), 2),
                "timescale": node.timescale.value,
            }
            for node in self.graph.nodes.values()
        ]
        scored_nodes.sort(key=lambda x: x["retention"], reverse=True)
        return {
            # Up to four high-retention concepts keep the planner prompt compact even
            # when the internal graph budget is larger.
            "active_concepts": scored_nodes[: min(self.budget_nodes, 4)],
            "consolidated_memories": self.consolidated_tokens[-2:],
            "memory_pressure": round(self.pressure, 2),
            "consolidations": self.total_consolidations,
        }
