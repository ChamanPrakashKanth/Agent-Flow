from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ActionName(str, Enum):
    SEARCH = "SEARCH"
    OPEN_SOURCE = "OPEN_SOURCE"
    EXTRACT = "EXTRACT"
    CROSS_CHECK = "CROSS_CHECK"
    SEARCH_MORE = "SEARCH_MORE"
    REJECT_STORY = "REJECT_STORY"
    CHECK_HISTORY = "CHECK_HISTORY"
    SELECT_STORY = "SELECT_STORY"
    WRITE_DRAFT = "WRITE_DRAFT"
    VERIFY_DRAFT = "VERIFY_DRAFT"
    QUEUE = "QUEUE"
    NO_POST = "NO_POST"
    FINISH = "FINISH"


class VerificationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    CONFLICTING = "CONFLICTING"
    UNVERIFIED = "UNVERIFIED"


class Action(BaseModel):
    action: ActionName
    target: str = ""
    query: str = ""
    reason: str = Field(default="", max_length=500)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: str = ""
    source: str = ""


class Evidence(BaseModel):
    url: str
    title: str = ""
    publisher: str = ""
    published_at: str = ""
    excerpt: str = Field(default="", max_length=4000)
    claims: list[str] = Field(default_factory=list)
    primary: bool = False
    canonical_origin: str = ""


class Story(BaseModel):
    headline: str
    event: str = ""
    published_at: str = ""
    sources: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    already_covered: bool = False
    importance: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)
    fingerprint: str = ""


class ShortsDraft(BaseModel):
    title: str = ""
    description: str = ""
    script: str = ""
    visual_keywords: list[str] = Field(default_factory=list)
    video_path: str = ""
    duration_seconds: float = 0.0
    generated: bool = False


class Draft(BaseModel):
    x: str
    threads: str
    youtube_short: ShortsDraft | None = None
    claim_evidence: dict[str, list[str]] = Field(default_factory=dict)
    verified: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)


class ConceptMemoryToken(BaseModel):
    token_id: str
    summary: str
    step: int
    timescale: str = "CONSOLIDATED"


class AgentState(BaseModel):
    task: str
    topic: str
    run_id: str
    step: int = 0
    phase: str = "discover"
    search_results: list[SearchResult] = Field(default_factory=list)
    stories: list[Story] = Field(default_factory=list)
    selected_index: int | None = None
    history_checked: bool = False
    draft: Draft | None = None
    draft_attempts: int = 0
    searches: int = 0
    page_reads: int = 0
    retries: int = 0
    recent_actions: list[str] = Field(default_factory=list)
    final_result: str = ""
    errors: list[str] = Field(default_factory=list)
    tokens_prompt: int = 0
    tokens_completion: int = 0
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    working_memory: Any = Field(default=None, exclude=True)

    def compact(self) -> dict[str, Any]:
        selected = self.stories[self.selected_index] if self.selected_index is not None and self.selected_index < len(self.stories) else None
        has_budgeted_memory = self.working_memory is not None and hasattr(self.working_memory, "get_budgeted_summary")
        data: dict[str, Any] = {
            "task": self.task, "topic": self.topic, "step": self.step, "phase": self.phase,
            "limits_used": {"searches": self.searches, "page_reads": self.page_reads, "retries": self.retries},
            # Memory carries the salient snippets. The action view keeps stable
            # indices plus only the fields needed to choose/open a source.
            "results": [{"i": i, "title": r.title[:140], "url": r.url} for i, r in enumerate(self.search_results[:4])],
            "stories": [{"i": i, "headline": s.headline, "sources": len(s.sources), "confidence": s.confidence,
                         "status": s.verification_status, "importance": s.importance, "covered": s.already_covered}
                        for i, s in enumerate(self.stories[:4])],
            "selected": selected.model_dump(exclude={"evidence"}) if selected else None,
            "has_draft": self.draft is not None,
            "history_checked": self.history_checked,
            "draft_verified": self.draft.verified if self.draft else False,
            "draft_attempts": self.draft_attempts,
            "recent_actions": self.recent_actions[-3:], "errors": self.errors[-2:],
        }
        if has_budgeted_memory:
            data["working_memory"] = self.working_memory.get_budgeted_summary()
        return data
