from __future__ import annotations

import json
from .policy import allowed_actions, safe_action
from ..model import LocalModel, first_json
from ..schemas import Action, AgentState

SYSTEM = """You are the planner in a small local news-research agent. Choose exactly ONE next action.
Return JSON only: {\"action\":\"ACTION\",\"target\":\"index or URL\",\"query\":\"optional\",\"reason\":\"brief\"}.
Never invent evidence. Prefer verification and a safe NO_POST over weak content. Obey allowed_actions."""


class Planner:
    def __init__(self, model: LocalModel): self.model = model

    def choose(self, state: AgentState) -> Action:
        allowed = allowed_actions(state)
        prompt = json.dumps({"state": state.compact(), "allowed_actions": [a.value for a in allowed]}, ensure_ascii=False)
        try:
            reply = self.model.chat(SYSTEM, prompt, json_mode=True)
            state.tokens_prompt += reply.prompt_tokens; state.tokens_completion += reply.completion_tokens
            action = Action.model_validate(first_json(reply.text))
            if action.action not in allowed: raise ValueError(f"disallowed action {action.action}")
            return action
        except Exception as exc:
            state.retries += 1; state.errors.append(f"planner_repair:{type(exc).__name__}")
            return safe_action(state)

