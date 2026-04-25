from gg.tasks.connectors._refs import extract_mentions, extract_refs, extract_urls


def test_extract_refs_github_full():
    text = "see owner/repo#42 and other/repo#5"
    refs = extract_refs(text)
    kinds = [(r.platform, r.normalized) for r in refs]

    assert ("github", "owner/repo#42") in kinds
    assert ("github", "other/repo#5") in kinds


def test_extract_refs_github_short_with_default_repo():
    refs = extract_refs("fixes #12 and #7", default_repo="acme/web")
    normalized = [r.normalized for r in refs]

    assert "acme/web#12" in normalized
    assert "acme/web#7" in normalized


def test_extract_refs_jira_keys():
    refs = extract_refs("Blocked by PROJ-123, relates to ABC-7")
    assert ("jira", "PROJ-123") in [(r.platform, r.normalized) for r in refs]
    assert ("jira", "ABC-7") in [(r.platform, r.normalized) for r in refs]


def test_extract_refs_dedup():
    refs = extract_refs("#1 #1 owner/repo#1", default_repo="owner/repo")
    normalized = [r.normalized for r in refs]

    assert normalized.count("owner/repo#1") == 1


def test_extract_urls_strips_trailing_punctuation():
    urls = extract_urls("check https://example.com/foo. and https://a.b/x.png)")
    assert "https://example.com/foo" in urls
    assert "https://a.b/x.png" in urls


def test_extract_mentions():
    mentions = extract_mentions("cc @alice and @bob-42, also email a@b.com")
    assert "alice" in mentions
    assert "bob-42" in mentions
    assert "b" not in mentions
