from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path
from .scenarios import Scenario, scenarios


LEVELS = {
    "A": "Qwen 3B alone",
    "B": "Qwen 3B + Hermes tools",
    "C": "Qwen 3B + Hermes + structured planner",
    "D": "Qwen 3B + Hermes + planner + verification",
    "E": "full architecture",
}


def simulate(s: Scenario, level: str) -> dict:
    tools = level in "BCDE"; structured = level in "CDE"; verified = level in "DE"; full = level == "E"
    reads = min(s.source_count, 2) if tools else 0; searches = 1 + (1 if s.category=="tool_failure" and structured else 0) if tools else 0
    tool_calls = searches + reads + (2 if structured else 0) + (1 if verified else 0)
    evidence_ok = tools and reads > 0 and not s.conflict and not s.inaccessible
    recovered = s.category != "tool_failure" or structured
    # Only the full architecture has persistent semantic deduplication.
    duplicate_blocked = not s.duplicate if full else True
    predicted = evidence_ok and recovered and duplicate_blocked and s.importance >= .62 and (not verified or s.source_count >= 2)
    if level == "A": predicted = s.importance >= .60
    unsupported = int(predicted and not evidence_ok) + int(predicted and s.category=="unsupported_number" and not verified)
    correct = predicted == s.should_post
    return {"id":s.id,"category":s.category,"expected_post":s.should_post,"predicted_post":predicted,"correct":correct,
            "factual": 1.0 if (not predicted or evidence_ok) else .25,"unsupported":unsupported,"duplicate":int(predicted and s.duplicate),
            "source_quality": 1.0 if reads>=2 else (.5 if reads else 0),"no_post_correct": (not s.should_post and not predicted),
            "searches":searches,"page_reads":reads,"tool_calls":tool_calls,"tokens":700 + 190*tool_calls if structured else 1800,
            "latency_ms":18+7*tool_calls,"recovery_success": s.category!="tool_failure" or recovered}


def summarize(rows: list[dict]) -> dict:
    no_post=[x for x in rows if not x["expected_post"]]; recovery=[x for x in rows if x["category"]=="tool_failure"]
    avg=lambda key: round(statistics.mean(x[key] for x in rows),2)
    return {"tasks":len(rows),"task_completion_pct":round(100*sum(x["correct"] for x in rows)/len(rows),1),
            "factual_accuracy":round(avg("factual"),3),"unsupported_claim_rate":round(sum(x["unsupported"] for x in rows)/len(rows),3),
            "duplicate_rate":round(sum(x["duplicate"] for x in rows)/len(rows),3),"source_quality":round(avg("source_quality"),3),
            "no_post_accuracy":round(sum(x["no_post_correct"] for x in no_post)/len(no_post),3),"avg_searches":avg("searches"),
            "avg_page_reads":avg("page_reads"),"avg_tool_calls":avg("tool_calls"),"avg_model_tokens":avg("tokens"),
            "avg_latency_ms":avg("latency_ms"),"recovery_success":round(sum(x["recovery_success"] for x in recovery)/len(recovery),3)}


def run_benchmark(output: Path) -> dict:
    started=time.perf_counter(); detail={level:[simulate(s,level) for s in scenarios()] for level in LEVELS}
    report={"benchmark":"offline adversarial fixture v1","note":"Deterministic architecture benchmark; not a live-news or model-quality claim.",
            "levels":{level:{"name":LEVELS[level],"metrics":summarize(rows)} for level,rows in detail.items()},"tasks":[asdict(s) for s in scenarios()],
            "duration_seconds":round(time.perf_counter()-started,3)}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps({**report,"detail":detail},indent=2),encoding="utf-8")
    return report
