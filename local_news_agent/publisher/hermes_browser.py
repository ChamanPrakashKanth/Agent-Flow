from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..config import Settings
from .hermes_computer_use import HermesComputerUsePublisher
from .queue import queue_lock


REQUIRED_PLATFORMS = ("x", "threads", "youtube")
LEASE_DURATION = timedelta(minutes=10)


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _save(path: Path, records: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records), encoding="utf-8")
    temporary.replace(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _expired_lease(record: dict[str, Any], now: datetime) -> bool:
    raw = record.get("publish_lease_until")
    if not raw:
        return True
    try:
        return datetime.fromisoformat(str(raw)) <= now
    except ValueError:
        return True


def _eligible(record: dict[str, Any], now: datetime) -> bool:
    if record.get("draft", {}).get("verified") is not True:
        return False
    status = record.get("status")
    if status in {"QUEUED_FOR_PUBLISHING", "PARTIALLY_POSTED"}:
        return True
    return status == "PUBLISHING" and _expired_lease(record, now)


def _verified_url(platform: str, value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    host = parsed.hostname or ""
    if parsed.scheme != "https":
        return False
    if platform == "x":
        return host == "x.com" and "/status/" in parsed.path
    if platform == "threads":
        return host in {"threads.com", "www.threads.com"} and "/post/" in parsed.path
    return (
        (host in {"youtube.com", "www.youtube.com"} and parsed.path == "/watch" and bool(parsed.query))
        or (host == "youtu.be" and len(parsed.path.strip("/")) >= 6)
        or (host == "studio.youtube.com" and "/video/" in parsed.path)
    )


def publish_one_due(settings: Settings) -> dict[str, Any]:
    """Claim and publish one verified record through Hermes Computer Use."""
    settings.ensure_dirs()
    now = _utc_now()
    claim_id = uuid.uuid4().hex

    with queue_lock(settings.queue_path):
        records = _records(settings.queue_path)
        candidate_index = next((index for index, item in enumerate(records) if _eligible(item, now)), None)
        if candidate_index is None:
            return {"status": "NO_VERIFIED_DRAFT"}
        record = records[candidate_index]
        statuses = record.setdefault("platform_status", {})
        for platform in REQUIRED_PLATFORMS:
            statuses.setdefault(platform, "PENDING")
        record["status"] = "PUBLISHING"
        record["publish_claim_id"] = claim_id
        record["publish_started_at"] = now.isoformat()
        record["publish_lease_until"] = (now + LEASE_DURATION).isoformat()
        _save(settings.queue_path, records)

    try:
        if settings.tool_backend == "hermes":
            try:
                results = HermesComputerUsePublisher(settings).publish_all(record)
            except Exception:
                from .extension_bridge import ChromeExtensionPublisher
                results = ChromeExtensionPublisher().publish_all(record)
        else:
            from .extension_bridge import ChromeExtensionPublisher
            results = ChromeExtensionPublisher().publish_all(record)
    except Exception as exc:
        results = {platform: {"status": "FAILED", "url": "", "message": type(exc).__name__}
                   for platform in REQUIRED_PLATFORMS if record["platform_status"].get(platform) != "POSTED"}

    if not isinstance(results, dict):
        results = {}

    report: dict[str, Any] = {"run_id": record.get("run_id"), "platforms": {}}

    for platform in REQUIRED_PLATFORMS:
        expected_status = "PRIVATE" if platform == "youtube" else "POSTED"
        if record["platform_status"].get(platform) == expected_status:
            report["platforms"][platform] = {
                "status": expected_status,
                "url": record.get("post_urls", {}).get(platform, ""),
            }
            continue
        result = results.get(platform, {})
        url = str(result.get("url", ""))
        success = result.get("status") == expected_status and _verified_url(platform, url)
        record["platform_status"][platform] = expected_status if success else "FAILED"
        if success:
            record.setdefault("post_urls", {})[platform] = url
        report["platforms"][platform] = {
            "status": record["platform_status"][platform],
            "url": url if success else "",
            "message": str(result.get("message", ""))[:500],
        }

    with queue_lock(settings.queue_path):
        latest = _records(settings.queue_path)
        target = next((item for item in latest if item.get("run_id") == record.get("run_id")), None)
        if target is None:
            raise RuntimeError("claimed queue record disappeared")
        if target.get("publish_claim_id") != claim_id:
            raise RuntimeError("publishing lease ownership changed")
        target["platform_status"] = record["platform_status"]
        target["post_urls"] = record.get("post_urls", {})
        complete = (
            record["platform_status"].get("x") == "POSTED"
            and record["platform_status"].get("threads") == "POSTED"
            and record["platform_status"].get("youtube") == "PRIVATE"
        )
        target["status"] = "POSTED_AND_PRIVATE_UPLOADED" if complete else "PARTIALLY_POSTED"
        target["published_at"] = _utc_now().isoformat() if complete else None
        target.pop("publish_claim_id", None)
        target.pop("publish_lease_until", None)
        _save(settings.queue_path, latest)

    report["status"] = target["status"]
    return report
