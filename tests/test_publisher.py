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
    assert record["platform_status"] == {"x": "FAILED", "threads": "FAILED", "youtube": "DRAFT"}


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
    assert result["status"] == "POSTED"
    record = json.loads(settings.queue_path.read_text(encoding="utf-8"))
    assert record["status"] == "POSTED"
    assert record["platform_status"]["youtube"] == "DRAFT"
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
    assert command[1:3] == ["--model", "hermes3:3b-hermes"]
    assert command[3:5] == ["--toolsets", "computer_use"]
    assert command[5] == "--oneshot"
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


def test_direct_research_backend_does_not_bypass_hermes_publisher(tmp_path: Path):
    settings = Settings(
        publish_mode="AUTO",
        tool_backend="direct",
        queue_path=tmp_path / "queue.jsonl",
        database_path=tmp_path / "agent.db",
        trajectory_path=tmp_path / "trajectory.jsonl",
        shorts_dir=tmp_path / "shorts",
    )
    _queue_verified(settings)
    fake = {
        "x": {"status": "POSTED", "url": "https://x.com/ChamanKant44703/status/123"},
        "threads": {"status": "POSTED", "url": "https://www.threads.com/@chamanprakashkanth/post/ABC"},
        "youtube": {"status": "PRIVATE", "url": "https://youtu.be/AbCdEf12345"},
    }
    with patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all", return_value=fake) as hermes:
        result = publish_one_due(settings)
    assert result["status"] == "POSTED"
    hermes.assert_called_once()


def test_extension_publish_backend_never_starts_hermes(tmp_path: Path):
    settings = Settings(
        publish_mode="AUTO",
        publish_backend="extension",
        queue_path=tmp_path / "queue.jsonl",
        database_path=tmp_path / "agent.db",
        trajectory_path=tmp_path / "trajectory.jsonl",
        shorts_dir=tmp_path / "shorts",
    )
    _queue_verified(settings)
    fake = {
        "x": {"status": "POSTED", "url": "https://x.com/ChamanKant44703/status/123"},
        "threads": {"status": "POSTED", "url": "https://www.threads.com/@chamanprakashkanth/post/ABC"},
        "youtube": {"status": "PRIVATE", "url": "https://youtu.be/AbCdEf12345"},
    }
    with patch("local_news_agent.publisher.hermes_browser.ChromeExtensionPublisher.publish_all", return_value=fake) as extension, \
         patch("local_news_agent.publisher.hermes_browser.HermesComputerUsePublisher.publish_all") as hermes:
        result = publish_one_due(settings)
    assert result["status"] == "POSTED"
    extension.assert_called_once()
    hermes.assert_not_called()


def test_threads_publish_can_be_paused(tmp_path: Path):
    settings = Settings(
        publish_mode="AUTO",
        publish_backend="extension",
        threads_publish_enabled=False,
        queue_path=tmp_path / "queue.jsonl",
        database_path=tmp_path / "agent.db",
        trajectory_path=tmp_path / "trajectory.jsonl",
        shorts_dir=tmp_path / "shorts",
    )
    _queue_verified(settings)
    fake = {
        "x": {"status": "POSTED", "url": "https://x.com/ChamanKant44703/status/123"},
        "threads": {"status": "PAUSED", "url": "", "message": "Threads publishing paused"},
        "youtube": {"status": "PRIVATE", "url": "https://youtu.be/AbCdEf12345"},
    }
    with patch("local_news_agent.publisher.hermes_browser.ChromeExtensionPublisher.publish_all", return_value=fake):
        result = publish_one_due(settings)
    assert result["platforms"]["threads"]["status"] == "PAUSED"
    assert result["platforms"]["threads"]["url"] == ""
    assert result["status"] == "POSTED"


def test_extension_publisher_skips_paused_threads(tmp_path: Path):
    from local_news_agent.publisher.extension_bridge import ChromeExtensionPublisher
    from unittest.mock import AsyncMock
    publisher = ChromeExtensionPublisher(token_path=tmp_path / "token")
    (tmp_path / "token").write_text("dummy-token-for-test-purposes-1234567890", encoding="utf-8")
    record = {
        "platform_status": {"x": "POSTED", "threads": "PAUSED", "youtube": "PRIVATE"},
        "draft": {"x": "X text", "threads": "Threads text", "youtube_short": {}},
    }
    with patch.object(publisher, "_send_command_async", new_callable=AsyncMock) as mock_send:
        result = publisher.publish_all(record)
        assert result.get("threads", {}).get("status") == "PAUSED"
        mock_send.assert_not_called()


def test_publisher_submit_marks_threads_paused_when_disabled(tmp_path: Path):
    queue_file = tmp_path / "queue.jsonl"
    pub = Publisher("AUTO", queue_file, threads_publish_enabled=False)
    pub.submit("run-paused", Story(headline="Test"), Draft(x="X", threads="Threads", verified=True))
    record = json.loads(queue_file.read_text(encoding="utf-8"))
    assert record["platform_status"]["threads"] == "PAUSED"
