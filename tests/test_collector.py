from datetime import UTC, datetime

from cyber_rss.collector import MAX_ENTRIES_PER_FEED, collect_source
from cyber_rss.sources import Source

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Critical CVE-2026-12345 actively exploited</title>
<link>https://example.org/advisory/1</link>
<description>Remote code execution affecting hospitals.</description>
<pubDate>Fri, 04 Sep 2026 07:00:00 GMT</pubDate>
<guid>advisory-1</guid></item>
</channel></rss>"""


def test_collect_source_normalizes_and_scores_entries():
    source = Source("cert", "CERT Test", "https://example.org/feed.xml")

    articles = collect_source(source, RSS, now=datetime(2026, 9, 4, 8, tzinfo=UTC))

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "Critical CVE-2026-12345 actively exploited"
    assert article.url == "https://example.org/advisory/1"
    assert article.source_name == "CERT Test"
    assert article.category == "cert"
    assert article.published_at == datetime(2026, 9, 4, 7, tzinfo=UTC)
    assert article.importance == "critical"
    assert article.score >= 70
    assert article.fingerprint


def test_collect_source_rejects_non_http_article_links():
    unsafe = RSS.replace(b"https://example.org/advisory/1", b"javascript:alert(1)")

    articles = collect_source(
        Source("cert", "CERT Test", "https://example.org/feed.xml"),
        unsafe,
        now=datetime(2026, 9, 4, 8, tzinfo=UTC),
    )

    assert articles == []


def test_collect_source_borne_les_champs_et_le_nombre_d_entrees():
    items = b"".join(
        b"<item><title>" + (b"A" * 800) + b"</title>"
        b"<link>https://example.org/article/" + str(index).encode() + b"</link>"
        b"<description>" + (b"B" * 7000) + b"</description></item>"
        for index in range(MAX_ENTRIES_PER_FEED + 5)
    )
    payload = b"<rss version='2.0'><channel><title>Test</title>" + items + b"</channel></rss>"

    articles = collect_source(
        Source("news", "Test", "https://example.org/feed.xml"),
        payload,
        now=datetime(2026, 9, 4, 8, tzinfo=UTC),
    )

    assert len(articles) == MAX_ENTRIES_PER_FEED
    assert len(articles[0].title) == 500
    assert len(articles[0].summary) == 5000


def test_collect_source_isole_une_entree_malformee_dans_un_flux_bozo():
    payload = b"""<rss version="2.0"><channel><title>Test</title>
    <item><title>Mauvaise date</title><link>https://example.org/bad</link>
    <pubDate>date impossible</pubDate></item>
    <item><title>Valide</title><link>https://example.org/good</link></item>
    </channel></rss>trailing"""

    articles = collect_source(
        Source("news", "Test", "https://example.org/feed.xml"),
        payload,
        now=datetime(2026, 9, 4, 8, tzinfo=UTC),
    )

    assert [article.title for article in articles] == ["Mauvaise date", "Valide"]


def test_collect_source_canonicalise_l_url_pour_dedupliquer_les_traceurs():
    first = RSS.replace(
        b"https://example.org/advisory/1",
        b"HTTPS://Example.ORG:443/advisory/1/?utm_source=rss#fragment",
    )
    second = RSS.replace(
        b"https://example.org/advisory/1",
        b"https://example.org/advisory/1?fbclid=tracking",
    )
    source = Source("cert", "CERT Test", "https://example.org/feed.xml")

    article_a = collect_source(source, first)[0]
    article_b = collect_source(source, second)[0]

    assert article_a.url == "https://example.org/advisory/1"
    assert article_a.fingerprint == article_b.fingerprint
