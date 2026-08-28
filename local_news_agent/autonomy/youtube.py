from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..schemas import ShortsDraft
from ..video.shorts_creator import ShortsCreator


class YouTubeDraftWriter:
    """Renders local artifacts only; it contains no browser/upload/publish path."""

    def __init__(self, root: Path, creator: ShortsCreator):
        self.root = root; self.creator = creator

    def save(self, topic: str, script: str, title: str, description: str, sources: list[str], keywords: list[str], run_id: str) -> dict[str, Any]:
        safe_topic = "-".join(topic.lower().split())[:50] or "topic"
        folder = self.root / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{safe_topic}"
        folder.mkdir(parents=True, exist_ok=True)
        draft = self.creator.create_short(ShortsDraft(title=title, description=description, script=script, visual_keywords=keywords), run_id)
        if draft.generated and draft.video_path:
            shutil.copy2(draft.video_path, folder / "video.mp4")
        (folder / "script.txt").write_text(script, encoding="utf-8")
        (folder / "title.txt").write_text(title, encoding="utf-8")
        (folder / "description.txt").write_text(description, encoding="utf-8")
        (folder / "sources.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
        metadata = {"topic": topic, "keywords": keywords, "duration_seconds": draft.duration_seconds, "rendered": draft.generated}
        (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (folder / "status.json").write_text(json.dumps({"status": "DRAFT", "publish_authorized": False}, indent=2), encoding="utf-8")
        return {"folder": str(folder.resolve()), "video": str((folder / "video.mp4").resolve()) if draft.generated else "", "status": "DRAFT", "publish_authorized": False}
