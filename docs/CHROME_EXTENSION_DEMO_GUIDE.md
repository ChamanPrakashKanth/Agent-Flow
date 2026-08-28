# Chrome Extension & Hermes Live Demo Guide

This guide details how to load the Chrome Extension, connect it to the local agent bridge, and observe real-time browser actions (Google News searches, DOM page extractions, and automated posting).

---

## 1. Architecture Overview

```
+----------------------------------------------------------------+
|  Local News Agent (Python 3.10+ & Ollama Hermes 3 Llama 3.2 3B)  |
|  - Aggressive KV-Cache Compression (q4_0 + Flash Attention)    |
|  - Budgeted Working Memory (Bounded Graph Decay: τ=0.60, B=8)  |
+-------------------------------+--------------------------------+
                                |
                                v WebSocket (ws://127.0.0.1:8765)
+-------------------------------+--------------------------------+
|  Extension Relay Server (scripts/start_extension_bridge.py)   |
+-------------------------------+--------------------------------+
                                |
                                v (Chrome Runtime Bridge)
+-------------------------------+--------------------------------+
|  Chrome Extension (chrome_extension/ - Manifest V3)           |
|  - Active User Chrome Profile (X, Threads, YouTube Studio)     |
|  - Real-time News RSS & Search Tab Automation                  |
|  - DOM Page Extraction & Canonical Verification                |
+----------------------------------------------------------------+
```

---

## 2. Setup Instructions

### Step 1: Start the Local Bridge Relay
Ensure the relay server is running on port `8765`:
```powershell
.venv\Scripts\python scripts/start_extension_bridge.py
```
*(The bridge creates a secure token at `data/bridge.token` and listens on `ws://127.0.0.1:8765`)*.

---

### Step 2: Load the Extension in Google Chrome

1. Open **Google Chrome** and go to:
   ```
   chrome://extensions
   ```
2. Toggle **Developer mode** **ON** in the top right corner.
3. Click **Load unpacked** in the top left corner.
4. Select the project's extension folder:
   ```
   c:\Users\user\Downloads\Agent Flow\chrome_extension
   ```
5. *(If already loaded, click the **Reload** 🔄 button on the **Local News Agent - Codex Chrome Bridge** extension card)*.

---

### Step 3: Verify Connection Status

Run the health check script:
```powershell
.venv\Scripts\python scripts/check_health.py
```

Expected Output:
```text
LOCAL NEWS AGENT HEALTH
Model: ollama / hermes3:3b
Publishing: AUTO; limit=2
X: https://x.com/ChamanKant44703
Threads: https://www.threads.com/@chamanprakashkanth
SQLite: ok
Chrome bridge: extension connected
Scheduled task: Ready
```

---

## 3. Running Live Demos

### Demo A: Live Research & Extraction in Chrome
Run a live news discovery cycle using the Chrome Extension as the tool backend:
```powershell
.venv\Scripts\python -m local_news_agent.cli --tools extension run --topic "artificial intelligence quantum computing"
```
**What happens in Chrome:**
- Chrome executes fresh Google News queries using extension permissions.
- Relevant article URLs are opened in background/foreground tabs for DOM content extraction.
- Budgeted Working Memory limits active concepts to $\le 4$ items and decays ephemeral search scraps with $\alpha_{\text{short}} = 0.75$.

---

### Demo B: Hermes with Chrome Extension Tools
Run research with Hermes orchestrating Chrome extension tools:
```powershell
.venv\Scripts\python -m local_news_agent.cli --tools hermes run --topic "semiconductors and chip design"
```
**What happens:**
- Hermes Agent CLI interacts with `ChromeExtensionWebTools` to gather fresh 48-hour evidence.

---

### Demo C: Automated Publishing
Queue a verified test draft and execute publishing:
```powershell
# 1. Queue a sample verified draft
.venv\Scripts\python scripts/queue_demo_draft.py

# 2. Trigger publishing through Chrome
.venv\Scripts\python -m local_news_agent.cli publish-due
```
**What happens in Chrome:**
- Chrome navigates to **X** (`https://x.com/compose/post`) and posts the verified text.
- Chrome navigates to **Threads** (`https://www.threads.net/`) and submits the post.
- Chrome opens **YouTube Studio** (`https://studio.youtube.com/`) and uploads the MP4 Short strictly as **`PRIVATE`**.
- Post URLs are verified on profile pages and logged to `data/news_agent.db`.

---

## 4. Troubleshooting

| Issue | Cause | Fix |
| :--- | :--- | :--- |
| `Chrome bridge: offline` | Relay server is not running. | Run `.venv\Scripts\python scripts/start_extension_bridge.py`. |
| `extension disconnected` | Extension not loaded or needs refresh. | Open `chrome://extensions` and click the **Reload** 🔄 button on the extension card. |
| `Ollama unavailable` | Ollama service is stopped. | Run `ollama serve` or start Ollama from the Windows start menu. |
| `BRIDGE_TOKEN_MISSING` | Token file was deleted. | Restart `scripts/start_extension_bridge.py` to regenerate `data/bridge.token`. |
