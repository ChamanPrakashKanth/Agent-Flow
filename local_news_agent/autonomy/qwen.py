from __future__ import annotations

import json
from typing import Any

import httpx

from .protocol import ActionDecision, parse_decision
from ..model import ModelReply, count_messages_tokens


SYSTEM = """You are a local Qwen Coder 3B research controller. Return JSON only with thought_summary, action, arguments, expected_result, confidence. Use only the supplied action allowlist. Do not emit shell commands, credentials, hidden reasoning, or citations you did not observe. If memory contains no sourced facts, choose search_web with a focused query. After search results, choose extract_page before drafting. Only choose finish when a useful task outcome has been reached or a safe constraint prevents progress."""


class QwenLlamaCppModel:
    """OpenAI-compatible llama.cpp server adapter; no Ollama dependency."""

    def __init__(self, base_url: str, model: str, context_tokens: int = 2048, client: Any = httpx):
        self.base_url = base_url.rstrip("/"); self.model = model; self.context_tokens = context_tokens; self.client = client

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.1) -> ModelReply:
        response = self.client.post(f"{self.base_url}/v1/chat/completions", json={"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": min(384, self.context_tokens // 3), "response_format": {"type": "json_object"}}, timeout=120)
        response.raise_for_status(); data = response.json(); usage = data.get("usage", {})
        return ModelReply(str(data["choices"][0]["message"]["content"]), usage.get("prompt_tokens") or count_messages_tokens(messages), usage.get("completion_tokens", 0))

    def decide(self, objective: str, memory: dict[str, Any], actions: list[str]) -> tuple[ActionDecision, ModelReply]:
        payload = {"objective": objective, "memory": memory, "allowed_actions": actions}
        reply = self.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
        def repair(error: str) -> str:
            repair_prompt = {
                "instruction": "Convert the original response below into exactly one valid JSON object with thought_summary, action, arguments, expected_result, and confidence. Do not add Markdown or prose.",
                "validation_error": error,
                "allowed_actions": actions,
                "original_response": reply.text,
            }
            repair_reply = self.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(repair_prompt, ensure_ascii=False)}])
            return repair_reply.text
        return parse_decision(reply.text, repair), reply
