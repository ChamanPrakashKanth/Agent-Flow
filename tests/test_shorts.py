import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_news_agent.config import Settings
from local_news_agent.publisher.queue import Publisher
from local_news_agent.schemas import Draft, ShortsDraft, Story
from local_news_agent.video.pexels import PexelsClient
from local_news_agent.video.shorts_creator import ShortsCreator
from scripts import start_extension_bridge


def test_pexels_client_unconfigured():
    client = PexelsClient(api_key="")
    assert not client.is_configured
    assert client.search_portrait_videos("tech") == []
    assert client.fetch_footage_for_keywords(["tech"], Path("data/test_footage")) == []


def test_pexels_client_selects_best_portrait_file():
    client = PexelsClient(api_key="test_key")
    video_data = {
        "id": 123,
        "video_files": [
            {"id": 1, "quality": "sd", "file_type": "video/mp4", "width": 540, "height": 960, "link": "https://example.com/sd.mp4"},
            {"id": 2, "quality": "hd", "file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://example.com/hd.mp4"},
            {"id": 3, "quality": "hd", "file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://example.com/landscape.mp4"},
        ]
    }
    url = client.get_best_video_url(video_data)
    assert url == "https://example.com/hd.mp4"


def test_shorts_draft_in_queue(tmp_path: Path):
    queue_file = tmp_path / "review_queue.jsonl"
    publisher = Publisher("REVIEW", queue_file)
    story = Story(headline="Major AI Release", event="New model launched", key_facts=["Model released"])
    shorts = ShortsDraft(
        title="Major AI Release #Shorts",
        description="New model launched #AI",
        script="A new open source model was launched today.",
        visual_keywords=["artificial intelligence", "coding"],
        video_path="data/shorts/short_test.mp4",
        generated=True,
    )
    draft = Draft(x="Post", threads="Threads", youtube_short=shorts, verified=True)
    publisher.submit("run_123", story, draft)

    records = [json.loads(line) for line in queue_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 1
    assert records[0]["platform_status"] == {
        "x": "PENDING",
        "threads": "PENDING",
        "youtube": "PENDING_PRIVATE",
    }
    assert records[0]["draft_artifacts"]["youtube_short"] == {
        "status": "DRAFT_READY",
        "video_path": "data/shorts/short_test.mp4",
        "upload_allowed": True,
        "required_visibility": "PRIVATE",
        "public_publish_allowed": False,
    }
    assert records[0]["draft"]["youtube_short"]["generated"] is True
    assert records[0]["draft"]["youtube_short"]["video_path"] == "data/shorts/short_test.mp4"


def test_shorts_creator_assembly(tmp_path: Path):
    settings = Settings(
        pexels_api_key="",
        shorts_dir=tmp_path / "shorts",
        youtube_shorts_enabled=True,
    )
    creator = ShortsCreator(settings)

    draft = ShortsDraft(
        title="Test Short #Shorts",
        description="Testing shorts",
        script="Here is a brief test news update.",
        visual_keywords=["technology"],
    )

    # Test full autonomous creation with fallback ambient visual
    out_draft = creator.create_short(draft, "test_run_1")
    assert out_draft.generated is True
    assert out_draft.video_path != ""
    assert Path(out_draft.video_path).exists()
    assert Path(out_draft.video_path).stat().st_size > 1000


def test_youtube_bridge_is_private_only():
    project_root = Path(__file__).resolve().parents[1]
    background = (project_root / "chrome_extension" / "background.js").read_text(encoding="utf-8").lower()
    manifest = (project_root / "chrome_extension" / "manifest.json").read_text(encoding="utf-8").lower()
    bridge = (project_root / "local_news_agent" / "publisher" / "extension_bridge.py").read_text(encoding="utf-8").lower()

    relay = (project_root / "scripts" / "start_extension_bridge.py").read_text(encoding="utf-8").lower()

    assert "upload_youtube_private" in background
    assert "studio.youtube.com" in manifest
    assert 'visibility !== "private"' in background
    assert "video_made_for_kids_not_mfk" in background
    assert "verifiedprivateurl" in background
    assert 'payload.get("visibility") != "private"' in relay
    assert "public_publish_allowed" not in bridge


def test_relay_rejects_non_private_and_outside_video(tmp_path: Path, monkeypatch):
    allowed_root = tmp_path / "shorts"
    allowed_root.mkdir()
    video = allowed_root / "short.mp4"
    video.write_bytes(b"test-video")
    monkeypatch.setattr(start_extension_bridge, "SHORTS_ROOT", allowed_root.resolve())

    command = {
        "action": "UPLOAD_YOUTUBE_PRIVATE",
        "payload": {
            "file_path": str(video),
            "title": "Private Short #Shorts",
            "description": "Private upload test",
            "visibility": "PRIVATE",
        },
    }
    assert start_extension_bridge._valid_command(command) == (True, "")

    command["payload"]["visibility"] = "PUBLIC"
    assert start_extension_bridge._valid_command(command)[1] == "YOUTUBE_VISIBILITY_MUST_BE_PRIVATE"

    command["payload"]["visibility"] = "PRIVATE"
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"test-video")
    command["payload"]["file_path"] = str(outside)
    assert start_extension_bridge._valid_command(command)[1] == "VIDEO_OUTSIDE_SHORTS_DIRECTORY"
