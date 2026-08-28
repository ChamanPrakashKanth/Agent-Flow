from __future__ import annotations

import logging
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
    Dedicated, zero-Hermes custom toolcaller engineered for low-memory environments (4GB VRAM / 6GB RAM).
    Operates with ultra-compact context (<=2048 tokens) and direct single-pass Python execution.
    """

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
        self.extension_tools = extension_tools or ChromeExtensionWebTools(fallback=self.direct_tools)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search fresh breaking news (last 24-48 hours) using Google News RSS and curated tech feeds."""
        logger.info("CustomToolCaller: Searching fresh news for %r (limit=%d)", query, limit)
        if self.extension_tools:
            try:
                raw_items = self.extension_tools.bridge.search_web(query, limit)
                if raw_items:
                    results: list[SearchResult] = []
                    for item in raw_items:
                        try:
                            result = SearchResult.model_validate(item)
                            if self.extension_tools._is_fresh(result.published_at):
                                results.append(result)
                        except Exception:
                            continue
                    if results:
                        return results[:limit]
            except Exception:
                pass
        return self.direct_tools.search(query, limit=limit)

    def extract(self, url: str) -> Evidence:
        """Extract clean text and factual claims from article URL."""
        logger.info("CustomToolCaller: Extracting content from %s", url)
        if self.extension_tools:
            try:
                raw_evidence = self.extension_tools.bridge.extract_page(url)
                if raw_evidence and isinstance(raw_evidence, dict) and raw_evidence.get("excerpt"):
                    return Evidence.model_validate(raw_evidence)
            except Exception:
                pass
        return self.direct_tools.extract(url)

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
        with deterministic state transitions and zero OOM risk.
        """
        state = AgentState(task="research_current_news", topic=topic, run_id=f"job_{Path().stat().st_mtime_ns if hasattr(Path(), 'stat') else 1}")
        
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

        return state
