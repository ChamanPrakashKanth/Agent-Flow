from __future__ import annotations

import json
from .policy import allowed_actions, safe_action
from ..model import LocalModel, first_json
from ..schemas import Action, AgentState

SYNONYMS: dict[str, list[str]] = {
    "EXTRACT_ARTICLE": ["EXTRACT", "OPEN_SOURCE"],
    "EXTRACT": ["OPEN_SOURCE", "EXTRACT"],
    "OPEN_SOURCE": ["EXTRACT", "OPEN_SOURCE"],
    "READ": ["OPEN_SOURCE", "EXTRACT"],
    "SEARCH_NEWS": ["SEARCH", "SEARCH_MORE"],
    "SEARCH_WEB": ["SEARCH", "SEARCH_MORE"],
    "SEARCH": ["SEARCH_MORE", "SEARCH"],
    "SEARCH_MORE": ["SEARCH", "SEARCH_MORE"],
    "VERIFY": ["VERIFY_DRAFT", "CROSS_CHECK"],
    "VERIFY_STORY": ["CROSS_CHECK"],
    "SELECT": ["SELECT_STORY"],
    "SELECT_STORY": ["SELECT"],
    "WRITE": ["WRITE_DRAFT"],
    "GENERATE_DRAFT": ["WRITE_DRAFT"],
    "DRAFT": ["WRITE_DRAFT"],
    "PUBLISH": ["QUEUE"],
}

SYSTEM = """You are the planner in a small local news-research agent. Choose exactly ONE next action.
You MUST choose the exact action name from the provided 'allowed_actions' list.
Return JSON only: {"action":"<ALLOWED_ACTION>","target":"index or URL","query":"optional","reason":"brief"}.
Never invent evidence. Prefer verification and a safe NO_POST over weak content."""


class Planner:
    def __init__(self, model: LocalModel): self.model = model

    def choose(self, state: AgentState) -> Action:
        allowed = allowed_actions(state)
        prompt = json.dumps({"state": state.compact(), "allowed_actions": [a.value for a in allowed]}, ensure_ascii=False)
        try:
            reply = self.model.chat(SYSTEM, prompt, json_mode=True)
            state.tokens_prompt += reply.prompt_tokens; state.tokens_completion += reply.completion_tokens
            data = first_json(reply.text)
            act_name_str = str(data.get("action", "")).strip().upper().replace(" ", "_")
            matched_act = next((a for a in allowed if a.value == act_name_str), None)
            if not matched_act:
                for syn in SYNONYMS.get(act_name_str, []):
                    matched_act = next((a for a in allowed if a.value == syn), None)
                    if matched_act:
                        break
            if not matched_act:
                raise ValueError(f"disallowed action {act_name_str}")
            return Action(
                action=matched_act,
                target=str(data.get("target", "")),
                query=str(data.get("query", "")),
                reason=str(data.get("reason", ""))[:500]
            )
        except Exception as exc:
            state.retries += 1; state.errors.append(f"planner_repair:{type(exc).__name__}")
            return safe_action(state)

