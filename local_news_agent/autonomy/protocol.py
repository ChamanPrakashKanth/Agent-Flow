from __future__ import annotations

from typing import Any, Callable
import json
import re

from pydantic import BaseModel, Field, field_validator

from ..model import first_json


SAFE_ACTIONS = {
    "search_web", "open_page", "extract_page", "save_fact", "retrieve_memory",
    "draft_x_post", "publish_x_post", "create_short_script", "generate_short_assets",
    "render_short", "prepare_youtube_metadata", "save_youtube_draft", "finish",
}


class ActionDecision(BaseModel):
    """The only model-to-tool protocol accepted by the harness."""

    thought_summary: str = Field(max_length=500)
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_result: str = Field(default="", max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("action")
    @classmethod
    def safe_action(cls, value: str) -> str:
        if value not in SAFE_ACTIONS:
            raise ValueError("action is not in the local allowlist")
        return value


def parse_decision(text: str, repair: Callable[[str], str] | None = None) -> ActionDecision:
    """Parse strict JSON, requesting one safe repair before a benign finish."""
    try:
        return ActionDecision.model_validate(first_json(text))
    except Exception as first_error:
        markdown = _parse_labeled_decision(text)
        if markdown is not None:
            return markdown
        if repair is not None:
            try:
                repaired = repair(str(first_error))
                try:
                    return ActionDecision.model_validate(first_json(repaired))
                except Exception:
                    markdown = _parse_labeled_decision(repaired)
                    if markdown is not None:
                        return markdown
            except Exception:
                pass
        return ActionDecision(
            thought_summary="Model response was malformed; ending safely.",
            action="finish",
            expected_result="No unsafe tool action is taken.",
            confidence=0.0,
        )


def _parse_labeled_decision(text: str) -> ActionDecision | None:
    """Safely normalize Qwen's common heading and key-value formats into the schema."""
    if not text:
        return None
    # 1. Match markdown headings ### Thought Summary ...
    match = re.search(
        r"(?:^|\n)###\s*Thought Summary\s*(.*?)\s*###\s*Action\s*(.*?)\s*###\s*Arguments\s*(.*?)\s*###\s*Expected Result\s*(.*?)\s*###\s*Confidence\s*([0-9.]+%?)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if match:
        thought, action, raw_args, expected, confidence = (x.strip() for x in match.groups())
    else:
        # 2. Match key-value format (thought_summary: ..., action: ..., etc.)
        p_thought = re.search(r"(?:^|\n)(?:thought_summary|thought):\s*(.*?)(?=\n(?:action|arguments|expected_result|confidence):|$)", text, re.DOTALL | re.IGNORECASE)
        p_action = re.search(r"(?:^|\n)action:\s*(.*?)(?=\n(?:arguments|expected_result|confidence|thought_summary):|$)", text, re.DOTALL | re.IGNORECASE)
        p_args = re.search(r"(?:^|\n)arguments:\s*(.*?)(?=\n(?:expected_result|confidence|thought_summary|action):|$)", text, re.DOTALL | re.IGNORECASE)
        p_exp = re.search(r"(?:^|\n)(?:expected_result|expected):\s*(.*?)(?=\n(?:confidence|thought_summary|action|arguments):|$)", text, re.DOTALL | re.IGNORECASE)
        p_conf = re.search(r"(?:^|\n)confidence:\s*([0-9.]+%?)", text, re.IGNORECASE)
        
        if not (p_action and p_thought):
            return None
        thought = p_thought.group(1).strip()
        action = p_action.group(1).strip()
        raw_args = p_args.group(1).strip() if p_args else "{}"
        expected = p_exp.group(1).strip() if p_exp else ""
        confidence = p_conf.group(1).strip() if p_conf else "0.7"

    action = action.splitlines()[0].strip().strip('"`').lower()
    try:
        arguments = json.loads(raw_args)
        if not isinstance(arguments, dict):
            arguments = {"query": str(arguments)} if action == "search_web" else {}
    except Exception:
        value = raw_args.strip('"` \n')
        arguments = {"query": value} if action == "search_web" and value else {}
    try:
        score = float(confidence.rstrip("%")) / (100.0 if confidence.endswith("%") else 1.0)
    except ValueError:
        score = 0.7
    try:
        return ActionDecision(thought_summary=thought[:500], action=action, arguments=arguments, expected_result=expected[:500], confidence=min(1.0, max(0.0, score)))
    except Exception:
        return None
