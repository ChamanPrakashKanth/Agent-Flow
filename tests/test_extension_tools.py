import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from local_news_agent.hermes.tools import ChromeExtensionWebTools, DirectWebTools
from local_news_agent.publisher.extension_bridge import ChromeExtensionPublisher
from local_news_agent.schemas import Evidence, SearchResult
from scripts import start_extension_bridge


def test_relay_validates_search_and_extract_commands():
    # Valid SEARCH_WEB
    valid_search = {
        "action": "SEARCH_WEB",
        "payload": {"query": "AI research models", "limit": 5}
    }
    assert start_extension_bridge._valid_command(valid_search) == (True, "")

    # Invalid empty SEARCH_WEB
    invalid_search = {
        "action": "SEARCH_WEB",
        "payload": {"query": "", "limit": 5}
    }
    assert start_extension_bridge._valid_command(invalid_search)[1] == "INVALID_SEARCH_QUERY"

    # Invalid limit SEARCH_WEB
    invalid_limit = {
        "action": "SEARCH_WEB",
        "payload": {"query": "AI models", "limit": 999}
    }
    assert start_extension_bridge._valid_command(invalid_limit)[1] == "INVALID_SEARCH_LIMIT"

    # Valid EXTRACT_PAGE
    valid_extract = {
        "action": "EXTRACT_PAGE",
        "payload": {"url": "https://example.com/article-123"}
    }
    assert start_extension_bridge._valid_command(valid_extract) == (True, "")

    # Invalid EXTRACT_PAGE URL
    invalid_extract = {
        "action": "EXTRACT_PAGE",
        "payload": {"url": "ftp://example.com/file"}
    }
    assert start_extension_bridge._valid_command(invalid_extract)[1] == "INVALID_EXTRACT_URL"

    private_extract = {"action": "EXTRACT_PAGE", "payload": {"url": "https://127.0.0.1/private"}}
    assert start_extension_bridge._valid_command(private_extract)[1] == "INVALID_EXTRACT_URL"


def test_chrome_extension_web_tools_search():
    mock_results = [
        {
            "title": "Major Breakthrough in Quantum AI",
            "url": "https://news.example.com/quantum-ai",
            "snippet": "Researchers announced a new hybrid algorithm.",
            "published_at": datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "source": "Quantum Journal"
        }
    ]
    with patch.object(ChromeExtensionPublisher, "search_web", return_value=mock_results):
        tools = ChromeExtensionWebTools()
        results = tools.search("Quantum AI", limit=5)
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].title == "Major Breakthrough in Quantum AI"
        assert results[0].url == "https://news.example.com/quantum-ai"
        assert results[0].source == "Quantum Journal"


def test_chrome_extension_web_tools_extract():
    mock_data = {
        "url": "https://news.example.com/quantum-ai",
        "title": "Major Breakthrough in Quantum AI",
        "publisher": "Quantum Journal",
        "published_at": "2026-08-27T12:00:00Z",
        "excerpt": "Researchers unveiled a breakthrough today.",
        "claims": ["Quantum algorithm unveiled"],
        "primary": False,
        "canonical_origin": "news.example.com"
    }
    with patch.object(ChromeExtensionPublisher, "extract_page", return_value=mock_data):
        tools = ChromeExtensionWebTools()
        evidence = tools.extract("https://news.example.com/quantum-ai")
        assert isinstance(evidence, Evidence)
        assert evidence.title == "Major Breakthrough in Quantum AI"
        assert evidence.canonical_origin == "news.example.com"
        assert evidence.primary is False
        assert "Quantum algorithm unveiled" in evidence.claims


def test_chrome_extension_web_tools_fallback():
    mock_fallback = MagicMock(spec=DirectWebTools)
    mock_fallback.search.return_value = [
        SearchResult(title="Fallback Story", url="https://fallback.example.com", snippet="...", published_at="", source="RSS")
    ]
    mock_fallback.extract.return_value = Evidence(
        url="https://fallback.example.com",
        title="Fallback Story",
        publisher="RSS",
        excerpt="Fallback content",
        canonical_origin="fallback.example.com"
    )

    with patch.object(ChromeExtensionPublisher, "search_web", return_value=[]):
        with patch.object(ChromeExtensionPublisher, "extract_page", return_value=None):
            tools = ChromeExtensionWebTools(fallback=mock_fallback)
            res = tools.search("AI", limit=2)
            assert len(res) == 1
            assert res[0].title == "Fallback Story"
            mock_fallback.search.assert_called_once_with("AI", 2)

            ev = tools.extract("https://fallback.example.com")
            assert ev.title == "Fallback Story"
            mock_fallback.extract.assert_called_once_with("https://fallback.example.com")


def test_chrome_extension_search_rejects_stale_results():
    stale = [{
        "title": "Old Story",
        "url": "https://news.example.com/old",
        "snippet": "Old information",
        "published_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        "source": "Archive",
    }]
    fallback = MagicMock(spec=DirectWebTools)
    fallback.search.return_value = []
    with patch.object(ChromeExtensionPublisher, "search_web", return_value=stale):
        assert ChromeExtensionWebTools(fallback=fallback).search("AI", limit=5) == []
    fallback.search.assert_called_once_with("AI", 5)
