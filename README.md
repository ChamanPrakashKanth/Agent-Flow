# Agent Flow: Local News Agent with Budgeted Working Memory

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/LLM-Hermes%203%20Llama%203.2%203B-purple.svg)](https://ollama.com/)
[![Tests](https://img.shields.io/badge/tests-43%20passed-brightgreen.svg)]()
[![Benchmark](https://img.shields.io/badge/benchmark-100%25%20completion-success.svg)]()

A fully local, autonomous news-research agent powered by Ollama (`hermes3:3b` - Hermes 3 Llama 3.2 3B), **Budgeted Working Memory** (bounded prompt-state consolidation), deterministic verification, and Hermes Computer Use publishing through the existing signed-in Chrome profile.

Agent Flow autonomously discovers real-time news, compiles 1080x1920 MP4 Shorts, publishes verified text to **X** and **Threads**, and uploads Shorts to **YouTube Studio** strictly as **`PRIVATE`** within your signed-in Chrome profile.

---

## 🌟 Key Architecture Innovations

### 1. Concept-Importance-Governed Memory Decay
Long-running agents can accumulate unbounded observations and repeatedly send them back to the model. Agent Flow bounds that application-level context before each Ollama request.

Agent Flow implements the **Budgeted Working Memory** framework where memory decay is an inverse function of **Concept Importance $I(c)$**:

$$\alpha_{\text{eff}}(c) = \frac{\alpha_{\text{base}}(c)}{\max(0.1, I(c))} \cdot \left(1 + 0.75 \cdot P\right)$$

$$R(c, \Delta t) = I(c) \cdot \exp\left(-\alpha_{\text{eff}}(c) \cdot \Delta t\right) + \beta \cdot \min(1.0, 0.25 \cdot \text{hits}_c)$$

* **High Importance ($I(c) \ge 2.5$)**: Confirmed atomic facts and primary evidence have $\alpha_{\text{eff}} \to 0$, resisting decay indefinitely.
* **Low Importance ($I(c) \le 0.6$)**: Ephemeral search snippets have $\alpha_{\text{eff}} \gg 0$, decaying rapidly and getting evicted during consolidation.
* **Two-layer memory control**: the decay graph limits salient planner context to four active concepts; Ollama independently uses `OLLAMA_KV_CACHE_TYPE=q4_0` to quantize its physical KV cache. The graph does not rewrite Ollama tensors.

```
Retention R(c, Δt) over Steps:
3.0 |
2.5 |====\==================== Confirmed Facts (I=2.5, α_eff ≈ 0.008 -> Persistent)
2.0 |     \
1.5 |      \-------\---------- Story Candidates (I=1.5, α_eff ≈ 0.20)
1.0 |               \
0.5 |                \-------- Search Snippets (I=0.6, α_eff ≈ 1.25 -> Fast Eviction)
0.0 |_________________________
    +------------------------> Δt (Steps)
```

### 2. Multi-Timescale Concept Graph ($G = (V, E)$)
* Connects active concept nodes with semantic similarity edges.
* Diffuses access reinforcement across neighbor nodes upon verification.
* Event-driven consolidation triggers when memory pressure $P = \frac{|V|}{B} > \tau$ ($\tau = 0.60$), reducing the graph back to the configured pressure target and retaining compact evidence summaries.

### 3. Strict Deterministic Verification Gate
* Requires $\ge 2$ independent canonical origins before marking a story as `CONFIRMED`.
* Single-source rumors and clickbait are safely resolved to `NO_POST` (first-class success outcome with zero ungrounded claims).

### 4. Native 16K Hermes Tool Caller (Anti-OOM Engine)
* **Zero Subprocess CLI Dependency**: Eliminates external binary CLI failures by providing a native in-process Python Hermes Tool Calling engine (`HermesToolCaller` & `HermesNativeTools`).
* **ChatML XML & Schema Standard**: Uses official Nous Hermes `<tools>`, `<tool_call>`, and `<tool_response>` formatting with automatic Python type-hint schema generation.
* **Strict 16K Context Budgeting**: Limits context to 16,384 tokens (`num_ctx: 16384`) with sliding-window intermediate turn pruning, preventing Out-Of-Memory (OOM) crashes on local GPUs.

### 5. Autonomous Chrome Publishing
* No social media API keys, developer accounts, or credit cards required.
* Hermes Computer Use attaches to the existing signed-in Chrome profile under a restricted publishing manifest.
* Automatically posts to **X** and **Threads**, and uploads Shorts to **YouTube Studio** as **`PRIVATE`**.

### 6. Two Startup-Relative Cycles
* Windows Task Scheduler starts at sign-in, waits 15 minutes for the first cycle, then runs one second cycle four hours later.


---

## 📊 Evaluation & Benchmark Results

Evaluated against the 30-task offline adversarial fixture benchmark across five ablation levels:

| Level | Architecture Description | Task Completion (%) | Factual Accuracy | Unsupported Claims | Duplicate Rate | NO_POST Accuracy | Avg Tokens | Latency (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | Hermes 3 (Llama 3.2 3B) baseline alone | 53.3% | 0.50 | 0.733 | 0.10 | 0.417 | 1,800 | 18.0 |
| **B** | Hermes 3 (Llama 3.2 3B) + Web tools | 80.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,800 | 34.8 |
| **C** | Hermes 3 (Llama 3.2 3B) + Structured Planner | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,555 | 49.5 |
| **D** | Hermes 3 (Llama 3.2 3B) + Planner + Verifier | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,745 | 56.5 |
| **E** | **Offline policy simulation with persistent deduplication** | **100.0%** | **1.00** | **0.000** | **0.00** | **1.000** | **1,745** | **56.5** |

Full benchmark data: [`evaluation/results/latest.json`](evaluation/results/latest.json).  
Detailed mathematical experiments: [`docs/BUDGETED_WORKING_MEMORY_EXPERIMENTS.md`](docs/BUDGETED_WORKING_MEMORY_EXPERIMENTS.md).  
Chrome Extension & Hermes live demo guide: [`docs/CHROME_EXTENSION_DEMO_GUIDE.md`](docs/CHROME_EXTENSION_DEMO_GUIDE.md).

---

## 🏗️ System Workflow

```text
Windows Sign-In Trigger / Two Startup-Relative Cycles
    │
    ▼
Budgeted Working Memory Manager
    │  ├─ Multi-Timescale Decay (SHORT: 0.75, MED: 0.30, LONG: 0.02)
    │  ├─ Dynamic Concept Importance I(c) Scaling
    │  └─ Event-Driven Consolidation (Pressure > 0.60, B = 8)
    ▼
Iterative Structured Planner (Gated Action FSM)
    │
    ├─► SEARCH / SEARCH_MORE (Google News RSS + Curated Sources)
    ├─► OPEN_SOURCE / EXTRACT (Atomic Evidence Extraction)
    ├─► CROSS_CHECK (Multi-Origin Canonical Domain Verification)
    ├─► CHECK_HISTORY (SQLite Fingerprint Deduplication)
    └─► SELECT_STORY -> Grounded Social & Short Synthesis
            │
            ├─► Local 1080x1920 MP4 Video Compiler (Strictly NO subtitles)
            └─► Durable Review Queue (QUEUED_FOR_PUBLISHING)
                    │
                    ▼
Hermes Computer Use (restricted existing-profile session)
    ├─► Autonomous Post to X (Twitter)
    ├─► Autonomous Post to Threads
    └─► YouTube Studio PRIVATE Video Upload
```

---

## 🚀 Quickstart Guide

### 1. Installation

```powershell
# Clone the repository
git clone https://github.com/ChamanPrakashKanth/Agent-Flow.git
cd "Agent-Flow"

# Setup Python 3.10 virtual environment
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# Configure environment
Copy-Item .env.example .env
```

### 2. Start Local Model Engine

```powershell
ollama pull hermes3:3b
ollama serve
```

### 3. Prepare Chrome (One-Time Setup)

Open Chrome normally and confirm you are signed into **X**, **Threads**, and **YouTube Studio**. Hermes attaches to that existing profile; the legacy extension bridge is not part of the production publishing path.

---

## 🛠️ CLI Usage

```powershell
# Check the local model and Hermes runtime
news-agent doctor

# Run a single research cycle on a specific topic
news-agent --tools direct run --topic "quantum computing hardware"

# Publish any queued verified drafts immediately
news-agent publish-due

# Run the unit suite
python -m pytest

# Run the 30-task adversarial offline benchmark
news-agent benchmark
```

---

## ⚙️ Background Daemon & Windows Task Scheduler

To enable two autonomous startup-relative research and publishing cycles:

```powershell
# Register the Windows Scheduled Task (Runs automatically on startup)
powershell -ExecutionPolicy Bypass -File scripts/register_scheduled_task.ps1

# Start the background daemon immediately
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File scripts/start_news_agent.ps1
```

* **Automation Log**: [`logs/automation_worker.log`](logs/automation_worker.log)
* **Research Trajectories**: [`logs/trajectories.jsonl`](logs/trajectories.jsonl)
* **Publishing Queue**: [`data/review_queue.jsonl`](data/review_queue.jsonl)

---

## 📜 License

MIT License. Designed and implemented for fully local, verifiable, hardware-bounded agentic AI research.
