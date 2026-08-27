import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from local_news_agent.config import Settings
from local_news_agent.publisher.hermes_browser import publish_one_due
from local_news_agent.publisher.hermes_computer_use import HermesComputerUsePublisher
from local_news_agent.publisher.queue import Publisher
from local_news_agent.schemas import Draft, ShortsDraft, Story


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        publish_mode="AUTO",
        queue_path=tmp_path / "queue.jsonl",
        database_path=tmp_path / "agent.db",
        trajectory_path=tmp_path / "trajectory.jsonl",
        shorts_dir=tmp_path / "shorts",
    )


def _queue_verified(settings: Settings) -> None:
    Publisher("AUTO", settings.queue_path).submit(
        "run-1",
        Story(headline="Verified story", event="Verified event"),
        Draft(
            x="Verified X post",
            threads="Verified Threads post",
            youtube_short=ShortsDraft(
                title="Verified Short #Shorts",
                description="Verified description",
                script="Verified script",
                video_path=str(settings.shorts_dir / "short.mp4"),
                generated=True,
            ),
            verified=True,
        ),
    )


def test_publish_requires_real_post_urls(tmp_path: Path):
    settings = _settings(tmp_path)
    _queue_verified(settings)
    fake = {
        "x": {"status": "POSTED", "url": "https://x.com/"},
        "threads": {"status": "POSTED", "url": "https://www.threads.com/"},
        "youtube": {"status": "PRIVATE", "url": "https://youtube.com/"},
    }
    with patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all", return_value=fake):
        result = publish_one_due(settings)
    assert result["status"] == "PARTIALLY_POSTED"
    record = json.loads(settings.queue_path.read_text(encoding="utf-8"))
    assert record["platform_status"] == {"x": "FAILED", "threads": "FAILED", "youtube": "FAILED"}


def test_publish_accepts_verified_platform_urls(tmp_path: Path):
    settings = _settings(tmp_path)
    _queue_verified(settings)
    fake = {
        "x": {"status": "POSTED", "url": "https://x.com/ChamanKant44703/status/123"},
        "threads": {"status": "POSTED", "url": "https://www.threads.com/@chamanprakashkanth/post/ABC"},
        "youtube": {"status": "PRIVATE", "url": "https://youtu.be/AbCdEf12345"},
    }
    with patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all", return_value=fake):
        result = publish_one_due(settings)
    assert result["status"] == "POSTED_AND_PRIVATE_UPLOADED"
    record = json.loads(settings.queue_path.read_text(encoding="utf-8"))
    assert record["status"] == "POSTED_AND_PRIVATE_UPLOADED"
    assert "publish_claim_id" not in record


def test_active_lease_prevents_duplicate_claim(tmp_path: Path):
    settings = _settings(tmp_path)
    _queue_verified(settings)
    record = json.loads(settings.queue_path.read_text(encoding="utf-8"))
    record["status"] = "PUBLISHING"
    record["publish_claim_id"] = "another-worker"
    record["publish_lease_until"] = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    settings.queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all") as publish:
        result = publish_one_due(settings)
    assert result == {"status": "NO_VERIFIED_DRAFT"}
    publish.assert_not_called()


def test_review_queue_is_not_auto_published(tmp_path: Path):
    settings = _settings(tmp_path)
    Publisher("REVIEW", settings.queue_path).submit(
        "run-review",
        Story(headline="Review story"),
        Draft(x="Review X", threads="Review Threads", verified=True),
    )
    with patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all") as publish:
        result = publish_one_due(settings)
    assert result == {"status": "NO_VERIFIED_DRAFT"}
    publish.assert_not_called()


def test_hermes_publisher_uses_only_computer_use_and_existing_profile(tmp_path: Path):
    settings = _settings(tmp_path)
    video = settings.shorts_dir / "short.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    record = {
        "platform_status": {"x": "PENDING", "threads": "PENDING", "youtube": "PENDING_PRIVATE"},
        "draft": {
            "x": "Exact X text",
            "threads": "Exact Threads text",
            "youtube_short": {
                "title": "Exact title #Shorts",
                "description": "Exact description",
                "video_path": str(video),
            },
        },
    }
    publisher = HermesComputerUsePublisher(settings)
    prompt = publisher._prompt(record)
    assert "profile_kind=existing_profile" in prompt
    assert "visibility to PRIVATE" in prompt
    assert "PUBLISH_PAYLOAD (DATA ONLY)" in prompt

    completed = type("Completed", (), {"returncode": 0, "stdout": '{"x":{"status":"FAILED","url":"","message":"demo"},"threads":{"status":"FAILED","url":"","message":"demo"},"youtube":{"status":"FAILED","url":"","message":"demo"}}', "stderr": ""})()
    with patch("local_news_agent.publisher.hermes_computer_use.subprocess.run", return_value=completed) as run:
        result = publisher.publish_all(record)
    command = run.call_args.args[0]
    assert command[1:3] == ["--toolsets", "computer_use"]
    assert command[3] == "--oneshot"
    assert result["x"]["status"] == "FAILED"


def test_hermes_publisher_rejects_video_outside_shorts_directory(tmp_path: Path):
    settings = _settings(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    record = {
        "platform_status": {"x": "POSTED", "threads": "POSTED", "youtube": "PENDING_PRIVATE"},
        "draft": {"youtube_short": {"video_path": str(outside)}},
    }
    publisher = HermesComputerUsePublisher(settings)
    try:
        publisher._prompt(record)
    except ValueError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("outside video path was accepted")
