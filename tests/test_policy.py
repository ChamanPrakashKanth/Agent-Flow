from local_news_agent.planner.policy import allowed_actions, safe_action
from local_news_agent.schemas import ActionName, AgentState, Draft, SearchResult, Story


def state(): return AgentState(task="test",topic="AI",run_id="r")


def test_first_action_is_search(): assert allowed_actions(state()) == [ActionName.SEARCH]


def test_safe_action_is_allowed():
    s=state(); assert safe_action(s).action in allowed_actions(s)


def test_search_results_force_source_read():
    s=state(); s.searches=1; s.search_results=[SearchResult(title="Story",url="https://example.test")]
    assert allowed_actions(s) == [ActionName.OPEN_SOURCE]


def test_failed_draft_gets_one_rewrite():
    s=state(); s.searches=1; s.history_checked=True; s.stories=[Story(headline="h",event="e",sources=["a","b"],verification_status="CONFIRMED",fingerprint="fp")]; s.selected_index=0
    s.draft=Draft(x="bad",threads="bad",unsupported_claims=["bad"]); s.draft_attempts=1
    assert allowed_actions(s) == [ActionName.WRITE_DRAFT]
    s.draft_attempts=2
    assert allowed_actions(s) == [ActionName.NO_POST]
