from unittest.mock import Mock

from local_news_agent.config import Settings
from local_news_agent.job_toolcaller import CustomJobToolCaller
from local_news_agent.schemas import Evidence, SearchResult


def test_case_toolcaller_rejects_unknown_case(tmp_path):
    settings = Settings(database_path=tmp_path / "agent.db")
    caller = CustomJobToolCaller(settings, direct_tools=Mock())
    result = caller.call("run_arbitrary_command")
    assert result.success is False
    assert result.message == "UNSUPPORTED_TOOL_CASE"


def test_search_case_is_bounded_and_does_not_require_extension(tmp_path):
    settings = Settings(database_path=tmp_path / "agent.db")
    direct = Mock()
    direct.search.return_value = [SearchResult(title="Fresh", url="https://example.test/news")]
    caller = CustomJobToolCaller(settings, direct_tools=direct)
    result = caller.call("search_news", query="AI", limit=99)
    assert result.success is True
    direct.search.assert_called_once_with("AI", limit=8)


def test_extract_case_requires_https(tmp_path):
    settings = Settings(database_path=tmp_path / "agent.db")
    direct = Mock()
    direct.extract.return_value = Evidence(url="https://example.test/news", excerpt="Evidence")
    caller = CustomJobToolCaller(settings, direct_tools=direct)
    denied = caller.call("extract_article", url="file:///secret.txt")
    assert denied.success is False
    direct.extract.assert_not_called()
