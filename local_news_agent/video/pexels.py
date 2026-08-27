from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import httpx

logger = logging.getLogger(__name__)


class PexelsClient:
    """Client for Pexels Video Search API."""

    BASE_URL = "https://api.pexels.com/videos"

    def __init__(self, api_key: str = "", timeout: float = 20.0):
        self.api_key = api_key.strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def search_portrait_videos(self, query: str, per_page: int = 5) -> list[dict[str, Any]]:
        """Search Pexels for vertical / portrait videos matching query."""
        if not self.is_configured:
            return []
        headers = {"Authorization": self.api_key}
        params = {"query": query, "orientation": "portrait", "per_page": per_page, "size": "medium"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.BASE_URL}/search", headers=headers, params=params)
                if res.status_code != 200:
                    logger.warning("Pexels API error %d: %s", res.status_code, res.text[:200])
                    return []
                data = res.json()
                return data.get("videos", [])
        except Exception as exc:
            logger.warning("Failed to query Pexels API: %s", exc)
            return []

    def get_best_video_url(self, video_data: dict[str, Any]) -> str | None:
        """Select the highest quality portrait MP4 file link."""
        files = video_data.get("video_files", [])
        if not files:
            return None
        # Prefer HD portrait MP4s
        candidates = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
        if not candidates:
            candidates = [f for f in files if f.get("link")]
        if not candidates:
            return None
        # Sort by resolution (prefer height 1920 or 1080)
        candidates.sort(key=lambda f: (f.get("height", 0) >= 1280, f.get("height", 0)), reverse=True)
        return candidates[0]["link"]

    def download_video(self, url: str, target_path: Path) -> bool:
        """Download video file to target path."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return False
                    with open(target_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            f.write(chunk)
            return target_path.exists() and target_path.stat().st_size > 1000
        except Exception as exc:
            logger.warning("Failed to download Pexels video %s: %s", url, exc)
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            return False

    def fetch_footage_for_keywords(self, keywords: list[str], output_dir: Path, max_clips: int = 3) -> list[Path]:
        """Fetch multiple distinct portrait clips for the given keyword list."""
        if not self.is_configured or not keywords:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        seen_video_ids: set[int] = set()

        for kw in keywords:
            if len(downloaded) >= max_clips:
                break
            videos = self.search_portrait_videos(kw, per_page=4)
            for v in videos:
                vid_id = v.get("id")
                if not vid_id or vid_id in seen_video_ids:
                    continue
                seen_video_ids.add(vid_id)
                url = self.get_best_video_url(v)
                if not url:
                    continue
                dest = output_dir / f"pexels_{vid_id}.mp4"
                if dest.exists() and dest.stat().st_size > 1000:
                    downloaded.append(dest)
                elif self.download_video(url, dest):
                    downloaded.append(dest)
                if len(downloaded) >= max_clips:
                    break

        return downloaded
