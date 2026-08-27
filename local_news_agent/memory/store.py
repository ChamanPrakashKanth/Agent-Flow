from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from ..schemas import Story


def normalize_url(url: str) -> str:
    p = urlsplit(url); query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")])
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), query, ""))


def fingerprint(text: str, published_at: str = "") -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a","an","the","by","for","from","in","of","on","to","with","and","announces","announced","unveils","unveiled"}
    core = " ".join(sorted(set(w for w in words if w not in stop)))
    date = published_at[:10]
    return hashlib.sha256(f"{core}|{date}".encode()).hexdigest()[:24]


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path; path.parent.mkdir(parents=True, exist_ok=True); self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS stories (fingerprint TEXT PRIMARY KEY, headline TEXT, event TEXT, status TEXT, publication_status TEXT, payload TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY, fingerprint TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS failures (id INTEGER PRIMARY KEY, run_id TEXT, action TEXT, error TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, result TEXT, metrics TEXT, created_at TEXT);
        """); self.db.commit()

    def seen(self, story: Story) -> bool:
        fp = story.fingerprint or fingerprint(story.event or story.headline, story.published_at)
        if self.db.execute("SELECT 1 FROM stories WHERE fingerprint=? AND publication_status IN ('QUEUED','PUBLISHED')", (fp,)).fetchone(): return True
        for u in story.sources:
            if self.db.execute("SELECT 1 FROM urls WHERE url=?", (normalize_url(u),)).fetchone(): return True
        return False

    def save_story(self, story: Story, status: str) -> None:
        fp = story.fingerprint or fingerprint(story.event or story.headline, story.published_at); story.fingerprint = fp; now = datetime.now(timezone.utc).isoformat()
        self.db.execute("INSERT OR REPLACE INTO stories VALUES (?,?,?,?,?,?,?)", (fp, story.headline, story.event, story.verification_status, status, story.model_dump_json(), now))
        self.db.executemany("INSERT OR IGNORE INTO urls VALUES (?,?,?)", [(normalize_url(u), fp, now) for u in story.sources]); self.db.commit()

    def failure(self, run_id: str, action: str, error: str) -> None:
        self.db.execute("INSERT INTO failures(run_id,action,error,created_at) VALUES(?,?,?,?)", (run_id, action, error[:1000], datetime.now(timezone.utc).isoformat())); self.db.commit()

    def save_run(self, run_id: str, result: str, metrics: dict) -> None:
        self.db.execute("INSERT OR REPLACE INTO runs VALUES(?,?,?,?)", (run_id, result, json.dumps(metrics), datetime.now(timezone.utc).isoformat())); self.db.commit()

    def queued_today(self) -> int:
        day = datetime.now(timezone.utc).date().isoformat()
        return self.db.execute("SELECT count(*) FROM stories WHERE publication_status='QUEUED' AND created_at LIKE ?", (day+"%",)).fetchone()[0]

