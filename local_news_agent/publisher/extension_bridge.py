from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import websockets

logger = logging.getLogger(__name__)


class ChromeExtensionPublisher:
    """Publish X/Threads and upload Shorts privately through the Chrome bridge."""

    def __init__(self, uri: str = "ws://127.0.0.1:8765", token_path: Path | None = None):
        self.uri = uri
        self.token_path = token_path or Path(__file__).resolve().parents[2] / "data" / "bridge.token"

    async def _send_command_async(self, action: str, payload: dict[str, Any], timeout: float = 40.0) -> dict[str, Any]:
        if not self.token_path.exists():
            return {"success": False, "error": "BRIDGE_TOKEN_MISSING"}
        token = self.token_path.read_text(encoding="utf-8").strip()
        for attempt in range(5):
            command_sent = False
            try:
                async with websockets.connect(self.uri, open_timeout=2.0, max_size=50 * 1024 * 1024) as ws:
                    await ws.send(json.dumps({"type": "REGISTER_AGENT", "token": token}))
                    ack_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    ack = json.loads(ack_raw)

                    if not ack.get("extension_connected"):
                        await asyncio.sleep(1.0)
                        continue

                    req_id = str(uuid.uuid4())
                    await ws.send(json.dumps({
                        "type": "COMMAND",
                        "id": req_id,
                        "action": action,
                        "payload": payload
                    }))
                    command_sent = True

                    res_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    response = json.loads(res_raw)
                    if response.get("id") != req_id:
                        return {"success": False, "error": "BRIDGE_RESPONSE_ID_MISMATCH"}
                    return response
            except Exception:
                # The browser may still complete a mutation after a late or
                # lost acknowledgement. Never resend a command once sent.
                if command_sent:
                    return {"success": False, "error": "COMMAND_RESULT_UNKNOWN_NO_RETRY"}
                await asyncio.sleep(1.0)

        return {
            "success": False,
            "error": "EXTENSION_NOT_CONNECTED: Please ensure Chrome has the extension loaded from chrome_extension/ folder."
        }

    def publish_all(self, draft_record: dict[str, Any]) -> dict[str, Any]:
        draft = draft_record.get("draft", {})
        results: dict[str, Any] = {}

        async def _run():
            # 1. Publish to X
            x_text = draft.get("x", "")
            if x_text and draft_record.get("platform_status", {}).get("x") != "POSTED":
                res = await self._send_command_async("PUBLISH_X", {"text": x_text}, timeout=180.0)
                results["x"] = {
                    "status": "POSTED" if res.get("success") else "FAILED",
                    "url": str(res.get("url", "")),
                    "message": res.get("error", "Posted via Chrome Extension")
                }

            # 2. Publish to Threads
            threads_status = draft_record.get("platform_status", {}).get("threads")
            threads_text = draft.get("threads", "")
            if threads_status == "PAUSED":
                results["threads"] = {
                    "status": "PAUSED",
                    "url": "",
                    "message": "Threads publishing paused"
                }
            elif threads_text and threads_status != "POSTED":
                res = await self._send_command_async("PUBLISH_THREADS", {"text": threads_text}, timeout=180.0)
                results["threads"] = {
                    "status": "POSTED" if res.get("success") else "FAILED",
                    "url": str(res.get("url", "")),
                    "message": res.get("error", "Posted via Chrome Extension")
                }

            # 3. Upload the generated Short to YouTube as PRIVATE only.
            short = draft.get("youtube_short") or {}
            video_path = str(short.get("video_path", ""))
            if (
                short.get("generated") is True
                and video_path
                and draft_record.get("platform_status", {}).get("youtube") != "PRIVATE"
            ):
                res = await self._send_command_async(
                    "UPLOAD_YOUTUBE_PRIVATE",
                    {
                        "file_path": video_path,
                        "title": str(short.get("title", ""))[:100],
                        "description": str(short.get("description", ""))[:5000],
                        "visibility": "PRIVATE",
                        "run_id": str(draft_record.get("run_id", "")),
                    },
                    timeout=600.0,
                )
                results["youtube"] = {
                    "status": "PRIVATE" if res.get("success") and res.get("visibility") == "PRIVATE" else "FAILED",
                    "url": str(res.get("url", "")),
                    "visibility": str(res.get("visibility", "")),
                    "message": res.get("error", "Uploaded privately via Chrome Extension"),
                }

            return results

        return self._run_coro(_run())


    def _run_coro(self, coro: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(coro)).result()
        else:
            return asyncio.run(coro)

    def search_web(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        res = self._run_coro(self._send_command_async("SEARCH_WEB", {"query": query, "limit": limit}, timeout=25.0))
        if res.get("success") and isinstance(res.get("results"), list):
            return res.get("results", [])
        logger.warning("Chrome extension search returned error or empty: %s", res.get("error"))
        return []

    def extract_page(self, url: str) -> dict[str, Any] | None:
        res = self._run_coro(self._send_command_async("EXTRACT_PAGE", {"url": url}, timeout=30.0))
        if res.get("success") and isinstance(res.get("data"), dict):
            return res.get("data")
        logger.warning("Chrome extension page extraction returned error on %s: %s", url, res.get("error"))
        return None
