from local_news_agent.schemas import Draft, Evidence, Story
from local_news_agent.verification.verifier import verify_draft, verify_story
from local_news_agent.research.service import merge_evidence


def test_two_origins_confirm_story():
    s=Story(headline="Release",event="Project released version 2",key_facts=["Project released version 2 after testing."],evidence=[
        Evidence(url="https://official.test/a",excerpt="Project released version 2 after testing.",canonical_origin="official"),
        Evidence(url="https://news.test/b",excerpt="Project released version 2 after testing.",canonical_origin="news")])
    assert verify_story(s).verification_status == "CONFIRMED"


def test_one_origin_never_confirms_story():
    s = Story(
        headline="Release",
        event="Project released version 2",
        key_facts=["Project released version 2.", "Testing completed."],
        evidence=[Evidence(
            url="https://official.test/a",
            excerpt="Project released version 2. Testing completed.",
            canonical_origin="official",
            primary=True,
        )],
    )
    assert verify_story(s).verification_status == "PARTIALLY_CONFIRMED"


def test_unsupported_draft_is_blocked():
    s=Story(headline="Release",event="Project released version 2",key_facts=["Project released version 2."],evidence=[Evidence(url="https://official.test/a",excerpt="Project released version 2.")])
    d=Draft(x="Project released version 2 and gained ten million users.",threads="The update is available.")
    assert not verify_draft(d,s).verified
    assert d.unsupported_claims


def test_short_schema_placeholder_is_blocked():
    s=Story(headline="Release",event="Project released version 2",key_facts=["Project released version 2."],evidence=[Evidence(url="https://official.test/a",excerpt="Project released version 2.")])
    d=Draft(x="max 280 chars",threads="Project released version 2.")
    assert not verify_draft(d,s).verified
    assert "max 280 chars" in d.unsupported_claims


def test_unrelated_domain_does_not_confirm_story():
    s=Story(headline="Vendor releases critical security fix",event="Vendor fixed a critical authentication flaw",sources=["https://official.test/a"],
            evidence=[Evidence(url="https://official.test/a",title="Security fix",excerpt="Vendor fixed a critical authentication flaw",canonical_origin="official")])
    merge_evidence(s,Evidence(url="https://other.test/b",title="Developer conference",excerpt="A startup demonstrated a new database tool",canonical_origin="other"))
    assert len(s.sources)==1
    assert s.verification_status != "CONFIRMED"
