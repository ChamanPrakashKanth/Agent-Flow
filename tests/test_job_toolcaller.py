import json
from unittest.mock import MagicMock, patch

import pytest
from local_news_agent.config import Settings
from local_news_agent.job_toolcaller import CustomJobToolCaller
from local_news_agent.model import LocalModel
from local_news_agent.schemas import Evidence, SearchResult, Story


def test_custom_job_toolcaller_search():
    settings = Settings(tool_backend="custom", model_context_tokens=2048)
    caller = CustomJobToolCaller(settings=settings)

    mock_results = [
        SearchResult(title="AI Chip Breakthrough", url="https://tech.test/chip", snippet="New quantum chip unveiled.", source="Tech News")
    ]
    with patch.object(caller.extension_tools.bridge, "search_web", return_value=[]), \
         patch.object(caller.direct_tools, "search", return_value=mock_results):
        results = caller.search("AI chip", limit=3)
        assert len(results) == 1
        assert results[0].title == "AI Chip Breakthrough"


def test_custom_job_toolcaller_extract():
    settings = Settings(tool_backend="custom", model_context_tokens=2048)
    caller = CustomJobToolCaller(settings=settings)

    mock_evidence = Evidence(
        url="https://tech.test/chip",
        title="AI Chip Breakthrough",
        publisher="Tech News",
        excerpt="Researchers today announced a revolutionary 2nm quantum semiconductor architecture.",
        claims=["2nm quantum semiconductor announced"],
    )
    with patch.object(caller.extension_tools.bridge, "extract_page", return_value=None), \
         patch.object(caller.direct_tools, "extract", return_value=mock_evidence):
        ev = caller.extract("https://tech.test/chip")
        assert ev.title == "AI Chip Breakthrough"
        assert len(ev.claims) == 1


def test_custom_job_toolcaller_pipeline():
    settings = Settings(tool_backend="custom", model_context_tokens=2048)
    mock_model = MagicMock(spec=LocalModel)
    caller = CustomJobToolCaller(settings=settings, model=mock_model)

    mock_results = [
        SearchResult(title="Semiconductor Breakthrough", url="https://tech.test/semi", snippet="New chip architecture.", source="Tech News")
    ]
    mock_evidence = Evidence(
        url="https://tech.test/semi",
        title="Semiconductor Breakthrough",
        publisher="Tech News",
        excerpt="New chip architecture announced with 2nm density.",
        claims=["New chip architecture announced with 2nm density"],
    )

    with patch.object(caller, "search", return_value=mock_results), \
         patch.object(caller, "extract", return_value=mock_evidence), \
         patch.object(caller, "generate_draft") as mock_draft:
        
        mock_draft.return_value = MagicMock(verified=True, unsupported_claims=[])
        state = caller.run_pipeline("semiconductors")

        assert state.searches == 1
        assert len(state.stories) == 1
        assert state.final_result == "DRAFT_VERIFIED"
