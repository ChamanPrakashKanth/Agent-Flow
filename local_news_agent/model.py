from __future__ import annotations

import json
import re
from dataclasses import dataclass
import httpx
from .config import Settings


@dataclass
class ModelReply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LocalModel:
    def __init__(self, settings: Settings): self.s = settings

    def chat(self, system: str, user: str, json_mode: bool = False, temperature: float = 0.1) -> ModelReply:
        if self.s.model_backend == "ollama":
            payload = {"model": self.s.model_name, "stream": False, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                       "options": {"temperature": temperature, "num_ctx": self.s.model_context_tokens}}
            if json_mode: payload["format"] = "json"
            response = httpx.post(f"{self.s.model_base_url}/api/chat", json=payload, timeout=180)
            response.raise_for_status(); data = response.json()
            return ModelReply(data["message"]["content"], data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        headers = {"Content-Type": "application/json"}
        if self.s.model_api_key: headers["Authorization"] = f"Bearer {self.s.model_api_key}"
        payload = {"model": self.s.model_name, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temperature}
        if json_mode: payload["response_format"] = {"type": "json_object"}
        response = httpx.post(f"{self.s.model_base_url}/v1/chat/completions", headers=headers, json=payload, timeout=180)
        response.raise_for_status(); data = response.json(); usage = data.get("usage", {})
        return ModelReply(data["choices"][0]["message"]["content"], usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def first_json(text: str) -> dict:
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    match = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.S)
    if not match: raise ValueError("model returned no JSON object")
    return json.loads(match.group(0))

