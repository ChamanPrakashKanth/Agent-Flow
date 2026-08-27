from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
from pathlib import Path

import websockets

from local_news_agent.config import Settings


settings = Settings.from_env()
print("LOCAL NEWS AGENT HEALTH")
print(f"Model: {settings.model_backend} / {settings.model_name}")
print(f"Publishing: {settings.publish_mode}; limit={settings.daily_publish_limit}")
print(f"X: {settings.x_profile_url}")
print(f"Threads: {settings.threads_profile_url}")

database = Path(settings.database_path)
if database.exists():
    with sqlite3.connect(database) as connection:
        print(f"SQLite: {connection.execute('PRAGMA integrity_check').fetchone()[0]}")
else:
    print("SQLite: not initialized")

queue = Path(settings.queue_path)
records = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines() if line.strip()] if queue.exists() else []
print(f"Queue records: {len(records)}")
for record in records:
    print(f"- {record.get('run_id')}: {record.get('status')} {record.get('platform_status')}")


async def check_bridge() -> None:
    token_path = Path("data/bridge.token")
    if not token_path.exists():
        print("Chrome bridge: token not initialized")
        return
    try:
        async with websockets.connect("ws://127.0.0.1:8765", open_timeout=2.0) as websocket:
            await websocket.send(json.dumps({
                "type": "REGISTER_AGENT",
                "token": token_path.read_text(encoding="utf-8").strip(),
            }))
            response = json.loads(await websocket.recv())
            state = "extension connected" if response.get("extension_connected") else "server ready; extension disconnected"
            print(f"Chrome bridge: {state}")
    except Exception as exc:
        print(f"Chrome bridge: offline ({type(exc).__name__})")


asyncio.run(check_bridge())

task_check = subprocess.run(
    ["powershell.exe", "-NoProfile", "-Command", "(Get-ScheduledTask -TaskName 'Local Ollama News Agent' -ErrorAction SilentlyContinue).State"],
    capture_output=True,
    text=True,
    check=False,
)
print(f"Scheduled task: {task_check.stdout.strip() or 'not readable/not registered'}")
