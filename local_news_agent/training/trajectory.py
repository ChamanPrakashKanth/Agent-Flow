from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TrajectoryLogger:
    def __init__(self, path: Path): self.path = path; path.parent.mkdir(parents=True, exist_ok=True)
    def log(self, **record: Any) -> None:
        safe = {"timestamp": datetime.now(timezone.utc).isoformat(), **record}
        with self.path.open("a", encoding="utf-8") as f: f.write(json.dumps(safe, ensure_ascii=False, default=str) + "\n")


def reward(result: str, factual: float, source_quality: float, duplicate: bool, unsupported: int, tool_calls: int, recovered: bool) -> float:
    value = (1.0 if result in {"QUEUED_FOR_REVIEW", "NO_POST"} else 0) + factual + .5 * source_quality
    value += .25 if recovered else 0; value -= 1.5 * unsupported + (1.0 if duplicate else 0) + max(0, tool_calls - 8) * .05
    return round(value, 4)

