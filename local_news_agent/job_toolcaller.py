from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .hermes.tools import ChromeExtensionWebTools, DirectWebTools, NewsTools
from .memory.store import MemoryStore, fingerprint
from .model import LocalModel
from .research.service import merge_evidence, story_from_evidence
from .schemas import Action, ActionName, AgentState, Draft, Evidence, SearchResult, Story, VerificationStatus
from .verification.verifier import verify_draft, verify_story
from .writer.writer import write

logger = logging.getLogger(__name__)


@dataclass
class JobToolResult:
    action: str
    success: bool
    data: Any = None
    message: str = ""


class CustomJobToolCaller(NewsTools):
    """
    Project-specific fork of the tool-calling layer for low-memory machines.

    Tool selection and execution are deterministic Python operations; Ollama is
    used only for compact planning/writing. Browser publishing is handled by
    the extension publisher and never enters Hermes' 64K agent loop.
    """

    SUPPORTED_CASES = frozenset({"search_news", "extract_article", "verify_story", "generate_draft"})

    def __init__(
        self,
        settings: Settings,
        model: LocalModel | None = None,
        memory: MemoryStore | None = None,
        direct_tools: DirectWebTools | None = None,
        extension_tools: ChromeExtensionWebTools | None = None,
    ):
        self.s = settings
        self.model = model or LocalModel(settings)
        self.memory = memory or MemoryStore(settings.database_path)
        self.direct_tools = direct_tools or DirectWebTools()
        # Extension research is opt-in. The worker can always use direct RSS/web
        # research even when Chrome has not opened yet.
        self.extension_tools = extension_tools

    def call(self, case: str, **payload: Any) -> JobToolResult:
        """Execute one bounded project case without a model-driven tool loop."""
        if case not in self.SUPPORTED_CASES:
            return JobToolResult(case, False, message="UNSUPPORTED_TOOL_CASE")
        try:
            if case == "search_news":
                data = self._search_news(str(payload.get("query", "")), int(payload.get("limit", 5)))
            elif case == "extract_article":
                data = self._extract_article(str(payload.get("url", "")))
            elif case == "verify_story":
                data = self.verify_story_candidates(payload["story"])
            else:
                data = self.generate_draft(payload["story"], payload["state"])
            return JobToolResult(case, True, data=data)
        except Exception as exc:
            logger.warning("Tool case %s failed safely: %s", case, type(exc).__name__)
            return JobToolResult(case, False, message=f"{type(exc).__name__}: {str(exc)[:200]}")

    def _search_news(self, query: str, limit: int) -> list[SearchResult]:
        limit = max(1, min(8, limit))
        if not query.strip():
            return []
        if self.extension_tools is not None:
            try:
                results = self.extension_tools.search(query, limit)
                if results:
                    return results[:limit]
            except Exception:
                pass
        return self.direct_tools.search(query, limit=limit)

    def _extract_article(self, url: str) -> Evidence:
        if not url.lower().startswith("https://"):
            raise ValueError("HTTPS article URL required")
        if self.extension_tools is not None:
            try:
                return self.extension_tools.extract(url)
            except Exception:
                pass
        return self.direct_tools.extract(url)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search fresh breaking news (last 24-48 hours) using Google News RSS and curated tech feeds."""
        logger.info("CustomToolCaller: Searching fresh news for %r (limit=%d)", query, limit)
        result = self.call("search_news", query=query, limit=limit)
        return result.data if result.success else []

    def extract(self, url: str) -> Evidence:
        """Extract clean text and factual claims from article URL."""
        logger.info("CustomToolCaller: Extracting content from %s", url)
        result = self.call("extract_article", url=url)
        if result.success:
            return result.data
        raise ValueError(result.message)

    def verify_story_candidates(self, story: Story) -> Story:
        """Verify story across independent canonical domains."""
        verify_story(story)
        story.fingerprint = story.fingerprint or fingerprint(story.event or story.headline, story.published_at)
        story.already_covered = self.memory.seen(story)
        return story

    def generate_draft(self, story: Story, state: AgentState) -> Draft:
        """Generate verified social posts and YouTube short draft with compact LLM prompt."""
        draft = write(self.model, story, state)
        verify_draft(draft, story)
        return draft

    def run_pipeline(self, topic: str) -> AgentState:
        """
        Execute full autonomous end-to-end news research, verification, and draft creation
        with deterministic state transitions and no Hermes runtime dependency.
        """
        state = AgentState(task="research_current_news", topic=topic, run_id=f"job_{uuid.uuid4().hex}")
        
        # 1. Search fresh breaking articles
        results = self.search(topic, limit=self.s.max_searches)
        state.searches += 1
        state.search_results = results

        if not results:
            state.final_result = "NO_POST"
            state.errors.append("no_fresh_results")
            return state

        # 2. Extract facts from candidate articles
        for item in results[:min(3, len(results))]:
            evidence = self.extract(item.url)
            state.page_reads += 1
            story = story_from_evidence(item, evidence)
            self.verify_story_candidates(story)
            state.stories.append(story)

        # 3. Filter eligible verified stories
        eligible = [
            (i, s) for i, s in enumerate(state.stories)
            if not s.already_covered and (s.confidence >= self.s.min_confidence or s.verification_status in {VerificationStatus.CONFIRMED, VerificationStatus.PARTIALLY_CONFIRMED})
        ]

        if not eligible:
            state.final_result = "NO_POST"
            return state

        # 4. Select top story and synthesize draft
        selected_idx, selected_story = eligible[0]
        state.selected_index = selected_idx

        draft = self.generate_draft(selected_story, state)
        state.draft = draft

        if draft.verified:
            state.final_result = "DRAFT_VERIFIED"
        else:
            state.final_result = "NO_POST"
            state.errors.append("unsupported_claims_in_draft")

        if hasattr(self.model, "unload_model"):
            self.model.unload_model()

        return state
