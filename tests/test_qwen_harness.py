from pathlib import Path

from local_news_agent.autonomy.bmw import BoundedMemoryWindow
from local_news_agent.autonomy.controller import ForecastController
from local_news_agent.autonomy.loop import RecursiveAgent
from local_news_agent.autonomy.protocol import parse_decision
from local_news_agent.autonomy.storage import RunStore


def test_bmw_remains_bounded_and_tracks_pressure():
    memory = BoundedMemoryWindow(max_items=4, max_tokens=60)
    for i in range(12):
        memory.add("observation", f"item {i} " + "detail " * 20, importance=i / 12)
    metrics = memory.metrics()
    assert metrics["items_retained"] <= 4
    assert metrics["items_discarded"] > 0
    assert metrics["estimated_kv_pressure"] <= 100


def test_forecast_controller_escalates_and_clamps():
    controller = ForecastController(alpha=1.0)
    controller.update(0, 1)
    assert controller.policy().require_human
    for _ in range(5): controller.update(0, 1)
    assert 0 <= controller.snapshot()["guidance"] <= 1
    assert controller.policy().require_human


def test_malformed_model_response_finishes_safely():
    decision = parse_decision("not json")
    assert decision.action == "finish"


def test_recursive_loop_stops_repeated_action_and_persists(tmp_path: Path):
    memory = BoundedMemoryWindow(); controller = ForecastController(); store = RunStore(tmp_path / "state.db")
    def decide(_context, _actions):
        from local_news_agent.autonomy.protocol import ActionDecision
        return ActionDecision(thought_summary="repeat", action="search_web", arguments={"query": "same"}, expected_result="x", confidence=.9), 10
    agent = RecursiveAgent(decide, {"search_web": lambda _args: {"ok": True, "summary": "one"}}, memory, controller, store, max_actions=10)
    result = agent.run("topic")
    assert result.status == "LOOP_STOPPED"
    assert store.inspect(result.run_id)["run"]["status"] == "LOOP_STOPPED"


def test_publish_path_keeps_youtube_draft(tmp_path: Path):
    from local_news_agent.config import Settings
    from local_news_agent.publisher.queue import Publisher
    from local_news_agent.publisher.hermes_browser import publish_one_due
    from local_news_agent.schemas import Draft, ShortsDraft, Story
    settings = Settings(publish_mode="AUTO", publish_backend="extension", queue_path=tmp_path / "queue.jsonl", database_path=tmp_path / "state.db", trajectory_path=tmp_path / "t.jsonl", shorts_dir=tmp_path / "shorts")
    Publisher("AUTO", settings.queue_path).submit("r", Story(headline="h"), Draft(x="x", threads="t", verified=True, youtube_short=ShortsDraft(video_path="v.mp4", generated=True)))
    # No bridge call is possible when both social destinations are already complete.
    import json
    record = json.loads(settings.queue_path.read_text())
    record["platform_status"].update({"x": "POSTED", "threads": "POSTED"})
    settings.queue_path.write_text(json.dumps(record) + "\n")
    result = publish_one_due(settings)
    assert result["status"] == "POSTED"
    saved = json.loads(settings.queue_path.read_text())
    assert saved["platform_status"]["youtube"] == "DRAFT"
