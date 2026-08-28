from __future__ import annotations

from local_news_agent.memory.budgeted_working_memory import (
    BudgetedWorkingMemory,
    ConceptGraph,
    ConceptNode,
    Timescale,
    stable_node_id,
)
from local_news_agent.schemas import AgentState


def test_timescale_decay_rates():
    """Verify that alpha_short > alpha_medium > alpha_long under passage of time."""
    n_short = ConceptNode(id="1", text="Search snippet", category="search", timescale=Timescale.SHORT)
    n_med = ConceptNode(id="2", text="Story candidate", category="story", timescale=Timescale.MEDIUM)
    n_long = ConceptNode(id="3", text="Confirmed fact", category="fact", timescale=Timescale.LONG)

    step_delta = 5
    r_short = n_short.retention(current_step=step_delta)
    r_med = n_med.retention(current_step=step_delta)
    r_long = n_long.retention(current_step=step_delta)

    assert r_long > r_med > r_short, f"Decay ordering violated: long={r_long}, med={r_med}, short={r_short}"


def test_retention_reinforcement():
    """Verify that access reinforcement beta * r increases retention strength."""
    node = ConceptNode(id="1", text="Key discovery", category="fact", timescale=Timescale.MEDIUM)
    initial_retention = node.retention(current_step=10)

    node.reinforce(current_step=10, weight=2)
    reinforced_retention = node.retention(current_step=10)

    assert reinforced_retention > initial_retention
    assert node.access_count == 3
    assert node.last_accessed_step == 10


def test_reinforcement_is_capped():
    node = ConceptNode(id="1", text="Popular concept", category="fact", timescale=Timescale.LONG)
    for step in range(100):
        node.reinforce(current_step=step, weight=5)
    assert node.importance == 5.0
    assert node.access_count == 20


def test_concept_graph_edges_and_diffusion():
    """Verify semantic edge creation and neighbor diffusion."""
    graph = ConceptGraph()
    n1 = ConceptNode(id="n1", text="DeepSeek announces new transformer model architecture", category="fact", timescale=Timescale.MEDIUM)
    n2 = ConceptNode(id="n2", text="Transformer model architecture benchmark released by DeepSeek", category="story", timescale=Timescale.SHORT)

    graph.add_node(n1)
    graph.add_node(n2)
    graph.add_edge("n1", "n2")

    assert len(graph.neighbors("n1")) == 1
    assert graph.neighbors("n1")[0].id == "n2"

    graph.reinforce("n1", current_step=8, weight=1)
    assert graph.nodes["n2"].last_accessed_step == 8


def test_event_driven_consolidation_under_pressure():
    """Verify that exceeding memory budget triggers GAT consolidation and state bounding."""
    bwm = BudgetedWorkingMemory(budget_nodes=5, pressure_threshold=0.75, min_retention_threshold=0.30)

    # Ingest 10 search results to create memory pressure
    for i in range(10):
        bwm.tick(step=i)
        bwm.ingest_search_result(
            title=f"Article {i} about Quantum Computing and Superconductors",
            snippet=f"Quantum processor breakthrough announced in benchmark iteration {i}.",
            url=f"https://example.com/quantum_{i}",
        )

    # Ingest 2 confirmed facts with LONG timescale
    bwm.ingest_confirmed_fact(
        headline="Quantum Advantage Demonstrated",
        fact="Laboratory achieves 99.9% 2-qubit gate fidelity with photonic links.",
        sources=["https://official.test/quantum"],
    )

    summary = bwm.get_budgeted_summary()
    assert bwm.total_consolidations >= 1
    assert len(summary["active_concepts"]) <= bwm.budget_nodes
    assert len(bwm.graph.nodes) <= bwm.budget_nodes
    assert len(summary["consolidated_memories"]) > 0


def test_ids_are_deterministic_and_source_sensitive():
    assert stable_node_id("search", "https://example.test/a") == stable_node_id("search", "https://example.test/a")
    assert stable_node_id("search", "https://example.test/a") != stable_node_id("search", "https://example.test/b")


def test_consolidation_reduces_to_pressure_target_and_is_not_a_noop():
    bwm = BudgetedWorkingMemory(budget_nodes=8, pressure_threshold=0.75)
    for i in range(7):
        bwm.ingest_search_result(f"Result {i}", f"Distinct evidence snippet {i}", f"https://example.test/{i}")
    assert len(bwm.graph.nodes) == 6
    assert bwm.total_consolidations == 1
    assert bwm.consolidate_if_needed() is False
    assert bwm.total_consolidations == 1


def test_reingesting_confirmed_fact_reinforces_in_place():
    bwm = BudgetedWorkingMemory(budget_nodes=8)
    first = bwm.ingest_confirmed_fact("Headline", "Verified atomic fact", ["https://one.test"])
    before = bwm.graph.nodes[first].access_count
    second = bwm.ingest_confirmed_fact("Headline", "Verified atomic fact", ["https://two.test"])
    assert first == second
    assert len(bwm.graph.nodes) == 1
    assert bwm.graph.nodes[first].access_count > before
    assert bwm.graph.nodes[first].metadata["sources"] == ["https://one.test", "https://two.test"]


def test_unverified_claim_is_not_labeled_confirmed():
    bwm = BudgetedWorkingMemory()
    node_id = bwm.ingest_evidence_claim("Headline", "Single-source statement", ["https://one.test"])
    node = bwm.graph.nodes[node_id]
    assert node.category == "evidence_claim"
    assert node.timescale == Timescale.MEDIUM


def test_agent_state_compact_with_budgeted_working_memory():
    """Verify AgentState.compact integrates working memory summary seamlessly."""
    bwm = BudgetedWorkingMemory(budget_nodes=6)
    bwm.ingest_search_result("Test headline", "Test snippet", "https://test.com/a")

    state = AgentState(task="test_task", topic="AI", run_id="r1", working_memory=bwm)
    compact_view = state.compact()

    assert "working_memory" in compact_view
    assert "active_concepts" in compact_view["working_memory"]
    assert "memory_pressure" in compact_view["working_memory"]
    assert len(compact_view["working_memory"]["active_concepts"]) == 1


def test_compact_prompt_bounds_raw_results_and_memory_nodes():
    bwm = BudgetedWorkingMemory(budget_nodes=12, pressure_threshold=1.0)
    state = AgentState(task="test_task", topic="AI", run_id="r1", working_memory=bwm)
    from local_news_agent.schemas import SearchResult

    for i in range(10):
        result = SearchResult(title=f"Headline {i}", url=f"https://example.test/{i}", snippet="x" * 1000)
        state.search_results.append(result)
        bwm.ingest_search_result(result.title, result.snippet, result.url)

    compact_view = state.compact()
    assert len(compact_view["results"]) == 4
    assert all("snippet" not in item for item in compact_view["results"])
    assert len(compact_view["working_memory"]["active_concepts"]) <= 4
