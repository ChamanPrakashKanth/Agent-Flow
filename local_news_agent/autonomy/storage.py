from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


class RunStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True); self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS harness_runs (run_id TEXT PRIMARY KEY, status TEXT, payload TEXT, created_at TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS harness_steps (run_id TEXT, iteration INTEGER, action TEXT, result TEXT, metrics TEXT, created_at TEXT)")
        self.db.commit()

    def step(self, run_id: str, iteration: int, action: str, result: str, metrics: dict) -> None:
        self.db.execute("INSERT INTO harness_steps VALUES (?,?,?,?,?,?)", (run_id, iteration, action, result[:1500], json.dumps(metrics), datetime.now(timezone.utc).isoformat())); self.db.commit()

    def finish(self, run_id: str, status: str, payload: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO harness_runs VALUES (?,?,?,?)", (run_id, status, json.dumps(payload), datetime.now(timezone.utc).isoformat())); self.db.commit()

    def inspect(self, run_id: str) -> dict:
        run = self.db.execute("SELECT status,payload,created_at FROM harness_runs WHERE run_id=?", (run_id,)).fetchone()
        steps = self.db.execute("SELECT iteration,action,result,metrics,created_at FROM harness_steps WHERE run_id=? ORDER BY iteration", (run_id,)).fetchall()
        return {"run": {"status": run[0], "payload": json.loads(run[1]), "created_at": run[2]} if run else None, "steps": [{"iteration": x[0], "action": x[1], "result": x[2], "metrics": json.loads(x[3]), "created_at": x[4]} for x in steps]}
