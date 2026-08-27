from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Timescale(str, Enum):
    SHORT = "SHORT"      # e.g., transient search snippets, ephemeral queries (fast decay)
    MEDIUM = "MEDIUM"    # e.g., candidate unselected stories (moderate decay)
    LONG = "LONG"        # e.g., confirmed facts, selected story, verified claims (slow decay)


# Base alpha decay coefficients (higher = faster forgetting)
ALPHA_MAP: dict[Timescale, float] = {
    Timescale.SHORT: 0.50,
    Timescale.MEDIUM: 0.15,
    Timescale.LONG: 0.02,
}


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
            effective_alpha = (base_alpha / max(0.1, self.importance)) * (1.0 + 0.5 * max(0.0, pressure))
            R(c, Delta t) = importance * exp(-effective_alpha * Delta t) + beta * min(1.0, 0.25 * access_count)

        - High Concept Importance (I(c) >> 1, e.g. confirmed facts, primary evidence):
          effective_alpha -> 0.0, decay is strongly dampened, concept persists in memory.
        - Low Concept Importance (I(c) -> 0, e.g. ephemeral search scraps):
          effective_alpha is high, concept decays rapidly and gets evicted during consolidation.
        """
        effective_alpha = (self.base_alpha / max(0.1, self.importance)) * (1.0 + 0.5 * max(0.0, pressure))
        delta_t = max(0, current_step - self.last_accessed_step)
        decay = self.importance * math.exp(-effective_alpha * delta_t)
        reinforcement = beta * min(1.0, 0.25 * self.access_count)
        return decay + reinforcement

    def reinforce(self, current_step: int, weight: int = 1) -> None:
        """Reinforce memory retention upon retrieval or verification."""
        self.last_accessed_step = current_step
        self.access_count += weight
        self.importance += 0.25 * weight



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
                    self.nodes[neighbor_id].last_accessed_step = current_step

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
        budget_nodes: int = 12,
        pressure_threshold: float = 0.75,
        min_retention_threshold: float = 0.25,
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
        node_id = f"search_{abs(hash(url)) % 100000}"
        if node_id not in self.graph.nodes:
            node = ConceptNode(
                id=node_id,
                text=f"{title}: {snippet[:180]}",
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
        node_id = f"story_{abs(hash(headline)) % 100000}"
        if node_id not in self.graph.nodes:
            node = ConceptNode(
                id=node_id,
                text=f"{headline} - {event[:200]}",
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

    def ingest_confirmed_fact(self, headline: str, fact: str, sources: list[str]) -> str:
        """Ingest verified/confirmed facts into long-timescale working memory."""
        node_id = f"fact_{abs(hash(fact)) % 100000}"
        node = ConceptNode(
            id=node_id,
            text=fact[:250],
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
                node.importance += 1.5
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

        self.total_consolidations += 1
        p = self.pressure

        # 1. Evaluate retention for all nodes
        node_retention: list[tuple[float, ConceptNode]] = [
            (node.retention(self.current_step, pressure=p), node)
            for node in list(self.graph.nodes.values())
        ]

        # 2. Identify sub-threshold decayed nodes and consolidate them
        decayed = [node for score, node in node_retention if score < self.min_retention_threshold]
        if decayed:
            cluster_text = " | ".join(node.text[:80] for node in decayed[:6])
            concept_token = {
                "token_id": f"c_mem_{self.total_consolidations}",
                "summary": f"Decayed concepts ({len(decayed)} items): {cluster_text[:200]}",
                "step": self.current_step,
                "timescale": "CONSOLIDATED",
            }
            self.consolidated_tokens.append(concept_token)
            self.consolidated_tokens = self.consolidated_tokens[-4:]
            for node in decayed:
                self.graph.remove_node(node.id)

        # 3. If still over budget, consolidate remaining overflow into concept summaries
        if len(self.graph.nodes) > self.budget_nodes:
            active_scored = [
                (node.retention(self.current_step, pressure=p), node)
                for node in self.graph.nodes.values()
            ]
            active_scored.sort(key=lambda x: x[0], reverse=True)

            to_compress = [node for _, node in active_scored[self.budget_nodes:]]
            if to_compress:
                cluster_text = " | ".join(node.text[:80] for node in to_compress[:6])
                concept_token = {
                    "token_id": f"c_mem_{self.total_consolidations}_overflow",
                    "summary": f"Consolidated concepts ({len(to_compress)} items): {cluster_text[:200]}",
                    "step": self.current_step,
                    "timescale": "CONSOLIDATED",
                }
                self.consolidated_tokens.append(concept_token)
                self.consolidated_tokens = self.consolidated_tokens[-4:]

                for node in to_compress:
                    self.graph.remove_node(node.id)

        return True


    def get_budgeted_summary(self) -> dict[str, Any]:
        """Return the bounded working memory view for compact prompt formatting."""
        p = self.pressure
        scored_nodes = [
            {
                "id": node.id,
                "category": node.category,
                "text": node.text[:140],
                "retention": round(node.retention(self.current_step, pressure=p), 2),
                "timescale": node.timescale.value,
            }
            for node in self.graph.nodes.values()
        ]
        scored_nodes.sort(key=lambda x: x["retention"], reverse=True)
        return {
            "active_concepts": scored_nodes[: self.budget_nodes],
            "consolidated_memories": self.consolidated_tokens[-2:],
            "memory_pressure": round(self.pressure, 2),
            "consolidations": self.total_consolidations,
        }
