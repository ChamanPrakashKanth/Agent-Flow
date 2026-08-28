# Budgeted Working Memory and Ollama KV-Cache Configuration

## 1. Abstract & Theoretical Motivation

Large language model agents operating in long-horizon environments suffer from unbounded KV-cache growth ($O(N)$ memory scaling per sequence length). On hardware-constrained edge machines ($\le 6\text{ GB RAM/VRAM}$), traditional agent architectures requiring $32\text{K}$ to $64\text{K}$ tokens fail due to out-of-memory allocations during KV cache buffer initialization.

Based on the research monograph **_BUDGETED WORKING MEMORY: A Conceptual Architecture for Compressing Transformer KV State with Graph Consolidation, Learned Retention, and Adaptive Loss_**, this repository implements an application-level approximation: a bounded concept graph with multi-timescale exponential retention, neighbor reinforcement, and event-driven consolidation. It does not modify transformer layers or Ollama's internal tensors.

---

## 2. Mathematical Formulations

### 2.1 Multi-Timescale Retention Function
Each concept node $v_i \in V$ is assigned a dynamic timescale decay rate $\alpha_i$:

$$R_i(\Delta t, P) = \exp\left(-\alpha_i \cdot (1 + 0.75 P) \cdot \Delta t\right) + \beta \cdot \min(1.0, 0.25 \cdot \text{hits}_i)$$

Where:
* **$\Delta t = t_{\text{current}} - t_{\text{last\_accessed}}$**: Elapsed steps since last reinforcement.
* **$P = \frac{|V|}{B}$**: Real-time memory pressure relative to node budget $B$ (default $B = 8$).
* **$\beta = 0.80$**: Access reinforcement boost factor.
* **Timescales**:
  * **`SHORT`** ($\alpha = 0.75$): Ephemeral search snippets and queries.
  * **`MEDIUM`** ($\alpha = 0.30$): Candidate unselected story hypotheses.
  * **`LONG`** ($\alpha = 0.02$): Confirmed atomic facts and verified source origins.

```
Retention R(Δt) over Time:
1.0 |-----------------\
0.8 |                  \--- LONG (α=0.02, Confirmed Facts)
0.6 |          \
0.4 |           \--- MEDIUM (α=0.30, Story Candidates)
0.2 |    \
0.0 |_____\_________ SHORT (α=0.75, Search Snippets)
    +-----------------------------------> Δt (Steps)
```

### 2.2 Concept Graph & Reinforcement Diffusion
Nodes $V$ are connected in a semantic similarity graph $G = (V, E)$. When a primary fact node $v_i$ is reinforced upon verification:

$$R_{\text{neighbor}} \leftarrow R_{\text{neighbor}} + \gamma \cdot \text{weight} \quad (\gamma = 0.40)$$

### 2.3 Event-Driven Consolidation
Consolidation is triggered only when memory pressure exceeds threshold $\tau$:

$$P = \frac{|V|}{B} > \tau \quad (\tau = 0.60)$$

1. **Eviction**: Nodes with $R_i < \theta_{\text{evict}}$ ($\theta = 0.35$) are pruned.
2. **Latent Consolidation**: Overflow connected subgraphs are clustered into compact `ConceptMemoryToken` latent summaries:

$$\mathbf{c}_k = \text{ClusterSummary}(\{v_j \in V_{\text{overflow}}\})$$

3. **Prompt-state bound**: the internal graph is reduced to the pressure target, and at most four active concepts plus two consolidation summaries enter the planner view.

Physical KV memory is handled separately by Ollama. The Windows startup script sets `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q4_0`; model requests also set their configured `num_ctx`. This is the layer that quantizes KV storage. Exact memory savings depend on model, context length, parallelism, and hardware and are not inferred from the graph-node count.

---

## 3. Experimental Results

### 3.1 30-Task Adversarial Benchmark

We evaluated the architecture across 30 tasks with adversarial decoys, single-source traps, outdated information, and cross-domain claims.

| Level | Architecture Description | Task Completion (%) | Factual Accuracy | Unsupported Claims | Duplicate Rate | NO_POST Accuracy | Avg Tokens | Latency (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | Hermes 3 (Llama 3.2 3B) baseline alone | 53.3% | 0.50 | 0.733 | 0.10 | 0.417 | 1,800 | 18.0 |
| **B** | Hermes 3 (Llama 3.2 3B) + Web tools | 80.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,800 | 34.8 |
| **C** | Hermes 3 (Llama 3.2 3B) + Structured Planner | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,555 | 49.5 |
| **D** | Hermes 3 (Llama 3.2 3B) + Planner + Verifier | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,745 | 56.5 |
| **E** | **Offline policy simulation with persistent deduplication** | **100.0%** | **1.00** | **0.000** | **0.00** | **1.000** | **1,745** | **56.5** |

These values come from the deterministic simulator in `evaluation/benchmark.py`; they are architecture-fixture results, not live model-quality, browser-publishing, GPU-offload, or causal memory-ablation measurements.

### 3.2 What Is Measured

The tests verify deterministic IDs, decay ordering, bounded graph pressure, non-no-op consolidation, capped reinforcement, prompt-view bounds, and confirmed-only promotion. Hardware memory and end-to-end publishing need separate runtime measurements and are not claimed by this offline fixture.

---

## 4. Key Findings

1. Single-source claims stay medium-timescale evidence and are promoted only after deterministic two-origin verification.
2. Consolidation reduces the graph to the configured pressure target and increments its counter only when nodes are actually removed.
3. Deterministic SHA-256-derived IDs and capped reinforcement avoid process-random identity and immortal-node feedback loops.
4. Each research run starts with fresh working memory; durable cross-run duplicate detection remains in SQLite.
