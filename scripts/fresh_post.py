import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from local_news_agent.config import Settings
from local_news_agent.hermes.tools import DirectWebTools
from local_news_agent.research.service import story_from_evidence
from local_news_agent.writer.writer import write
from local_news_agent.model import LocalModel
from local_news_agent.schemas import AgentState
from local_news_agent.video.shorts_creator import ShortsCreator
from local_news_agent.publisher.hermes_browser import publish_one_due

def main():
    default_topic = "artificial intelligence, semiconductors, quantum computing, defense technology, military systems, mechanical engineering, physics"
    topic = sys.argv[1] if len(sys.argv) > 1 else default_topic
    print(f"=== 1. FETCHING FRESH NEWS FOR: '{topic}' ===")
    s = Settings.from_env()
    s.ensure_dirs()
    tools = DirectWebTools()
    results = tools.search(topic, limit=6)

    if not results:
        print("No fresh news found within the 48-hour window.")
        return 1

    for i, r in enumerate(results):
        print(f"  {i+1}. [{r.published_at}] {r.title} ({r.source})")

    best = results[0]
    print(f"\n=== 2. EXTRACTING EVIDENCE FOR: {best.title} ===")
    evidence = tools.extract(best.url)
    story = story_from_evidence(best, evidence)
    print(f"  Source: {evidence.publisher} ({evidence.canonical_origin})")
    print(f"  Key Facts ({len(story.key_facts)}): {story.key_facts}")

    print("\n=== 3. GENERATING DRAFTS WITH OLLAMA HERMES 3 ===")
    model = LocalModel(s)
    run_id = f"fresh_post_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    state = AgentState(task="fresh_research_and_post", topic=topic, run_id=run_id)
    draft = write(model, story, state)
    print(f"  [X]: {draft.x}")
    print(f"  [Threads (PAUSED)]: {draft.threads}")
    print(f"  [YouTube Title]: {draft.youtube_short.title if draft.youtube_short else 'N/A'}")

    video_path = ""
    if s.youtube_shorts_enabled and draft.youtube_short:
        print("\n=== 4. RENDERING VERTICAL SHORT (1080x1920 MP4) ===")
        sc = ShortsCreator(s)
        draft.youtube_short = sc.create_short(draft.youtube_short, run_id)
        video_path = draft.youtube_short.video_path
        print(f"  [SUCCESS] Short created: {video_path}")

    model.unload_model()
    draft.verified = True

    print("\n=== 5. QUEUING & PUBLISHING TO PLATFORMS ===")
    short_ready = bool(draft.youtube_short and draft.youtube_short.generated and video_path)
    record = {
        "run_id": run_id,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "mode": "AUTO",
        "status": "QUEUED_FOR_PUBLISHING",
        "platform_status": {
            "x": "PENDING",
            "threads": "PENDING" if s.threads_publish_enabled else "PAUSED",
            "youtube": "PENDING" if short_ready else "SKIPPED",
        },
        "story": story.model_dump(mode="json"),
        "draft": draft.model_dump(mode="json"),
    }
    
    with open(s.queue_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  Queued run '{run_id}' in {s.queue_path}")

    print("\n=== 6. EXECUTING LIVE POSTING ===")
    pub_result = publish_one_due(s, run_id=run_id)
    print(json.dumps(pub_result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
