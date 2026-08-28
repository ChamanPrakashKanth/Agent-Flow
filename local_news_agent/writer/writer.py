from __future__ import annotations

import json
from ..model import LocalModel, first_json
from ..schemas import Draft, ShortsDraft, Story

SYSTEM = """Write original, sober social content using ONLY supplied facts. No invented numbers, quotes, certainty, or details.
Return one JSON object with:
- "x": string post (1-280 characters)
- "threads": string explanatory post (1-900 characters)
- "youtube_short": object with:
    - "title": string (engaging title, <= 70 characters, ending with #Shorts)
    - "description": string (brief summary and hashtags)
    - "script": string (spoken voiceover text, approx 40-70 words, fast-paced, strictly based on facts)
    - "visual_keywords": list of 3-5 short visual search terms for stock footage (e.g. ["technology", "coding", "server", "artificial intelligence"])
Never put evidence URLs in prose."""


def write(model: LocalModel, story: Story, token_sink=None) -> Draft:
    facts = story.key_facts[:8] if story.key_facts else [story.event or story.headline]
    payload = {"headline": story.headline, "event": story.event, "verified_facts": facts, "sources": story.sources}
    reply = model.chat(SYSTEM, json.dumps(payload, ensure_ascii=False), json_mode=True, temperature=.25)
    if token_sink:
        token_sink.tokens_prompt += reply.prompt_tokens; token_sink.tokens_completion += reply.completion_tokens
    data = first_json(reply.text)
    x = str(data.get("x", "")).strip()[:280] or story.headline[:280]
    threads = str(data.get("threads", "")).strip()[:900] or f"{story.headline}. {story.event or ''}".strip()[:900]

    short_raw = data.get("youtube_short")
    if isinstance(short_raw, dict):
        short_title = str(short_raw.get("title", f"{story.headline[:60]} #Shorts"))[:100]
        short_desc = str(short_raw.get("description", story.headline))[:500]
        short_script = str(short_raw.get("script", "")).strip() or " ".join(facts[:3])
        keywords = [str(k).strip() for k in short_raw.get("visual_keywords", []) if str(k).strip()]
        if not keywords:
            keywords = [w for w in story.headline.split() if len(w) > 4][:4] or ["technology", "news"]
    else:
        short_title = f"{story.headline[:60]} #Shorts"
        short_desc = f"{story.headline}\n\n#News #Tech #Shorts"
        short_script = f"{story.headline}. {' '.join(facts[:2])}"
        keywords = [w for w in story.headline.split() if len(w) > 4][:4] or ["technology", "news"]

    shorts_draft = ShortsDraft(
        title=short_title,
        description=short_desc,
        script=short_script,
        visual_keywords=keywords,
    )
    return Draft(x=x, threads=threads, youtube_short=shorts_draft)
