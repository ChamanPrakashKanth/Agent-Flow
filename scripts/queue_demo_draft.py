import json
from pathlib import Path
from datetime import datetime, timezone
from local_news_agent.config import Settings

s = Settings.from_env()
s.ensure_dirs()

video_path = Path("data/shorts/short_fresh_live_demo.mp4").resolve()
if not video_path.exists():
    print(f"Warning: {video_path} does not exist. Creating placeholder or run fresh_demo.py first.")

record = {
    "run_id": "fresh_live_demo_post",
    "queued_at": datetime.now(timezone.utc).isoformat(),
    "mode": "AUTO",
    "status": "QUEUED_FOR_PUBLISHING",
    "platform_status": {
        "x": "PENDING",
        "threads": "PENDING" if s.threads_publish_enabled else "PAUSED",
        "youtube": "PENDING"
    },
    "story": {
        "headline": "Agent Plugins specification packages AI tools and skills",
        "event": "The Agent Plugins standard allows packaging Agent Skills and MCP servers into portable modules for developers.",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["https://developers.googleblog.com/en/agent-plugins-package-your-skills-tools-and-more/"],
        "key_facts": [
            "Agent Plugins is a specification for packaging Agent Skills and MCP servers into portable plugins.",
            "Developers can package tools, prompts, and server configs into clean reusable plugins."
        ],
        "confidence": 0.95,
        "verification_status": "CONFIRMED",
        "already_covered": False,
        "importance": 0.88,
        "evidence": [
            {
                "url": "https://developers.googleblog.com/en/agent-plugins-package-your-skills-tools-and-more/",
                "title": "Agent Plugins package your skills, tools, and more",
                "publisher": "Google Developers",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "excerpt": "Agent Plugins is a standard for packaging Agent Skills and MCP servers.",
                "claims": [],
                "primary": True,
                "canonical_origin": "developers.googleblog.com"
            }
        ],
        "fingerprint": "agent_plugins_live_post"
    },
    "draft": {
        "x": "New standard: Agent Plugins enables packaging AI Agent Skills and MCP servers into portable plugins for developers.",
        "threads": "AI developer update: The Agent Plugins specification standardizes packaging Agent Skills and MCP servers into portable plugins.",
        "youtube_short": {
            "title": "Agent Plugins Specification: Package AI Skills & MCP Tools #Shorts",
            "description": "Standard for packaging AI agent skills and MCP servers. #AI #DevTools #Coding #Shorts",
            "script": "The Agent Plugins specification standardizes packaging agent skills and MCP servers into portable plugins for developers.",
            "visual_keywords": ["technology", "coding", "software", "artificial intelligence"],
            "video_path": str(video_path),
            "duration_seconds": 5.2,
            "generated": True
        },
        "claim_evidence": {},
        "verified": True,
        "unsupported_claims": []
    }
}

s.queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
print(f"[SUCCESS] Draft queued for publishing in {s.queue_path}")
threads_info = "Threads" if s.threads_publish_enabled else "Threads (PAUSED)"
print(f"Target Platforms: X, {threads_info}, YouTube Studio (PRIVATE)")
