# Agent Flow: Local News Agent with Budgeted Working Memory

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/LLM-Qwen%202.5%20Coder%203B-purple.svg)](https://ollama.com/)
[![Tests](https://img.shields.io/badge/tests-35%20passed-brightgreen.svg)]()
[![Benchmark](https://img.shields.io/badge/benchmark-100%25%20completion-success.svg)]()

A fully local, autonomous news-research agent powered by Ollama (`qwen2.5-coder:3b`), **Budgeted Working Memory** (concept graph consolidation & concept-importance-governed KV-cache decay), deterministic verification, and autonomous browser publishing.

Agent Flow autonomously discovers real-time news, compiles 1080x1920 MP4 Shorts, publishes verified text to **X** and **Threads**, and uploads Shorts to **YouTube Studio** strictly as **`PRIVATE`** within your signed-in Chrome profile.

---

## 🌟 Key Architecture Innovations

### 1. Concept-Importance-Governed Memory Decay
Standard LLM agent memory grows unboundedly ($O(N)$ KV-cache RAM), causing Out-Of-Memory (OOM) failures on hardware-constrained edge machines ($\le 6\text{ GB RAM}$). 

Agent Flow implements the **Budgeted Working Memory** framework where memory decay is an inverse function of **Concept Importance $I(c)$**:

$$\alpha_{\text{eff}}(c) = \frac{\alpha_{\text{base}}(c)}{\max(0.1, I(c))} \cdot \left(1 + 0.5 \cdot P\right)$$

$$R(c, \Delta t) = I(c) \cdot \exp\left(-\alpha_{\text{eff}}(c) \cdot \Delta t\right) + \beta \cdot \min(1.0, 0.25 \cdot \text{hits}_c)$$

* **High Importance ($I(c) \ge 2.5$)**: Confirmed atomic facts and primary evidence have $\alpha_{\text{eff}} \to 0$, resisting decay indefinitely.
* **Low Importance ($I(c) \le 0.6$)**: Ephemeral search snippets have $\alpha_{\text{eff}} \gg 0$, decaying rapidly and getting evicted during consolidation.
* **KV-Cache Invariance**: Keeps active context bounded under 4,096 tokens, cutting KV-cache allocation by **50%–75%** and enabling 100% GPU offload on 6GB VRAM.

```
Retention R(c, Δt) over Steps:
3.0 |
2.5 |====\==================== Confirmed Facts (I=2.5, α_eff ≈ 0.008 -> Persistent)
2.0 |     \
1.5 |      \-------\---------- Story Candidates (I=1.5, α_eff ≈ 0.10)
1.0 |               \
0.5 |                \-------- Search Snippets (I=0.6, α_eff ≈ 0.83 -> Fast Eviction)
0.0 |_________________________
    +------------------------> Δt (Steps)
```

### 2. Multi-Timescale Concept Graph ($G = (V, E)$)
* Connects active concept nodes with semantic similarity edges.
* Diffuses access reinforcement across neighbor nodes upon verification.
* Event-driven consolidation triggers when memory pressure $P = \frac{|V|}{B} > \tau$ ($\tau = 0.75$), compressing overflow subgraphs into latent `ConceptMemoryToken` tokens.

### 3. Strict Deterministic Verification Gate
* Requires $\ge 2$ independent canonical origins before marking a story as `CONFIRMED`.
* Single-source rumors and clickbait are safely resolved to `NO_POST` (first-class success outcome with zero ungrounded claims).

### 4. Autonomous Chrome Browser Bridge
* No social media API keys, developer accounts, or credit cards required.
* Local authenticated WebSocket relay (`ws://127.0.0.1:8765`) communicates directly with a Chrome MV3 Extension.
* Automatically posts to **X** and **Threads**, and uploads Shorts to **YouTube Studio** as **`PRIVATE`**.

### 5. 24/7 Silent Background Daemon
* Windows Task Scheduler integration (`Local Ollama News Agent`) starts at logon and runs in an infinite, non-blocking background loop.

---

## 📊 Evaluation & Benchmark Results

Evaluated against the 30-task offline adversarial fixture benchmark across five ablation levels:

| Level | Architecture Description | Task Completion (%) | Factual Accuracy | Unsupported Claims | Duplicate Rate | NO_POST Accuracy | Avg Tokens | Latency (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | Qwen 3B baseline alone | 53.3% | 0.50 | 0.733 | 0.10 | 0.417 | 1,800 | 18.0 |
| **B** | Qwen 3B + Web tools | 80.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,800 | 34.8 |
| **C** | Qwen 3B + Structured Planner | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,555 | 49.5 |
| **D** | Qwen 3B + Planner + Verifier | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,745 | 56.5 |
| **E** | **Full Architecture + Budgeted Memory** | **100.0%** | **1.00** | **0.000** | **0.00** | **1.000** | **1,745** | **56.5** |

Full benchmark data: [`evaluation/results/latest.json`](evaluation/results/latest.json).  
Detailed mathematical experiments: [`docs/BUDGETED_WORKING_MEMORY_EXPERIMENTS.md`](docs/BUDGETED_WORKING_MEMORY_EXPERIMENTS.md).

---

## 🏗️ System Workflow

```text
Scheduled Trigger / 24/7 Background Daemon
    │
    ▼
Budgeted Working Memory Manager
    │  ├─ Multi-Timescale Decay (SHORT: 0.50, MED: 0.15, LONG: 0.02)
    │  ├─ Dynamic Concept Importance I(c) Scaling
    │  └─ Event-Driven Consolidation (Pressure > 0.75)
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
Chrome Extension Bridge (ws://127.0.0.1:8765)
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
ollama pull qwen2.5-coder:3b
ollama serve
```

### 3. Load Chrome Extension (One-Time Setup)

1. Open **Google Chrome** and navigate to `chrome://extensions`.
2. Turn **ON** **Developer mode** (top-right toggle).
3. Click **Load unpacked** (top-left) and select:
   ```text
   C:\Users\user\Downloads\Agent Flow\chrome_extension
   ```
4. Confirm you are signed into **X**, **Threads**, and **YouTube Studio** in your Chrome profile.

---

## 🛠️ CLI Usage

```powershell
# Check full system health & bridge status
news-agent doctor

# Run a single research cycle on a specific topic
news-agent --tools direct run --topic "quantum computing hardware"

# Publish any queued verified drafts immediately
news-agent publish-due

# Run the 35-test unit suite
python -m pytest

# Run the 30-task adversarial offline benchmark
news-agent benchmark
```

---

## ⚙️ Background Daemon & Windows Task Scheduler

To enable fully autonomous, silent 24/7 background research and publishing:

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
