from pathlib import Path
from local_news_agent.memory.store import MemoryStore, fingerprint, normalize_url
from local_news_agent.schemas import Story


def test_url_normalization():
    assert normalize_url("HTTPS://www.Example.com/a/?utm_source=x&b=2#z") == "https://example.com/a?b=2"


def test_event_fingerprint_ignores_announcement_wording():
    assert fingerprint("Company X announces Y") == fingerprint("Y unveiled by Company X")


def test_persistent_duplicate(tmp_path: Path):
    store=MemoryStore(tmp_path/"m.db"); story=Story(headline="Company X announces Y",event="Company X announces Y",sources=["https://example.com/a?utm_source=x"])
    store.save_story(story,"QUEUED")
    equivalent=Story(headline="Y unveiled by Company X",event="Y unveiled by Company X",sources=["https://other.test/report"])
    assert store.seen(equivalent)

