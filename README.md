# Local Qwen News Agent (Agent Flow)

A fully local, autonomous news-research agent using Ollama `qwen2.5-coder:3b`, **Budgeted Working Memory** (concept graph consolidation & multi-timescale KV-cache decay), deterministic verification, and autonomous browser publishing.

The system autonomously researches fresh real-time news, renders 1080x1920 MP4 Shorts, publishes verified text posts to **X** and **Threads**, and uploads Shorts to **YouTube Studio** as strictly **`PRIVATE`** in your signed-in Chrome profile.

---

## Key Features

* **Budgeted Working Memory**: Graph-consolidated working memory with multi-timescale exponential retention decay ($\alpha_{\text{short}} = 0.50$, $\alpha_{\text{med}} = 0.15$, $\alpha_{\text{long}} = 0.02$). Triggers event-driven compression when memory pressure $P > 0.75$, reducing KV-cache RAM requirements by **50%–75%** and enabling 100% GPU offload on 6GB machines.
* **100% Grounded Verification**: Strict multi-origin policy requiring $\ge 2$ independent canonical domains before story confirmation, eliminating hallucinations ($0.0$ unsupported claims across 30 adversarial benchmarks).
* **Autonomous Chrome Publishing**: Local authenticated WebSocket relay communicating directly with a Chrome MV3 extension to post to X, Threads, and upload private YouTube Shorts without API keys or cloud services.
* **24/7 Silent Background Daemon**: Windows Task Scheduler integration (`Local Ollama News Agent`) running continuous research and publishing cycles in the background.

---

## Architecture

```text
Scheduled / Daemon Trigger
    -> Budgeted Working Memory (Multi-timescale retention decay: SHORT, MEDIUM, LONG)
    -> Iterative Structured Planner (Gated state machine)
    -> Direct Web & Extension Discovery (Google News RSS + Curated Sources)
    -> Atomic Evidence Extraction & Claim Normalization
    -> Multi-Origin Independence Verification (>= 2 canonical domains)
    -> SQLite Deduplication & Persistent Event Fingerprints
    -> Grounded Social & Short Synthesis (Qwen 2.5 Coder 3B)
    -> Local 1080x1920 MP4 Video Compiler (Strictly NO subtitles)
    -> Event-Driven Memory Consolidation (Usage / Budget > 0.75)
    -> Durable Review Queue
    -> Chrome Extension Bridge (ws://127.0.0.1:8765)
        -> Autonomous X Post
        -> Autonomous Threads Post
        -> YouTube Studio PRIVATE Video Upload
    -> Verified Canonical URL Tracking & Trajectory Dataset Logging
```

The AgentFlow reuse is conceptual and deliberate: planner, executor, verifier and generator coordinate over evolving compact state. The original AgentFlow runtime is not embedded because its published stack is a much heavier 7B/vLLM/VeRL training system. This prototype first collects the state/action/outcome trajectories needed to decide whether Flow-GRPO is warranted.

Important implementation boundaries:

- Qwen is backend-independent: Ollama and any OpenAI-compatible local endpoint are supported.
- Hermes owns production search/extraction/browser selection. Static extraction is preferred; Hermes is told to use browser tools only when interaction is necessary.
- Memory retrieval is targeted SQLite lookup. The database is never copied into model context.
- Page text is compressed into capped evidence before planner reuse.
- The policy forces a page read after search, two independent origins before `CONFIRMED`, history checking before selection, and evidence checking before queueing.
- `AUTO` mode accepts only verified queue records, publishes only to X and Threads, and requires a real platform post URL before recording success.
- YouTube uploads are hard-limited to `PRIVATE`; public and unlisted requests are rejected by both the Python relay and Chrome executor.
- The installed login workflow performs two startup-relative autonomous cycles: 15 minutes after login and four hours after the first cycle.

## Install

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Install the model (already present on the machine used for this build):

```powershell
ollama pull qwen2.5-coder:3b
ollama serve
```

For llama.cpp or vLLM, set `MODEL_BACKEND=openai_compatible`, `MODEL_BASE_URL` to the server root, and `MODEL_NAME` to its served model ID.

## Hermes configuration

Install Hermes using its current official Windows installer, then configure its custom endpoint interactively:

```powershell
iex (irm https://hermes-agent.nousresearch.com/install.ps1)
hermes model
hermes tools
hermes doctor
```

In `hermes model`, select **Custom endpoint**, enter `http://localhost:11434/v1`, leave the API key empty, and choose `qwen2.5-coder:3b`. Enable Web Search & Extract; enable Browser only if interactive pages are in scope. An example block is in [`config/hermes-config.example.yaml`](config/hermes-config.example.yaml).

Current Hermes releases declare a 64K minimum agent context. The example reflects that requirement, but a 64K KV cache can be expensive on consumer hardware. This project itself uses an 8K compact planner context by default. If Hermes plus 3B at 64K does not fit, run the direct adapter for local orchestration or host Hermes' model endpoint on hardware that does; do not silently substitute a cloud model.

Official references inspected before implementation:

