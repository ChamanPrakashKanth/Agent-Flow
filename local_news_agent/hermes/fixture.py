from __future__ import annotations

from .tools import NewsTools
from ..evaluation.scenarios import scenarios
from ..schemas import Evidence, SearchResult


class FixtureTools(NewsTools):
    def _find(self, query: str):
        return next((x for x in scenarios() if x.id in query or x.headline.lower() in query.lower()), scenarios()[0])
    def search(self, query: str, limit: int=8) -> list[SearchResult]:
        s=self._find(query)
        return [SearchResult(title=s.headline,url=f"fixture://{s.id}/{i}",snippet=s.facts[min(i,len(s.facts)-1)],source=f"source-{i}") for i in range(min(s.source_count,limit))]
    def extract(self, url: str) -> Evidence:
        sid=url.split("/")[2]; s=next(x for x in scenarios() if x.id==sid)
        if s.inaccessible: raise RuntimeError("fixture page unavailable")
        i=int(url.rsplit("/",1)[-1]); return Evidence(url=url,title=s.headline,publisher=f"source-{i}",excerpt=s.facts[min(i,len(s.facts)-1)],claims=[s.facts[min(i,len(s.facts)-1)]],primary=i==0,canonical_origin=f"origin-{i}")

