from __future__ import annotations

import json
import uuid
from .config import Settings
from .hermes.tools import NewsTools
from .memory.budgeted_working_memory import BudgetedWorkingMemory
from .memory.store import MemoryStore, fingerprint
from .planner.planner import Planner
from .publisher.queue import Publisher
from .research.service import merge_evidence, story_from_evidence
from .schemas import Action, ActionName, AgentState, VerificationStatus
from .training.trajectory import TrajectoryLogger, reward
from .verification.verifier import verify_draft, verify_story
from .video.shorts_creator import ShortsCreator
from .writer.writer import write


class NewsAgent:
    def __init__(self, settings: Settings, planner: Planner, tools: NewsTools, memory: MemoryStore, publisher: Publisher, trajectories: TrajectoryLogger):
        self.s = settings; self.planner = planner; self.tools = tools; self.memory = memory; self.publisher = publisher; self.log = trajectories
        self.shorts = ShortsCreator(settings)
        self.working_memory = self._new_working_memory()

    def _new_working_memory(self) -> BudgetedWorkingMemory:
        return BudgetedWorkingMemory(
            budget_nodes=self.s.memory_budget_nodes,
            pressure_threshold=self.s.memory_consolidation_threshold,
        )

    def run(self, topic: str) -> AgentState:
        # A run's step counter starts at zero, so its working memory must too.
        # Persistent cross-run deduplication remains in MemoryStore/SQLite.
        self.working_memory = self._new_working_memory()
        state = AgentState(task="research_current_news", topic=topic, run_id=uuid.uuid4().hex, working_memory=self.working_memory)
        seen_actions: dict[str, int] = {}
        while state.step < self.s.max_iterations and not state.final_result:
            self.working_memory.tick(state.step)
            before = state.compact(); action = self.planner.choose(state); key = f"{action.action}:{action.target}:{action.query}"
            seen_actions[key] = seen_actions.get(key, 0) + 1
            if seen_actions[key] > 2:
                state.errors.append("loop_detected"); state.final_result = "NO_POST"; observation = "repeated action terminated safely"
            else:
                try: observation = self._execute(state, action)
                except Exception as exc:
                    state.retries += 1; state.errors.append(f"{action.action}:{type(exc).__name__}"); self.memory.failure(state.run_id, action.action, str(exc)); observation = f"tool failure: {type(exc).__name__}: {str(exc)[:300]}"
                    if state.retries > self.s.max_retries: state.final_result = "NO_POST"
            state.step += 1; state.recent_actions.append(key)
            self.log.log(task=state.task, run_id=state.run_id, state=before, action=action.model_dump(mode="json"), tool=action.action,
                         observation=str(observation)[:self.s.max_observation_chars], compressed_observation=str(observation)[:400], next_state=state.compact(), final_result=state.final_result or None, reward=None)
        if not state.final_result: state.final_result = "NO_POST"; state.errors.append("iteration_limit")
        metrics = {"steps": state.step, "searches": state.searches, "page_reads": state.page_reads, "tool_calls": state.step,
                   "prompt_tokens": state.tokens_prompt, "completion_tokens": state.tokens_completion, "total_tokens": state.tokens_prompt+state.tokens_completion,
                   "working_memory_pressure": self.working_memory.pressure, "working_memory_consolidations": self.working_memory.total_consolidations}
        chosen = state.stories[state.selected_index] if state.selected_index is not None and state.selected_index < len(state.stories) else None
        score = reward(state.final_result, chosen.confidence if chosen else (1.0 if state.final_result=="NO_POST" else 0), .8 if chosen and any(e.primary for e in chosen.evidence) else .5,
                       chosen.already_covered if chosen else False, len(state.draft.unsupported_claims) if state.draft else 0, state.step, bool(state.errors))
        self.log.log(task=state.task, run_id=state.run_id, state=state.compact(), action=None, tool=None, observation=None, compressed_observation=None,
                     next_state=None, final_result=state.final_result, reward=score, metrics=metrics)
        self.memory.save_run(state.run_id, state.final_result, {**metrics, "reward": score})
        if hasattr(self.planner, "model") and hasattr(self.planner.model, "unload_model"):
            self.planner.model.unload_model()
        return state

    def _index(self, target: str, size: int) -> int:
        try: i = int(target)
        except ValueError: i = 0
        return max(0, min(i, size-1))

    def _execute(self, s: AgentState, a: Action) -> str:
        if a.action in (ActionName.SEARCH, ActionName.SEARCH_MORE):
            if s.searches >= self.s.max_searches: return "search limit reached"
            results = self.tools.search(a.query or s.topic); s.searches += 1
            known = {x.url for x in s.search_results}; s.search_results.extend(x for x in results if x.url not in known)
            for r in results:
                self.working_memory.ingest_search_result(r.title, r.snippet, r.url)
            return f"{len(results)} results; {len(s.search_results)} unique cached"
        if a.action in (ActionName.OPEN_SOURCE, ActionName.EXTRACT):
            if s.page_reads >= self.s.max_page_reads or not s.search_results: return "page-read limit or no results"
            i = self._index(a.target, len(s.search_results)); ev = self.tools.extract(s.search_results[i].url); s.page_reads += 1
            existing = next((x for x in s.stories if x.fingerprint == fingerprint((ev.claims or [s.search_results[i].snippet])[0], ev.published_at or s.search_results[i].published_at)), None)
            if existing:
                merge_evidence(existing, ev)
                self.working_memory.ingest_story_candidate(existing.headline, existing.event, existing.confidence, existing.sources)
            else:
                story = story_from_evidence(s.search_results[i], ev)
                s.stories.append(story)
                self.working_memory.ingest_story_candidate(story.headline, story.event, story.confidence, story.sources)
            for claim in (ev.claims or [ev.excerpt[:200]]):
                self.working_memory.ingest_evidence_claim(s.search_results[i].title, claim, [ev.url])
            return f"evidence compressed: {len(ev.excerpt)} chars, {len(ev.claims)} claims"
        if a.action == ActionName.CROSS_CHECK:
            if not s.stories or s.searches >= self.s.max_searches: return "cannot cross-check"
            i = self._index(a.target, len(s.stories)); story = s.stories[i]; results = self.tools.search(a.query or story.headline, 5); s.searches += 1
            for r in results:
                self.working_memory.ingest_search_result(r.title, r.snippet, r.url)
            candidate = next((r for r in results if r.url not in story.sources), None)
            if candidate and s.page_reads < self.s.max_page_reads:
                ev = self.tools.extract(candidate.url); s.page_reads += 1; merge_evidence(story, ev)
                for claim in (ev.claims or [ev.excerpt[:200]]):
                    self.working_memory.ingest_evidence_claim(story.headline, claim, [ev.url])
            verify_story(story)
            if story.verification_status == VerificationStatus.CONFIRMED:
                for fact in story.key_facts:
                    self.working_memory.ingest_confirmed_fact(story.headline, fact, story.sources)
            self.working_memory.ingest_story_candidate(story.headline, story.event, story.confidence, story.sources)
            return f"{story.verification_status}; independent evidence={len(story.evidence)}"
        if a.action == ActionName.REJECT_STORY:
            if s.stories: s.stories.pop(self._index(a.target, len(s.stories)))
            return "story rejected"
        if a.action == ActionName.CHECK_HISTORY:
            for story in s.stories: story.fingerprint = story.fingerprint or fingerprint(story.event, story.published_at); story.already_covered = self.memory.seen(story)
            s.history_checked = True
            return f"history checked; duplicates={sum(x.already_covered for x in s.stories)}"
        if a.action == ActionName.SELECT_STORY:
            eligible = [(i, x) for i, x in enumerate(s.stories) if not x.already_covered and x.confidence >= self.s.min_confidence and x.importance >= self.s.min_importance and x.verification_status == VerificationStatus.CONFIRMED]
            if not eligible:
                eligible = [(i, x) for i, x in enumerate(s.stories) if not x.already_covered and x.confidence >= self.s.min_confidence and x.importance >= self.s.min_importance]
            if not eligible: s.final_result = "NO_POST"; return "no eligible story"
            s.selected_index = max(eligible, key=lambda pair: (pair[1].importance, pair[1].confidence))[0]
            self.working_memory.reinforce_selected(s.stories[s.selected_index].headline)
            return f"selected {s.selected_index}"
        if a.action == ActionName.WRITE_DRAFT:
            if s.selected_index is None: raise ValueError("no selected story")
            s.draft = write(self.planner.model, s.stories[s.selected_index], s); s.draft_attempts += 1
            return f"draft generated (attempt {s.draft_attempts}): {s.draft.model_dump_json()}"
        if a.action == ActionName.VERIFY_DRAFT:
            if s.selected_index is None or not s.draft: raise ValueError("draft unavailable")
            verify_draft(s.draft, s.stories[s.selected_index]); return f"verified={s.draft.verified}; unsupported={len(s.draft.unsupported_claims)}"
        if a.action == ActionName.QUEUE:
            if s.selected_index is None or not s.draft or not s.draft.verified: s.final_result = "NO_POST"; return "unsafe draft rejected"
            if self.memory.queued_today() >= self.s.daily_publish_limit: s.final_result = "NO_POST"; return "daily limit reached"
            if self.s.youtube_shorts_enabled and s.draft.youtube_short and not s.draft.youtube_short.generated:
                if hasattr(self.planner, "model") and hasattr(self.planner.model, "unload_model"):
                    self.planner.model.unload_model()
                try:
                    s.draft.youtube_short = self.shorts.create_short(s.draft.youtube_short, s.run_id)
                except Exception as exc:
                    s.errors.append(f"shorts_error:{type(exc).__name__}")
            story = s.stories[s.selected_index]; s.final_result = self.publisher.submit(s.run_id, story, s.draft); self.memory.save_story(story, "QUEUED")
            return s.final_result

        if a.action == ActionName.NO_POST: s.final_result = "NO_POST"; return "safe no-post outcome"
        if a.action == ActionName.FINISH: s.final_result = s.final_result or "NO_POST"; return "finished"
        return "action acknowledged"
