from __future__ import annotations

import re
from urllib.parse import urlsplit
from ..schemas import Evidence, SearchResult, Story, VerificationStatus
from ..memory.store import fingerprint


def atomic_facts(text: str, limit: int = 6) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text.strip()))
    return [x[:500] for x in chunks if 30 <= len(x) <= 500][:limit]


def story_from_evidence(result: SearchResult, evidence: Evidence) -> Story:
    facts = evidence.claims or atomic_facts(evidence.excerpt)
    if not facts and result.snippet:
        facts = atomic_facts(result.snippet) or ([result.snippet[:500]] if len(result.snippet.strip()) >= 20 else [])
    if not facts and (result.title or evidence.title):
        facts = [result.title or evidence.title]
    event = facts[0] if facts else result.snippet[:500]
    has_facts = bool(facts)
    return Story(
        headline=result.title or evidence.title,
        event=event,
        published_at=evidence.published_at or result.published_at,
        sources=[evidence.url],
        key_facts=facts,
        confidence=.64 if has_facts else .2,
        importance=score_importance(result.title, event),
        verification_status=VerificationStatus.PARTIALLY_CONFIRMED if has_facts else VerificationStatus.UNVERIFIED,
        evidence=[evidence],
        fingerprint=fingerprint(event or result.title, evidence.published_at or result.published_at)
    )


def score_importance(headline: str, event: str) -> float:
    text = f"{headline} {event}".lower(); score = .55
    terms = (
        # AI & Computing
        "launch", "release", "research", "open source", "breakthrough", "model", "ai", "llm", "announce", "announces",
        "developer", "tool", "feature", "system", "version", "claude", "gpt", "gemini", "agent", "benchmark", "weights",
        # Semiconductors & Hardware
        "semiconductor", "chip", "chips", "wafer", "nanometer", "transistor", "tsmc", "nvidia", "intel", "asml",
        "lithography", "packaging", "gpu", "processor", "fab", "foundry", "silicon",
        # Theoretical Physics & Quantum Mechanics
        "quantum", "physics", "qubit", "qubits", "superconductor", "superconductivity", "entanglement", "photonics",
        "particle", "fusion", "cern", "collider", "laser", "thermodynamics", "optics",
        # Defense & Aerospace Engineering
        "defense", "aerospace", "hypersonic", "radar", "missile", "satellite", "propulsion", "military", "naval",
        "autonomous", "drone", "pentagon", "space", "orbit", "robotics", "engineering", "materials"
    )
    for term in terms:
        if term in text: score += .05
    for term in ("rumor", "might", "could", "shocking", "you won't believe"):
        if term in text: score -= .10
    return max(0.0, min(1.0, score))


def merge_evidence(story: Story, evidence: Evidence) -> Story:
    # A different domain is not automatically corroboration. Require shared
    # event terms before it can contribute to confirmation.
    stop={"this","that","with","from","have","will","into","about","after","before","their","there","news"}
    base={w for w in re.findall(r"[a-z0-9]+",f"{story.headline} {story.event}".lower()) if len(w)>3 and w not in stop}
    incoming={w for w in re.findall(r"[a-z0-9]+",f"{evidence.title} {evidence.excerpt}".lower()) if len(w)>3 and w not in stop}
    required=min(3,max(2,len(base)//4))
    if len(base & incoming) < required:
        return story
    if evidence.url not in story.sources: story.sources.append(evidence.url)
    story.evidence.append(evidence)
    for fact in evidence.claims or atomic_facts(evidence.excerpt):
        if fact not in story.key_facts: story.key_facts.append(fact)
    origins = {
        e.publisher.lower() if (e.canonical_origin or urlsplit(e.url).netloc.removeprefix("www.")) in {"news.google.com", "google.com"} and e.publisher and e.publisher not in {"Google News", "Web Source"}
        else (e.canonical_origin or urlsplit(e.url).netloc.removeprefix("www."))
        for e in story.evidence
    }
    if len(origins) >= 2:
        story.confidence = min(.96, .58 + .14 * len(origins)); story.verification_status = VerificationStatus.CONFIRMED
    else:
        story.confidence = max(story.confidence, .55); story.verification_status = VerificationStatus.PARTIALLY_CONFIRMED
    return story
