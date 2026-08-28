# Agent Flow: Local News Agent with Budgeted Working Memory

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LLM Backend](https://img.shields.io/badge/LLM-Ollama%20%7C%20llama.cpp-purple.svg)](https://github.com/ggerganov/llama.cpp)
[![Models](https://img.shields.io/badge/Models-Hermes%203%20%7C%20Qwen%202.5%20Coder%203B-blueviolet.svg)]()
[![Tests](https://img.shields.io/badge/tests-65%20passed-brightgreen.svg)]()
[![Benchmark](https://img.shields.io/badge/benchmark-100%25%20completion-success.svg)]()

A fully local, hardware-bounded autonomous news-research agent supporting both **Ollama** (`hermes3:3b`) and **llama.cpp** (`qwen2.5-coder-3b-instruct`), **Budgeted Working Memory (BMW)**, deterministic multi-origin verification, automatic **Pexels vertical stock footage** integration, and direct publishing through the user's signed-in Chrome profile.

Agent Flow autonomously discovers real-time news across technical domains, compiles clean 1080x1920 vertical MP4 Shorts, publishes verified text to **X** and **Threads**, and saves YouTube Shorts drafts safely with deterministic boundaries.

---

## 🌟 Key Architecture Innovations

### 1. Dual Local Engine Architecture: Ollama & llama.cpp (Qwen 2.5 Coder 3B)
* **llama.cpp Server Integration**: Native OpenAI-compatible adapter (`QwenLlamaCppModel`) connecting to `llama-server` on `http://127.0.0.1:8080`, supporting strict JSON formatting and prompt self-repair.
* **Ollama Runtime**: Hermes 3 Llama 3.2 3B engine with `q4_0` KV cache compression and Flash Attention for sub-4GB VRAM setups.

### 2. Concept-Importance-Governed Memory Decay (BMW)
Long-running agents accumulate unbounded observations. Agent Flow bounds context through the **Bounded Memory Window (BMW)** framework where memory decay is governed by **Concept Importance $I(c)$**:

$$\alpha_{\text{eff}}(c) = \frac{\alpha_{\text{base}}(c)}{\max(0.1, I(c))} \cdot \left(1 + 0.75 \cdot P\right)$$

$$R(c, \Delta t) = I(c) \cdot \exp\left(-\alpha_{\text{eff}}(c) \cdot \Delta t\right) + \beta \cdot \min(1.0, 0.25 \cdot \text{hits}_c)$$

* **High Importance ($I(c) \ge 2.5$)**: Primary facts and cross-verified claims resist decay indefinitely.
* **Low Importance ($I(c) \le 0.6$)**: Ephemeral search snippets decay rapidly and are evicted during consolidation.
* **KV Pressure Tracking**: Monitors working memory density and triggers event-driven summarization when pressure exceeds threshold $\tau = 0.60$.

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

### 3. Forecast Controller & Calibrated Execution
* Autonomous execution loop (`observe → plan → validate → execute → score`) with loop-detection guards that halt on repetitive steps.
* Calibrated uncertainty controller that clamps guidance and requests human review when encountering repeated execution anomalies.

### 4. Pexels Stock Video & Local 1080x1920 Short Compiler
* **Pexels Video Search API**: Automatically queries and downloads high-definition portrait stock clips matching extracted topic keywords.
* **Offline Ambient Fallback**: Smoothly generates a dark gradient background if no API key or network connection is available.
* **Local SAPI / eSpeak Audio**: Generates narration audio locally without cloud TTS dependencies.

### 5. Strict Deterministic Verification Gate
* Requires $\ge 2$ independent canonical origins before marking a story as `CONFIRMED`.
* Single-source rumors and clickbait are safely resolved to `NO_POST` (first-class success outcome with zero ungrounded claims).

### 6. Autonomous Chrome Publishing & Safe YouTube Drafts
* Authenticated localhost relay connects directly to the user's normal Chrome profile extension.
* Posts to **X** and **Threads** without cloud developer API fees.
* YouTube outputs are bundled into local artifact packages (`drafts/youtube/`) with `publish_authorized: false`.

---

## 📊 Evaluation & Benchmark Results

Evaluated against the 30-task offline adversarial fixture benchmark across five ablation levels:

| Level | Architecture Description | Task Completion (%) | Factual Accuracy | Unsupported Claims | Duplicate Rate | NO_POST Accuracy | Avg Tokens | Latency (ms) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | Hermes 3 (Llama 3.2 3B) baseline alone | 53.3% | 0.50 | 0.733 | 0.10 | 0.417 | 1,800 | 18.0 |
| **B** | Hermes 3 (Llama 3.2 3B) + Web tools | 80.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,800 | 34.8 |
| **C** | Hermes 3 (Llama 3.2 3B) + Structured Planner | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,555 | 49.5 |
| **D** | Hermes 3 (Llama 3.2 3B) + Planner + Verifier | 90.0% | 1.00 | 0.000 | 0.10 | 0.875 | 1,745 | 56.5 |
| **E** | **Offline policy simulation with persistent deduplication** | **100.0%** | **1.00** | **0.000** | **0.00** | **1.000** | **1,745** | **56.5** |

Full test suite: **65 passing unit tests** across harness, memory, policy, and toolcaller components.

---

## 🏗️ System Workflow

```text
User / Scheduled Trigger / run_qwen.bat
    │
    ▼
Bounded Memory Window (BMW)
    │  ├─ Dynamic Concept Importance I(c) Scaling
    │  ├─ Multi-Timescale Decay
    │  └─ Event-Driven Consolidation (Pressure > 0.60, B = 8)
    ▼
Autonomous Execution Controller (Qwen 2.5 Coder / Hermes 3)
    │
    ├─► SEARCH_WEB (Google News RSS / Curated Sources)
    ├─► EXTRACT_PAGE (Atomic Sourced Evidence Extraction)
    ├─► CROSS_CHECK (Multi-Origin Canonical Domain Verification)
    ├─► DRAFT_X / THREADS (Grounded Social Copy)
    └─► SHORT_SYNTHESIS
            │
            ├─► Pexels Portrait Footage Fetcher (or Ambient Fallback)
            ├─► Local SAPI / eSpeak Narration Compiler
            ├─► 1080x1920 MP4 Video Stitcher
            └─► Durable Draft Package (drafts/youtube/)
```

---

## 🚀 Quickstart & One-Click Execution

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

### 2. Configure Environment (`.env`)

Edit [`.env`](.env) with your preferences:
```env
# Optional Pexels stock video key for vertical Shorts
PEXELS_API_KEY=your_pexels_key_here

# Social profiles for Chrome extension publishing
X_PROFILE_URL=https://x.com/your_account
THREADS_PROFILE_URL=https://www.threads.com/@your_account
```

---

### 3. Running with Qwen 2.5 Coder & `llama.cpp`

#### One-Click Batch Launcher:
Double-click [`run_qwen.bat`](run_qwen.bat) or run from PowerShell:
```powershell
.\run_qwen.bat "quantum computing, artificial intelligence"
```

#### Manual Steps:
```powershell
# 1. Start llama-server (Window 1)
.\tools\llama.cpp\llama-server.exe -m "C:\models\qwen2.5-coder-3b-instruct-q4_k_m.gguf" -c 2048 --port 8080 --threads 4

# 2. Run Qwen Autonomous Agent (Window 2)
.\.venv\Scripts\python.exe -m local_news_agent.cli qwen-run --browser direct --topic "AI, quantum mechanics, defence systems"

# 3. Inspect run metrics & trajectories
.\.venv\Scripts\python.exe -m local_news_agent.cli inspect-run <run_id>
```

---

### 4. Running with Ollama (`hermes3:3b`)

```powershell
# 1. Start Ollama
ollama pull hermes3:3b
ollama serve

# 2. Run research & verification cycle
.\.venv\Scripts\python.exe -m local_news_agent.cli --tools custom run --topic "artificial intelligence, semiconductors"

# 3. Publish due verified drafts
$env:PUBLISH_MODE="AUTO"; .\.venv\Scripts\python.exe -m local_news_agent.cli publish-due
```

---

### 5. Interactive Control Menu

Launch the unified control panel:
```powershell
.\run_agent.bat
```

---

## 🛠️ Diagnostics & Tests

```powershell
# Run system doctor
.\.venv\Scripts\python.exe -m local_news_agent.cli doctor

# Run health check
.\.venv\Scripts\python.exe scripts/check_health.py

# Run full unit test suite (65 tests)
.\.venv\Scripts\python.exe -m pytest

# Run 30-task adversarial benchmark
.\.venv\Scripts\python.exe -m local_news_agent.cli benchmark
```

---

## 🔐 Safety & Privacy Notes

* All LLM inferences run locally on device via `llama.cpp` or Ollama.
* Social publishing uses your existing signed-in Chrome profile via local token-authenticated WebSocket relay (`127.0.0.1:8765`); browser cookies and credentials are never stored or transmitted.
* YouTube output is strictly local draft-only under `drafts/youtube/` with `publish_authorized: false`.

---

## 📜 License

MIT License. Designed and implemented for fully local, verifiable, hardware-bounded agentic AI research.