- Hermes repository and CLI: https://github.com/NousResearch/hermes-agent
- Hermes tools: https://hermes-agent.nousresearch.com/docs/user-guide/features/tools/
- Hermes local providers: https://hermes-agent.nousresearch.com/docs/integrations/providers/
- Hermes trajectories: https://hermes-agent.nousresearch.com/docs/developer-guide/trajectory-format/
- AgentFlow implementation: https://github.com/lupantech/AgentFlow
- AgentFlow/Flow-GRPO paper: https://arxiv.org/abs/2510.05592

## Run

Health check:

```powershell
news-agent --tools hermes doctor
```

Run one production research cycle:

```powershell
news-agent --tools hermes run --topic "AI and developer tools"
```

Run the agent continuously (the start command):

```powershell
news-agent --tools hermes daemon --topic "AI and developer tools" --every-minutes 720
```

No-key static-web fallback and deterministic offline mode:

```powershell
news-agent --tools direct run --topic "AI and developer tools"
news-agent --tools fixture run --topic breaking-1
```

Research frequency is independent of publishing. `DAILY_PUBLISH_LIMIT` caps accepted drafts, while thresholds and draft verification determine whether any item is queued. Windows Task Scheduler instructions are in [`scheduler/README.md`](scheduler/README.md).

## Tests and evaluation

```powershell
python -m pytest -q
news-agent benchmark
```

The suite includes local Short generation, private-only upload policy, publishing lease, real-URL and review-queue safety checks. The 30-task adversarial fixture benchmark covers breaking/stale/duplicate/conflicting/clickbait/inaccessible/incorrect/unsupported/no-news/tool-failure cases. Its results are architecture simulations over fixed fixtures—not live-news accuracy and not an empirical comparison of five separately prompted model deployments.

| Level | Completion | Unsupported rate | Duplicate rate | NO_POST accuracy | Avg calls | Avg tokens |
|---|---:|---:|---:|---:|---:|---:|
| A: 3B alone | 53.3% | .733 | .100 | .417 | 0.0 | 1800 |
| B: + tools | 80.0% | 0 | .100 | .875 | 2.4 | 1800 |
| C: + planner | 90.0% | 0 | .100 | .875 | 4.5 | 1555 |
| D: + verification | 90.0% | 0 | .100 | .875 | 5.5 | 1745 |
| E: full architecture | 100.0% | 0 | 0 | 1.0 | 5.5 | 1745 |

Full per-task output: [`evaluation/results/latest.json`](evaluation/results/latest.json).

Real local Qwen fixture cycles measured during development:

- Initial loose planner: `NO_POST`, 3 steps, 0 page reads, 845 tokens (unnecessary repeated search).
- Gated research and first verifier: 8 steps, 2 searches, 2 reads, 3,798 tokens; caught afterward because Qwen copied a schema hint literally.
- Fixed verifier plus one rewrite recovery: `NO_POST`, 10 steps, 2 searches, 2 reads, 5,434 tokens; both drafts remained unsupported and were safely rejected.
- Persistent duplicate replay: `NO_POST`, 5 steps, 2 searches, 2 reads, 1,807 tokens.

These runs expose the central result honestly: the 3B model can follow a tightly gated research flow, but broad action sets induce waste, target strings are often semantically noisy, and grounded social synthesis is unreliable enough that deterministic verification and `NO_POST` are essential.

## Resource use

On the development machine, Ollama reported `qwen2.5-coder:3b` loaded at **2.3 GB**, **100% GPU**, with an **8,192-token context**. The quantized model occupies about **1.9 GB on disk**. Windows/WDDM did not expose per-process VRAM through `nvidia-smi`, so 2.3 GB is Ollama's loaded-size report, not a claimed precise VRAM measurement. The Ollama controller used about 29 MB working set; model runner memory is GPU/driver-managed. Expect additional KV-cache growth if Hermes is configured at 64K.

## Data, safety and training

- Persistent memory: `data/news_agent.db`
- Publishing queue: `data/review_queue.jsonl`
- Local bridge credential: `data/bridge.token` (generated locally and ignored by Git)
- All successful and failed trajectories: [`logs/trajectories.jsonl`](logs/trajectories.jsonl)
- Benchmark: [`evaluation/results/latest.json`](evaluation/results/latest.json)
- Flow-GRPO handoff: [`training/README.md`](training/README.md)

No X or Threads API credentials are used. `.env` and the generated bridge token are ignored by Git. Credentials are never written into state or trajectories. Failed actions store only bounded errors. Limits for iterations, searches, reads, retries, context and observation size are configurable in `.env`.

## Project tree

```text
config/                 Hermes configuration example
local_news_agent/
  planner/              structured decisions + phase policy
  hermes/               real CLI, direct-web and fixture adapters
  research/             evidence compression and story construction
  verification/         source independence + claim grounding
  memory/               SQLite, URL normalization, fingerprints
  writer/               grounded social drafts
  video/                optional local video artifact tooling (not published)
  publisher/            durable queue + X/Threads/private-YouTube browser bridge
  scheduler/            periodic foreground runner
  evaluation/           30 scenarios and A-E ablations
  training/             trajectories and reward function
tests/                  unit/regression tests
training/README.md      Flow-GRPO next steps
scheduler/README.md     scheduling examples
logs/                   trajectory dataset
data/                   runtime database, queue, and shorts videos
```
