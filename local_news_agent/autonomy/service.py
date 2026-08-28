from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..config import Settings
from ..hermes.tools import ChromeExtensionWebTools, DirectWebTools
from ..publisher.extension_bridge import ChromeExtensionPublisher
from ..schemas import Evidence, SearchResult
from ..video.shorts_creator import ShortsCreator
from .bmw import BoundedMemoryWindow
from .controller import ForecastController
from .loop import RecursiveAgent
from .protocol import ActionDecision
from .qwen import QwenLlamaCppModel
from .storage import RunStore
from .youtube import YouTubeDraftWriter


class QwenHarness:
    def __init__(self, settings: Settings, browser_backend: str = "direct", model: Any | None = None):
        self.s = settings; self.s.ensure_dirs(); self.use_extension = browser_backend == "extension"
        self.browser = ChromeExtensionWebTools() if self.use_extension else DirectWebTools()
        self.bridge = ChromeExtensionPublisher() if self.use_extension else None
        self.model = model or QwenLlamaCppModel(settings.qwen_llamacpp_url, settings.qwen_model_name, settings.qwen_context_tokens)
        self.memory = BoundedMemoryWindow(settings.bmw_max_items, settings.bmw_max_tokens)
        self.controller = ForecastController(); self.store = RunStore(settings.database_path)
        self.results: list[Any] = []; self.facts: list[dict[str, Any]] = []; self.topic = ""
        self.x_draft = ""; self.short_script = ""; self.youtube_draft: dict[str, Any] | None = None
        self.youtube = YouTubeDraftWriter(settings.youtube_drafts_dir, ShortsCreator(settings))

    def _decide(self, context: dict[str, Any], actions: list[str]) -> tuple[ActionDecision, int]:
        decision, reply = self.model.decide(context["objective"], context["memory"], actions)
        # A small local model occasionally ignores JSON-mode despite the server
        # request. Recovery is deterministic and read-only: advance the next
        # evidence-gathering step instead of treating malformed prose as a tool
        # command or giving up on an otherwise valid task.
        required_stage = None
        if not self.results:
            required_stage = ("search_web", {"query": self.topic}, "Candidate sources with provenance.")
        elif not self.facts:
            required_stage = ("extract_page", {"index": 0}, "Sourced factual claims.")
        elif not self.x_draft:
            required_stage = ("draft_x_post", {}, "Concise sourced X draft.")
        elif not self.short_script:
            required_stage = ("create_short_script", {}, "Independent short-form script.")
        elif self.youtube_draft is None:
            required_stage = ("save_youtube_draft", {"script": self.short_script}, "Rendered local YouTube draft; no upload.")
        if required_stage and decision.action != required_stage[0]:
            action, arguments, expected = required_stage
            decision = ActionDecision(thought_summary="Bounded workflow guard advanced the next required safe stage.", action=action, arguments=arguments, expected_result=expected, confidence=0.6)
        return decision, reply.prompt_tokens

    def _search(self, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or self.topic)
        if self.bridge is not None:
            raw = self.bridge.search_web(query, 5)
            self.results = [SearchResult.model_validate(item) for item in raw]
        else:
            self.results = self.browser.search(query, 5)
        sources = [r.url for r in self.results]
        return {"ok": bool(self.results), "summary": f"found {len(self.results)} candidate sources", "sources": sources}

    def _extract(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self.results: return {"ok": False, "error": "no_search_results"}
        index = max(0, min(int(args.get("index", 0)), len(self.results) - 1)); source = self.results[index]
        if self.bridge is not None:
            raw = self.bridge.extract_page(source.url)
            evidence = Evidence.model_validate(raw) if raw else self.browser.extract(source.url)
        else:
            evidence = self.browser.extract(source.url)
        claims = evidence.claims or [evidence.excerpt[:280]]
        self.facts.extend({"claim": c, "source": evidence.url} for c in claims if c)
        return {"ok": bool(claims), "summary": f"extracted {len(claims)} sourced claims", "sources": [evidence.url]}

    def _save_fact(self, args: dict[str, Any]) -> dict[str, Any]:
        claim, source = str(args.get("claim", "")).strip(), str(args.get("source", "")).strip()
        if not claim or not source: return {"ok": False, "error": "claim_and_source_required"}
        self.facts.append({"claim": claim[:500], "source": source}); return {"ok": True, "summary": "fact retained", "sources": [source]}

    def _draft_x(self, args: dict[str, Any]) -> dict[str, Any]:
        facts = self.facts[:3]
        if not facts: return {"ok": False, "error": "no_sourced_facts"}
        text = str(args.get("text") or f"{facts[0]['claim']} Source: {facts[0]['source']}")[:280]
        self.x_draft = text
        return {"ok": True, "draft": text, "summary": "X draft created from sourced facts", "sources": [x["source"] for x in facts]}

    def _short_script(self, args: dict[str, Any]) -> dict[str, Any]:
        facts = self.facts[:3]
        if not facts: return {"ok": False, "error": "no_sourced_facts"}
        hook = str(args.get("hook") or f"Here is what changed: {facts[0]['claim']}")
        script = f"{hook} Here is the context. {facts[0]['claim']} Why it matters: this development affects the wider field. Sources are listed in the draft notes."
        self.short_script = script[:900]
        return {"ok": True, "script": self.short_script, "summary": "independent short-form script created", "sources": [x["source"] for x in facts]}

    def _save_youtube(self, args: dict[str, Any]) -> dict[str, Any]:
        script = str(args.get("script", "")).strip()
        if not script: return {"ok": False, "error": "script_required"}
        draft = self.youtube.save(self.topic, script, str(args.get("title") or f"{self.topic[:70]} #Shorts"), str(args.get("description") or "Local research draft. Sources included.")[:3000], [x["source"] for x in self.facts], list(args.get("keywords") or self.topic.split()[:3]), str(args.get("run_id") or "qwen"))
        self.youtube_draft = draft
        return {"ok": True, "draft": draft, "summary": "YouTube draft saved locally; publishing is disabled", "sources": [x["source"] for x in self.facts]}

    def run(self, topic: str):
        self.topic = topic
        self.results = []; self.facts = []; self.x_draft = ""; self.short_script = ""; self.youtube_draft = None
        tools = {"search_web": self._search, "open_page": self._extract, "extract_page": self._extract, "save_fact": self._save_fact, "draft_x_post": self._draft_x, "create_short_script": self._short_script, "save_youtube_draft": self._save_youtube}
        return RecursiveAgent(self._decide, tools, self.memory, self.controller, self.store, self.s.qwen_max_actions).run(topic)
