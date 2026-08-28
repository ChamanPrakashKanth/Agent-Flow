from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import websockets


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = PROJECT_ROOT / "data" / "bridge.token"
TEXT_ACTIONS = {"PUBLISH_X": 280, "PUBLISH_THREADS": 500}
SHORTS_ROOT = (PROJECT_ROOT / "data" / "shorts").resolve()

_EXTENSION_SOCKET: Any = None
_AUTHENTICATED_AGENTS: set[Any] = set()
_PENDING_RESPONSES: dict[str, tuple[Any, str]] = {}
_ALLOWED_EXTRACT_URLS: dict[str, None] = {}


def _load_or_create_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(48)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


BRIDGE_TOKEN = _load_or_create_token()


def _is_open(ws: Any) -> bool:
    return ws is not None and getattr(getattr(ws, "state", None), "name", "") == "OPEN"


def _origin(ws: Any) -> str:
    request = getattr(ws, "request", None)
    headers = getattr(request, "headers", None)
    return str(headers.get("Origin", "")) if headers else ""


ALLOWED_ACTIONS = {*TEXT_ACTIONS, "UPLOAD_YOUTUBE_PRIVATE", "SEARCH_WEB", "EXTRACT_PAGE"}


def _is_public_https_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            return False
        if parsed.port not in {None, 443} or host == "localhost" or host.endswith((".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            return True
        return not (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
    except ValueError:
        return False


def _valid_command(message: dict[str, Any]) -> tuple[bool, str]:
    action = message.get("action")
    if action not in ALLOWED_ACTIONS:
        return False, "ACTION_NOT_ALLOWED"
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return False, "INVALID_PAYLOAD"
    if action == "SEARCH_WEB":
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return False, "INVALID_SEARCH_QUERY"
        limit = payload.get("limit", 8)
        if not isinstance(limit, int) or limit < 1 or limit > 20:
            return False, "INVALID_SEARCH_LIMIT"
        return True, ""
    if action == "EXTRACT_PAGE":
        url = payload.get("url")
        if not isinstance(url, str) or len(url) > 2000 or not _is_public_https_url(url):
            return False, "INVALID_EXTRACT_URL"
        return True, ""
    if action in TEXT_ACTIONS:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return False, "EMPTY_POST"
        if len(text) > TEXT_ACTIONS[action]:
            return False, "POST_TOO_LONG"
        return True, ""
    if payload.get("visibility") != "PRIVATE":
        return False, "YOUTUBE_VISIBILITY_MUST_BE_PRIVATE"
    title = payload.get("title")
    description = payload.get("description")
    if not isinstance(title, str) or not title.strip() or len(title) > 100:
        return False, "INVALID_YOUTUBE_TITLE"
    if not isinstance(description, str) or len(description) > 5000:
        return False, "INVALID_YOUTUBE_DESCRIPTION"
    try:
        video_path = Path(str(payload.get("file_path", ""))).resolve(strict=True)
        video_path.relative_to(SHORTS_ROOT)
    except (OSError, ValueError):
        return False, "VIDEO_OUTSIDE_SHORTS_DIRECTORY"
    if video_path.suffix.lower() != ".mp4" or not video_path.is_file():
        return False, "INVALID_VIDEO_FILE"
    return True, ""


async def relay_handler(websocket: Any) -> None:
    global _EXTENSION_SOCKET
    try:
        async for raw in websocket:
            try:
                message = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(message, dict):
                continue

            message_type = message.get("type")
            if message_type == "REGISTER_EXTENSION":
                orig = _origin(websocket)
                if orig and not orig.startswith("chrome-extension://") and not orig.startswith("http://127.0.0.1"):
                    await websocket.close(code=1008, reason="extension origin required")
                    return
                if message.get("protocol") != 5:
                    await websocket.close(code=1008, reason="protocol mismatch")
                    return
                _EXTENSION_SOCKET = websocket
                logging.info("[Relay] authenticated Chrome extension connected")
                await websocket.send(json.dumps({"type": "ACK", "status": "EXTENSION_REGISTERED"}))


            elif message_type == "REGISTER_AGENT":
                supplied = str(message.get("token", ""))
                if not hmac.compare_digest(supplied, BRIDGE_TOKEN):
                    await websocket.close(code=1008, reason="authentication failed")
                    return
                _AUTHENTICATED_AGENTS.add(websocket)
                await websocket.send(json.dumps({"type": "ACK", "extension_connected": _is_open(_EXTENSION_SOCKET)}))

            elif message_type == "COMMAND":
                if websocket not in _AUTHENTICATED_AGENTS:
                    await websocket.close(code=1008, reason="agent authentication required")
                    return
                request_id = str(message.get("id", ""))
                valid, error = _valid_command(message)
                if not request_id or not valid:
                    await websocket.send(json.dumps({"id": request_id, "type": "RESPONSE", "success": False, "error": error or "MISSING_ID"}))
                    continue
                if not _is_open(_EXTENSION_SOCKET):
                    await websocket.send(json.dumps({"id": request_id, "type": "RESPONSE", "success": False, "error": "EXTENSION_NOT_CONNECTED"}))
                    continue
                _PENDING_RESPONSES[request_id] = (websocket, str(message.get("action", "")))
                logging.info("[Relay] forwarding approved %s command", message.get("action"))
                await _EXTENSION_SOCKET.send(json.dumps(message))

            elif message_type == "RESPONSE" and websocket is _EXTENSION_SOCKET:
                request_id = str(message.get("id", ""))
                pending = _PENDING_RESPONSES.pop(request_id, None)
                target, action = pending if pending else (None, "")
                if action == "SEARCH_WEB" and message.get("success") and target is not None:
                    for result in message.get("results", []):
                        url = result.get("url") if isinstance(result, dict) else None
                        if isinstance(url, str) and _is_public_https_url(url):
                            _ALLOWED_EXTRACT_URLS[url] = None
                    while len(_ALLOWED_EXTRACT_URLS) > 100:
                        _ALLOWED_EXTRACT_URLS.pop(next(iter(_ALLOWED_EXTRACT_URLS)))
                if _is_open(target) and target in _AUTHENTICATED_AGENTS:
                    await target.send(json.dumps(message))
    finally:
        if websocket is _EXTENSION_SOCKET:
            _EXTENSION_SOCKET = None
            logging.info("[Relay] Chrome extension disconnected")
        _AUTHENTICATED_AGENTS.discard(websocket)
        for request_id, (target, _action) in list(_PENDING_RESPONSES.items()):
            if target is websocket:
                _PENDING_RESPONSES.pop(request_id, None)


async def main() -> None:
    logging.info("Starting authenticated X/Threads/private-YouTube extension relay on ws://127.0.0.1:8765")
    async with websockets.serve(relay_handler, "127.0.0.1", 8765, max_size=50 * 1024 * 1024):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
