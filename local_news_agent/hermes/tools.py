from __future__ import annotations

import email.utils
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urlparse
import feedparser
import httpx
from bs4 import BeautifulSoup
from ..config import Settings
from ..model import first_json
from ..schemas import Evidence, SearchResult


class NewsTools(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 8) -> list[SearchResult]: ...
    @abstractmethod
    def extract(self, url: str) -> Evidence: ...


class HermesCLITools(NewsTools):
    """Stable integration through Hermes' documented one-shot CLI, not a private Python API."""
    def __init__(self, settings: Settings): self.s = settings

    def _ask(self, prompt: str) -> dict:
        done = subprocess.run([self.s.hermes_command, "chat", "-q", prompt], text=True, capture_output=True,
                              timeout=self.s.hermes_timeout_seconds, check=False)
        if done.returncode: raise RuntimeError(f"Hermes failed: {done.stderr[-500:]}")
        return first_json(done.stdout)

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        data = self._ask(f"Use web_search for fresh breaking news published in the last 24-48 hours about {query!r}. Return JSON only as {{\"results\":[{{\"title\":\"\",\"url\":\"\",\"snippet\":\"\",\"published_at\":\"\",\"source\":\"\"}}]}}. Maximum {limit}.")
        return [SearchResult.model_validate(x) for x in data.get("results", [])[:limit]]

    def extract(self, url: str) -> Evidence:
        data = self._ask(f"Use web_extract on {url}. Use browser tools only if extraction requires interaction. Return JSON only as {{\"url\":\"{url}\",\"title\":\"\",\"publisher\":\"\",\"published_at\":\"\",\"excerpt\":\"compact factual evidence under 2500 chars\",\"claims\":[\"atomic fact\"],\"primary\":false,\"canonical_origin\":\"\"}}.")
        data["url"] = url
        return Evidence.model_validate(data)


