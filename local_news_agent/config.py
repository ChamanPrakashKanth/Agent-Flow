from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    model_backend: str = "ollama"
    model_name: str = "hermes3:3b"
    model_base_url: str = "http://127.0.0.1:11434"
    model_api_key: str = ""
    model_context_tokens: int = 2048
    tool_backend: str = "custom"
    hermes_command: str = "hermes"
    hermes_model: str = "hermes3:3b-hermes"
    hermes_timeout_seconds: int = 300
    x_profile_url: str = "https://x.com/ChamanKant44703"
    threads_profile_url: str = "https://www.threads.com/@chamanprakashkanth"
    publish_mode: str = "REVIEW"
    daily_publish_limit: int = 3
    min_importance: float = 0.62
    min_confidence: float = 0.70
    max_iterations: int = 24
    max_searches: int = 5
    max_page_reads: int = 8
    max_retries: int = 2
    max_observation_chars: int = 1500
    database_path: Path = Path("data/news_agent.db")
    queue_path: Path = Path("data/review_queue.jsonl")
    trajectory_path: Path = Path("logs/trajectories.jsonl")
    pexels_api_key: str = ""
    youtube_shorts_enabled: bool = True
    shorts_dir: Path = Path("data/shorts")
    voice_name: str = ""
    memory_budget_nodes: int = 8
    memory_consolidation_threshold: float = 0.60
    ollama_flash_attention: bool = True
    ollama_kv_cache_type: str = "q4_0"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        def val(name: str, default: str) -> str: return os.getenv(name, default)
        def bool_val(name: str, default: str) -> bool: return val(name, default).strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            model_backend=val("MODEL_BACKEND", "ollama"), model_name=val("MODEL_NAME", "hermes3:3b"),
            model_base_url=val("MODEL_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            model_api_key=val("MODEL_API_KEY", ""), model_context_tokens=int(val("MODEL_CONTEXT_TOKENS", "2048")),
            tool_backend=val("TOOL_BACKEND", "custom"), hermes_command=val("HERMES_COMMAND", "hermes"),
            hermes_model=val("HERMES_MODEL", "hermes3:3b-hermes"),
            hermes_timeout_seconds=int(val("HERMES_TIMEOUT_SECONDS", "300")), publish_mode=val("PUBLISH_MODE", "REVIEW").upper(),
            x_profile_url=val("X_PROFILE_URL", "https://x.com/ChamanKant44703"),
            threads_profile_url=val("THREADS_PROFILE_URL", "https://www.threads.com/@chamanprakashkanth"),
            daily_publish_limit=int(val("DAILY_PUBLISH_LIMIT", "3")), min_importance=float(val("MIN_IMPORTANCE", ".62")),
            min_confidence=float(val("MIN_CONFIDENCE", ".70")), max_iterations=int(val("MAX_ITERATIONS", "24")),
            max_searches=int(val("MAX_SEARCHES", "5")), max_page_reads=int(val("MAX_PAGE_READS", "8")),
            max_retries=int(val("MAX_RETRIES", "2")), max_observation_chars=int(val("MAX_OBSERVATION_CHARS", "1500")),
            database_path=Path(val("DATABASE_PATH", "data/news_agent.db")), queue_path=Path(val("QUEUE_PATH", "data/review_queue.jsonl")),
            trajectory_path=Path(val("TRAJECTORY_PATH", "logs/trajectories.jsonl")),
            pexels_api_key=val("PEXELS_API_KEY", ""),
            youtube_shorts_enabled=bool_val("YOUTUBE_DRAFTS_ENABLED", val("YOUTUBE_SHORTS_ENABLED", "true")),
            shorts_dir=Path(val("SHORTS_DIR", "data/shorts")),
            voice_name=val("VOICE_NAME", ""),
            memory_budget_nodes=int(val("MEMORY_BUDGET_NODES", "8")),
            memory_consolidation_threshold=float(val("MEMORY_CONSOLIDATION_THRESHOLD", "0.60")),
            ollama_flash_attention=bool_val("OLLAMA_FLASH_ATTENTION", "true"),
            ollama_kv_cache_type=val("OLLAMA_KV_CACHE_TYPE", "q4_0"),
        )

    def ensure_dirs(self) -> None:
        for path in (self.database_path, self.queue_path, self.trajectory_path, self.shorts_dir / "placeholder"):
            path.parent.mkdir(parents=True, exist_ok=True)
