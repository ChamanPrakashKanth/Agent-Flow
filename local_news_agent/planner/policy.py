from __future__ import annotations

from ..schemas import Action, ActionName, AgentState, VerificationStatus


def allowed_actions(s: AgentState) -> list[ActionName]:
    if s.final_result: return [ActionName.FINISH]
    if s.searches == 0: return [ActionName.SEARCH]
    # A successful search must lead to reading a source. This gate prevents a
    # small model from producing (or rejecting) content from headlines alone.
    if not s.stories and s.search_results and s.page_reads < 2: return [ActionName.OPEN_SOURCE]
    if not s.stories: return [ActionName.SEARCH_MORE, ActionName.NO_POST]
    if any(not x.event for x in s.stories): return [ActionName.EXTRACT, ActionName.OPEN_SOURCE, ActionName.REJECT_STORY]
    if any(len(x.sources) < 2 and x.verification_status != VerificationStatus.CONFIRMED for x in s.stories) and s.searches < 3:
        return [ActionName.CROSS_CHECK, ActionName.CHECK_HISTORY]
    if not s.history_checked: return [ActionName.CHECK_HISTORY]
    if s.selected_index is None: return [ActionName.SELECT_STORY, ActionName.NO_POST]
    if s.draft is None: return [ActionName.WRITE_DRAFT]
    if not s.draft.verified and s.draft.unsupported_claims and s.draft_attempts < 2: return [ActionName.WRITE_DRAFT]
    if not s.draft.verified and s.draft.unsupported_claims: return [ActionName.NO_POST]
    if not s.draft.verified: return [ActionName.VERIFY_DRAFT]
    return [ActionName.QUEUE, ActionName.NO_POST]


def safe_action(s: AgentState) -> Action:
    allowed = allowed_actions(s); a = allowed[0]
    target = ""
    if a in (ActionName.OPEN_SOURCE, ActionName.EXTRACT): target = str(min(s.page_reads, max(0, len(s.search_results)-1)))
    if a in (ActionName.CROSS_CHECK, ActionName.CHECK_HISTORY, ActionName.SELECT_STORY, ActionName.WRITE_DRAFT, ActionName.VERIFY_DRAFT): target = "0"
    return Action(action=a, target=target, query=s.topic if a in (ActionName.SEARCH, ActionName.SEARCH_MORE) else "", reason="deterministic recovery policy")
