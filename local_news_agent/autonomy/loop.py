from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .bmw import BoundedMemoryWindow
from .controller import ForecastController
from .protocol import ActionDecision, SAFE_ACTIONS
from .storage import RunStore


@dataclass
class RunResult:
    run_id: str; status: str; iterations: int; x_draft: str = ""; youtube_draft: dict[str, Any] | None = None; errors: list[str] | None = None


class RecursiveAgent:
    """Observe → plan → validate → execute → score loop with bounded termination."""

    def __init__(self, decide: Callable[[dict[str, Any], list[str]], tuple[ActionDecision, int]], tools: dict[str, Callable[[dict[str, Any]], dict[str, Any]]], memory: BoundedMemoryWindow, controller: ForecastController, store: RunStore, max_actions: int = 16):
        self.decide, self.tools, self.memory, self.controller, self.store, self.max_actions = decide, tools, memory, controller, store, max(1, max_actions)

    def run(self, objective: str) -> RunResult:
        run_id = uuid.uuid4().hex; seen: dict[str, int] = {}; errors: list[str] = []; x_draft = ""; yt = None
        status = "MAX_ACTIONS"
        for iteration in range(self.max_actions):
            policy = self.controller.policy()
            if policy.require_human:
                status = "HUMAN_REVIEW_REQUIRED"; break
            decision, prompt_tokens = self.decide({"objective": objective, "memory": self.memory.context(), "policy": policy.__dict__}, sorted(set(self.tools) | {"finish"}))
            key = f"{decision.action}:{sorted(decision.arguments.items())}"
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 2:
                status = "LOOP_STOPPED"; errors.append("repeated_equivalent_action"); break
            if decision.action == "finish":
                status = "FINISHED"; self.store.step(run_id, iteration, "finish", decision.expected_result, {**self.controller.snapshot(), **self.memory.metrics(), "prompt_tokens": prompt_tokens}); break
            if decision.action not in self.tools or (decision.action == "publish_x_post" and not bool(decision.arguments.get("human_authorized"))):
                result = {"ok": False, "error": "unsafe_or_unavailable_action"}
            else:
                started = time.monotonic()
                try: result = self.tools[decision.action](decision.arguments)
                except Exception as exc: result = {"ok": False, "error": type(exc).__name__}
                result["latency_ms"] = int((time.monotonic() - started) * 1000)
            ok = bool(result.get("ok")); self.controller.update(1.0 if ok else 0.0, max(0.0, min(1.0, decision.confidence)))
            text = str(result.get("summary") or result.get("error") or result)[:1000]
            self.memory.add("observation", text, 0.8 if ok else 0.25, result.get("sources", []))
            if decision.action == "draft_x_post" and ok: x_draft = str(result.get("draft", ""))
            if decision.action == "save_youtube_draft" and ok: yt = result.get("draft")
            metrics = {**self.controller.snapshot(), **self.memory.metrics(), "prompt_tokens": prompt_tokens, "retry_budget": policy.retry_budget, "confidence": decision.confidence}
            self.store.step(run_id, iteration, decision.action, text, metrics)
        result = RunResult(run_id, status, iteration + 1, x_draft, yt, errors)
        self.store.finish(run_id, status, result.__dict__)
        return result
