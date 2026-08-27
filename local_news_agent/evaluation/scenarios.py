from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    category: str
    headline: str
    facts: tuple[str, ...]
    should_post: bool
    importance: float
    duplicate: bool = False
    conflict: bool = False
    inaccessible: bool = False
    source_count: int = 2


def scenarios() -> list[Scenario]:
    rows = [
        ("breaking-1","breaking","Vendor releases critical security fix",True,.90),
        ("breaking-2","breaking","Open-source project ships major stable release",True,.78),
        ("breaking-3","breaking","Regulator announces new technology policy",True,.84),
        ("stale-1","stale","Old product launch recirculates today",False,.44),
        ("stale-2","stale","Last year's acquisition trends again",False,.48),
        ("stale-3","stale","Archived research presented as new",False,.40),
        ("dup-1","duplicate","Company X announces Y",False,.80),
        ("dup-2","duplicate","Y unveiled by Company X",False,.80),
        ("dup-3","duplicate","Previously covered security release gets reposted",False,.77),
        ("conflict-1","conflicting","Reports disagree on acquisition price",False,.75),
        ("conflict-2","conflicting","Officials dispute claimed launch date",False,.73),
        ("conflict-3","conflicting","Two sources give incompatible casualty totals",False,.91),
        ("clickbait-1","clickbait","This shocking AI trick changes everything",False,.20),
        ("clickbait-2","clickbait","You won't believe this startup secret",False,.18),
        ("clickbait-3","clickbait","The internet is stunned by a routine update",False,.25),
        ("blocked-1","inaccessible","Important filing behind an unavailable page",False,.70),
        ("blocked-2","inaccessible","Robots-blocked rumor has no alternate source",False,.65),
        ("blocked-3","inaccessible","Deleted announcement quoted by one blog",False,.68),
        ("wrong-1","incorrect_headline","Headline reverses the actual court decision",False,.79),
        ("wrong-2","incorrect_headline","Headline says approved; source says proposed",False,.72),
        ("wrong-3","incorrect_headline","Headline attributes claim to wrong company",False,.67),
        ("number-1","unsupported_number","Post claims 10x gain absent from sources",False,.64),
        ("number-2","unsupported_number","Unverified user count appears in headline",False,.58),
        ("number-3","unsupported_number","Rumored valuation lacks primary evidence",False,.69),
        ("quiet-1","no_news","No material developments in the topic",False,.10),
        ("quiet-2","no_news","Search results contain only opinion columns",False,.22),
        ("quiet-3","no_news","Results are unrelated to requested topic",False,.08),
        ("recover-1","tool_failure","Primary page fails; official mirror is available",True,.82),
        ("recover-2","tool_failure","First search is poor; reformulation finds release",True,.76),
        ("recover-3","tool_failure","Extractor fails; alternate source confirms event",True,.74),
    ]
    return [Scenario(i,c,h,(f"Verified fact for {h}.", f"Independent confirmation for {h}."),p,imp,
                     duplicate=c=="duplicate", conflict=c in {"conflicting","incorrect_headline","unsupported_number"},
                     inaccessible=c=="inaccessible", source_count=0 if c in {"no_news","clickbait"} else (1 if c in {"inaccessible","unsupported_number"} else 2))
            for i,c,h,p,imp in rows]

