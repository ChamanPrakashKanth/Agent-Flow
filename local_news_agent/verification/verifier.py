from __future__ import annotations

import re
from ..schemas import Draft, Story, VerificationStatus


def tokenize(text: str) -> set[str]: return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def independent_sources(story: Story) -> int:
    origins = set()
    for e in story.evidence:
        origin = e.canonical_origin or re.sub(r"^www\.", "", re.sub(r"^https?://", "", e.url).split("/")[0])
        if origin in {"news.google.com", "google.com"} and e.publisher and e.publisher not in {"Google News", "Web Source"}:
            origin = e.publisher.lower()
        origins.add(origin)
    return len(origins)


def verify_story(story: Story) -> Story:
    count = independent_sources(story)
    if count >= 2 and story.key_facts:
        story.verification_status = VerificationStatus.CONFIRMED
        story.confidence = min(.95, .68 + .1 * count)
    elif count >= 1 and story.key_facts:
        story.verification_status = VerificationStatus.PARTIALLY_CONFIRMED
        story.confidence = min(story.confidence, .64)
    else:
        story.verification_status = VerificationStatus.UNVERIFIED
        story.confidence = .2
    return story


def verify_draft(draft: Draft, story: Story) -> Draft:
    evidence_text = " ".join(story.key_facts + [e.excerpt for e in story.evidence]); evidence_tokens = tokenize(evidence_text)
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", draft.x + "\n" + draft.threads) if len(x.strip()) >= 5]
    if not draft.x.strip() or not draft.threads.strip():
        draft.unsupported_claims = ["missing required draft text"]
        draft.verified = False
        return draft
    unsupported = []
    mapping: dict[str, list[str]] = {}
    for sentence in sentences:
        overlap = tokenize(sentence) & evidence_tokens
        urls = [e.url for e in story.evidence if len(tokenize(e.excerpt) & tokenize(sentence)) >= 2]
        if len(overlap) < 2 or not urls: unsupported.append(sentence)
        else: mapping[sentence] = urls
    draft.claim_evidence = mapping; draft.unsupported_claims = unsupported; draft.verified = not unsupported and story.verification_status == VerificationStatus.CONFIRMED
    return draft