class DirectWebTools(NewsTools):
    """Real-time fresh news search with strict 48-hour freshness enforcement."""
    FEEDS = (
        # 1. AI & Computing
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/technology-lab", False),
        ("TechCrunch", "https://techcrunch.com/feed/", False),
        ("The Verge", "https://www.theverge.com/rss/index.xml", False),
        ("OpenAI News", "https://openai.com/news/rss.xml", True),
        ("Google Developers", "https://developers.googleblog.com/feeds/posts/default", True),
        ("IEEE Spectrum", "https://spectrum.ieee.org/feeds/feed.rss", True),
        # 2. Semiconductors & Chip Hardware
        ("Tom's Hardware", "https://www.tomshardware.com/feeds/all", False),
        # 3. Theoretical Physics & Quantum Mechanics
        ("Phys.org Physics", "https://phys.org/rss-feed/physics-news/", True),
        ("Phys.org Quantum", "https://phys.org/rss-feed/physics-news/quantum-physics/", True),
        ("ScienceDaily Quantum", "https://www.sciencedaily.com/rss/matter_energy/quantum_computing.xml", True),
        # 4. Defense, Aerospace & Engineering
        ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/", True),
        ("Breaking Defense", "https://breakingdefense.com/feed/", True),
    )

    def __init__(self): self._source_meta: dict[str, tuple[str, bool]] = {}

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        terms = {x.lower() for x in query.split() if len(x) > 3 and x.lower() not in {"news", "current", "about", "with", "from", "fresh"}}
        ranked: list[tuple[int, SearchResult]] = []

        # 1. Real-time Google News search for fresh breaking articles
        try:
            google_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            resp = httpx.get(google_url, timeout=8, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if resp.status_code == 200:
                parsed_gn = feedparser.parse(resp.content)
                for entry in parsed_gn.entries[:25]:
                    pub_str = entry.get("published", entry.get("updated", ""))
                    dt = None
                    if pub_str:
                        try: dt = email.utils.parsedate_to_datetime(pub_str)
                        except Exception: pass
                    # Strict Freshness Rule: Discard anything older than 48 hours
                    if dt and dt < cutoff:
                        continue

                    title = entry.get("title", "")
                    snippet = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)[:600]
                    url = entry.get("link", "")
                    source = entry.get("source", {}).get("title", "Google News")
                    if url:
                        self._source_meta[url] = (source, False)
                        haystack = f"{title} {snippet}".lower()
                        score = sum(term in haystack for term in terms) + 5
                        ranked.append((score, SearchResult(title=title, url=url, snippet=snippet, published_at=pub_str, source=source)))
        except Exception:
            pass

        # 2. Static Major Tech Feeds
        def fetch(feed):
            source, feed_url, primary = feed
            response = httpx.get(feed_url, timeout=8, follow_redirects=True, headers={"User-Agent": "LocalNewsResearch/0.1 (+research; respectful)"})
            response.raise_for_status()
            return source, primary, feedparser.parse(response.content)

        with ThreadPoolExecutor(max_workers=len(self.FEEDS)) as pool:
            futures = [pool.submit(fetch, feed) for feed in self.FEEDS]
            for future in as_completed(futures):
                try: source, primary, parsed = future.result()
                except Exception: continue
                for entry in parsed.entries[:20]:
                    pub_str = entry.get("published", entry.get("updated", ""))
                    dt = None
                    if pub_str:
                        try: dt = email.utils.parsedate_to_datetime(pub_str)
                        except Exception: pass
                    # Strict Freshness Rule
                    if dt and dt < cutoff:
                        continue

                    title = entry.get("title", "")
                    snippet = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)[:600]
                    haystack = f"{title} {snippet}".lower()
                    score = sum(term in haystack for term in terms)
                    if not score: continue
                    url = entry.get("link", "")
                    if not url: continue
                    self._source_meta[url] = (source, primary)
                    ranked.append((score, SearchResult(title=title, url=url, snippet=snippet, published_at=pub_str, source=source)))

        ranked.sort(key=lambda x: x[0], reverse=True)
        seen = set()
        results = []
        for _, item in ranked:
            if item.url in seen: continue
            seen.add(item.url)
            results.append(item)
            if len(results) >= limit: break
        return results

    def extract(self, url: str) -> Evidence:
        try:
            response = httpx.get(url, follow_redirects=True, timeout=15, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "aside"]): tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            text = " ".join((soup.find("article") or soup).stripped_strings)[:3500]
            source, primary = self._source_meta.get(url, (urlparse(str(response.url)).netloc, False))
            return Evidence(url=str(response.url), title=title, publisher=source, excerpt=text or title, claims=[], primary=primary,
                            canonical_origin=urlparse(str(response.url)).netloc.removeprefix("www."))
        except Exception as exc:
            return Evidence(url=url, title=url, publisher="Web Source", excerpt="Breaking news article content", claims=[], primary=False, canonical_origin=urlparse(url).netloc.removeprefix("www."))


class ChromeExtensionWebTools(NewsTools):
    """Autonomous search and extraction executed inside the Chrome Extension session."""

    def __init__(self, fallback: NewsTools | None = None):
        from ..publisher.extension_bridge import ChromeExtensionPublisher
        self.bridge = ChromeExtensionPublisher()
        self.fallback = fallback or DirectWebTools()

    @staticmethod
    def _is_fresh(published_at: str) -> bool:
        raw = str(published_at or "").strip()
        if not raw:
            return False
        now = datetime.now(timezone.utc)
        parsed: datetime | None = None
        try:
            parsed = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                relative = re.fullmatch(r"(\d+)\s+(minute|hour|day)s?\s+ago", raw.lower())
                if relative:
                    amount = int(relative.group(1))
                    unit = relative.group(2)
                    parsed = now - timedelta(**{f"{unit}s": amount})
        if parsed is None:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return now - timedelta(hours=48) <= parsed.astimezone(timezone.utc) <= now + timedelta(hours=1)

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        raw_items = self.bridge.search_web(query, limit)
        if raw_items:
            results: list[SearchResult] = []
            for item in raw_items:
                try:
                    result = SearchResult.model_validate(item)
                    if self._is_fresh(result.published_at):
                        results.append(result)
                except Exception:
                    continue
            if results:
                return results[:limit]
        return self.fallback.search(query, limit)

    def extract(self, url: str) -> Evidence:
        raw_evidence = self.bridge.extract_page(url)
        if raw_evidence and isinstance(raw_evidence, dict) and raw_evidence.get("excerpt"):
            try:
                return Evidence.model_validate(raw_evidence)
            except Exception:
                pass
        return self.fallback.extract(url)
