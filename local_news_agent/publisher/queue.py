from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from ..schemas import Draft, Story


class Publisher:
    def __init__(self, mode: str, queue_path: Path, threads_publish_enabled: bool = True):
        self.mode = mode
        self.path = queue_path
        self.threads_publish_enabled = threads_publish_enabled
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def submit(self, run_id: str, story: Story, draft: Draft) -> str:
        short = draft.youtube_short
        short_ready = bool(short and short.generated and short.video_path)
        platform_status = {
            "x": "PENDING",
            "threads": "PENDING" if self.threads_publish_enabled else "PAUSED",
            "youtube": "DRAFT" if short_ready else "DRAFT_NOT_GENERATED",
        }
        initial_status = "QUEUED_FOR_PUBLISHING" if self.mode == "AUTO" else "PENDING_REVIEW"
        draft_artifacts = {
            "youtube_short": {
                "status": "DRAFT_READY" if short_ready else "DRAFT_NOT_GENERATED",
                "video_path": short.video_path if short else "",
                "upload_allowed": False,
                "required_visibility": "DRAFT_ONLY",
                "public_publish_allowed": False,
            }
        }
        record = {"run_id": run_id, "queued_at": datetime.now(timezone.utc).isoformat(), "mode": self.mode, "status": initial_status,
                  "platform_status": platform_status,
                  "draft_artifacts": draft_artifacts,
                  "story": story.model_dump(mode="json"), "draft": draft.model_dump(mode="json")}
        with queue_lock(self.path):
            with self.path.open("a", encoding="utf-8") as f: f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return "QUEUED_FOR_AUTO_PUBLISHING" if self.mode == "AUTO" else "QUEUED_FOR_REVIEW"




@contextmanager
def queue_lock(path: Path, timeout: float = 30.0):
    """Small cross-process lock that protects JSONL append/rewrite operations."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for queue lock: {lock_path}")
            time.sleep(0.1)
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
