import json
import sys
from local_news_agent.config import Settings

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from local_news_agent.hermes.tools import DirectWebTools
from local_news_agent.research.service import story_from_evidence
from local_news_agent.writer.writer import write
from local_news_agent.model import LocalModel
from local_news_agent.schemas import AgentState
from local_news_agent.video.shorts_creator import ShortsCreator

print("=== FETCHING STRICTLY FRESH REAL-TIME NEWS (LAST 24-48 HOURS) ===")
s = Settings.from_env()
tools = DirectWebTools()
results = tools.search("AI agents developer tool coding release", limit=5)

for i, r in enumerate(results):
    print(f"{i+1}. [{r.published_at}] {r.title} ({r.source})")

if not results:
    print("No fresh news found within the 48-hour window.")
    exit(1)

best = results[0]
print(f"\nSelected Freshest Article: [{best.published_at}] {best.title}")
evidence = tools.extract(best.url)
story = story_from_evidence(best, evidence)
print(f"Extracted {len(story.key_facts)} key facts from {evidence.canonical_origin}.")

print("\n=== GENERATING VERIFIED DRAFTS WITH OLLAMA HERMES 3 LLAMA 3.2 3B ===")
model = LocalModel(s)
state = AgentState(task="fresh_demo", topic="AI developer tools", run_id="fresh_live_demo")
draft = write(model, story, state)
print("1. X Post:", draft.x)
print("2. Threads Post:", draft.threads)
print("3. YouTube Short Title:", draft.youtube_short.title)

print("\n=== COMPILING LOCAL DRAFT-ONLY SHORT (NO UPLOAD, NO SUBTITLES) ===")
sc = ShortsCreator(s)
draft.youtube_short = sc.create_short(draft.youtube_short, "fresh_live_demo")
print(f"[SUCCESS] Rendered 1080x1920 MP4 Short: {draft.youtube_short.video_path}")
print(f"Duration: {draft.youtube_short.duration_seconds}s | Subtitles: Strictly NONE")
print("Publishing: DISABLED (local draft artifact only)")
