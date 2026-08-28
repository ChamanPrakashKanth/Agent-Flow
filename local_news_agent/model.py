import json
import os
import re
from dataclasses import dataclass
import httpx
from .config import Settings


from typing import Any


@dataclass
class ModelReply:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


def estimate_tokens(text: str) -> int:
    """Fast, reliable token estimation for Llama/Hermes tokenizers (~3.6-4.0 chars/token)."""
    if not text:
        return 0
    # Add base token overhead for whitespace/punctuation boundaries
    return max(1, int(len(text) / 3.7) + len(text.split()) // 8)


def count_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate token usage for a list of ChatML/Hermes messages."""
    tokens = 4  # overhead for conversation container
    for msg in messages:
        tokens += 4  # role and message format framing tokens
        content = str(msg.get("content", ""))
        tokens += estimate_tokens(content)
        if "name" in msg:
            tokens += estimate_tokens(str(msg["name"])) + 2
    return tokens


class LocalModel:
    def __init__(self, settings: Settings):
        self.s = settings
        if self.s.model_backend == "ollama":
            if self.s.ollama_flash_attention:
                os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
            if self.s.ollama_kv_cache_type:
                os.environ["OLLAMA_KV_CACHE_TYPE"] = self.s.ollama_kv_cache_type

    def chat_messages(self, messages: list[dict[str, Any]], json_mode: bool = False, temperature: float = 0.1) -> ModelReply:
        max_gen = min(512, max(128, self.s.model_context_tokens // 2))
        if self.s.model_backend == "ollama":
            payload = {
                "model": self.s.model_name,
                "stream": False,
                "messages": messages,
                "keep_alive": "5m",
                "options": {
                    "temperature": temperature,
                    "num_ctx": self.s.model_context_tokens,
                    "num_predict": max_gen,
                },
            }
            if json_mode:
                payload["format"] = "json"
            response = httpx.post(f"{self.s.model_base_url}/api/chat", json=payload, timeout=180)
            response.raise_for_status()
            data = response.json()
            return ModelReply(
                data["message"]["content"],
                data.get("prompt_eval_count", 0) or count_messages_tokens(messages),
                data.get("eval_count", 0),
            )

        headers = {"Content-Type": "application/json"}
        if self.s.model_api_key:
            headers["Authorization"] = f"Bearer {self.s.model_api_key}"
        payload = {
            "model": self.s.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_gen,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = httpx.post(f"{self.s.model_base_url}/v1/chat/completions", headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens") or count_messages_tokens(messages)
        completion_tokens = usage.get("completion_tokens", 0)
        return ModelReply(data["choices"][0]["message"]["content"], prompt_tokens, completion_tokens)

    def unload_model(self) -> bool:
        """Proactively unload model from Ollama VRAM to free GPU memory."""
        if self.s.model_backend != "ollama":
            return True
        try:
            httpx.post(
                f"{self.s.model_base_url}/api/generate",
                json={"model": self.s.model_name, "keep_alive": 0},
                timeout=5,
            )
            return True
        except Exception:
            return False

    def chat(self, system: str, user: str, json_mode: bool = False, temperature: float = 0.1) -> ModelReply:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self.chat_messages(messages, json_mode=json_mode, temperature=temperature)


def first_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{(?:[^{}]|\{[^{}]*\})*\}", text, re.S)
    if not match:
        raise ValueError("model returned no JSON object")
    return json.loads(match.group(0))


